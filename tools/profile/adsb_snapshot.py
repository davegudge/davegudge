#!/usr/bin/env python3
"""Export safe aggregate telemetry from a local dump1090-fa receiver."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_JSON_DIR = Path("/run/dump1090-fa")
DEFAULT_STATE_FILE = Path.home() / ".local/state/profile-adsb-window.json"
MAX_AIRCRAFT_AGE_SECONDS = 120
MAX_STATS_AGE_SECONDS = 180
WINDOW_SECONDS = 30 * 60
MAX_POLL_GAP_SECONDS = 300
AIRCRAFT_ID = re.compile(r"~?[0-9a-fA-F]{6}\Z")


def snapshot(json_dir: Path, now: float | None = None, state_file: Path | None = None) -> dict:
    now = time.time() if now is None else now
    aircraft = json.loads((json_dir / "aircraft.json").read_text(encoding="utf-8"))
    stats = json.loads((json_dir / "stats.json").read_text(encoding="utf-8"))
    aircraft_at = float(aircraft["now"])
    last15 = stats["last15min"]
    stats_at = float(last15["end"])
    if not 0 <= now - aircraft_at <= MAX_AIRCRAFT_AGE_SECONDS:
        raise ValueError("aircraft data is stale or dated in the future")
    if not 0 <= now - stats_at <= MAX_STATS_AGE_SECONDS:
        raise ValueError("receiver statistics are stale or dated in the future")

    recent = [item for item in aircraft["aircraft"]
              if 0 <= item.get("seen", float("inf")) <= 60
              and item.get("messages", 0) >= 2]
    positioned = sum(0 <= item.get("seen_pos", float("inf")) <= 60 for item in recent)
    messages = last15["messages"]
    if not isinstance(messages, int) or messages < 0:
        raise ValueError("invalid message count")

    result = {
        "schema_version": 1,
        "source": "dump1090-fa",
        "observed_at": datetime.fromtimestamp(aircraft_at, timezone.utc).isoformat().replace("+00:00", "Z"),
        "aircraft_seen_last_60_seconds": len(recent),
        "aircraft_with_positions_last_60_seconds": positioned,
        "messages_last_15_minutes": messages,
    }
    if state_file is not None:
        rolling = rolling_count(aircraft, aircraft_at, state_file)
        if rolling is not None and rolling >= len(recent):
            result["schema_version"] = 2
            result["aircraft_seen_last_30_minutes"] = rolling
    return result


def rolling_count(aircraft: dict, observed_at: float, state_file: Path) -> int | None:
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        if (state.get("version") != 1 or
                not 0 <= observed_at - state["updated_at"] <= MAX_POLL_GAP_SECONDS or
                not state["started_at"] <= state["updated_at"] or
                not isinstance(state["salt"], str) or len(state["salt"]) != 32 or
                not isinstance(state["aircraft"], dict)):
            raise ValueError("invalid rolling state")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        state = {"version": 1, "started_at": observed_at, "salt": secrets.token_hex(16), "aircraft": {}}

    cutoff = observed_at - WINDOW_SECONDS
    seen = {key: value for key, value in state["aircraft"].items()
            if isinstance(value, (int, float)) and cutoff < value <= observed_at}
    for item in aircraft["aircraft"]:
        aircraft_id = item.get("hex")
        age = item.get("seen")
        if (not isinstance(aircraft_id, str) or not AIRCRAFT_ID.fullmatch(aircraft_id) or
                not isinstance(age, (int, float)) or not 0 <= age <= MAX_POLL_GAP_SECONDS or
                item.get("messages", 0) < 2):
            continue
        last_heard = observed_at - age
        if last_heard <= cutoff:
            continue
        digest = hashlib.sha256(bytes.fromhex(state["salt"]) + aircraft_id.lower().encode("ascii")).hexdigest()
        seen[digest] = max(last_heard, seen.get(digest, 0))

    state["aircraft"] = seen
    state["updated_at"] = observed_at
    state_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=state_file.parent, prefix=".profile-adsb-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(state, stream, separators=(",", ":"))
        os.replace(temporary, state_file)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return len(seen) if observed_at - state["started_at"] >= WINDOW_SECONDS else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-dir", type=Path, default=DEFAULT_JSON_DIR)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    args = parser.parse_args()
    try:
        print(json.dumps(snapshot(args.json_dir, state_file=args.state_file), sort_keys=True, separators=(",", ":")))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"ADS-B snapshot unavailable: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
