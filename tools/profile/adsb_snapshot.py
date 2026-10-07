#!/usr/bin/env python3
"""Export safe aggregate telemetry from a local dump1090-fa receiver."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_JSON_DIR = Path("/run/dump1090-fa")
MAX_AIRCRAFT_AGE_SECONDS = 120
MAX_STATS_AGE_SECONDS = 180


def snapshot(json_dir: Path, now: float | None = None) -> dict:
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

    return {
        "schema_version": 1,
        "source": "dump1090-fa",
        "observed_at": datetime.fromtimestamp(aircraft_at, timezone.utc).isoformat().replace("+00:00", "Z"),
        "aircraft_seen_last_60_seconds": len(recent),
        "aircraft_with_positions_last_60_seconds": positioned,
        "messages_last_15_minutes": messages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-dir", type=Path, default=DEFAULT_JSON_DIR)
    args = parser.parse_args()
    try:
        print(json.dumps(snapshot(args.json_dir), sort_keys=True, separators=(",", ":")))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"ADS-B snapshot unavailable: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
