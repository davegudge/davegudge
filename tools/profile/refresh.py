#!/usr/bin/env python3
"""Refresh verified profile snapshots and render the profile images."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from adsb_publish import NoRedirect, PROFILE_USER_AGENT
from gitlab_snapshot import collect, empty_snapshot, load_config, validate_snapshot
from github_snapshot import collect as collect_github, empty_snapshot as empty_github_snapshot
from signal_snapshot import collect as collect_signal


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "tools" / "profile" / "data"


def timestamp(value: str, now: datetime, max_age: timedelta) -> None:
    observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if observed.tzinfo is None or not -timedelta(seconds=30) <= now - observed <= max_age:
        raise ValueError("snapshot timestamp is outside the accepted window")


def nonnegative_int(value: object) -> bool:
    return type(value) is int and 0 <= value <= 1_000_000_000


def validate_smon(data: dict, now: datetime) -> None:
    expected = {"schema_version", "generated_at", "instance", "services_healthy",
                "services_monitored", "active_projects", "successful_deployments_last_30_days"}
    version = data.get("schema_version")
    if version == 2:
        expected |= {"successful_deployments_total", "monitoring_checks_last_24_hours"}
    if set(data) != expected or version not in (1, 2) or data["instance"] != "current":
        raise ValueError("unexpected SMON summary schema")
    timestamp(data["generated_at"], now, timedelta(minutes=10))
    counts = [data[key] for key in expected - {"schema_version", "generated_at", "instance"}]
    if not all(nonnegative_int(value) for value in counts) or data["services_healthy"] > data["services_monitored"]:
        raise ValueError("invalid SMON counts")
    if version == 2 and data["successful_deployments_total"] < data["successful_deployments_last_30_days"]:
        raise ValueError("invalid SMON deployment counts")


def validate_adsb(data: dict, now: datetime) -> None:
    expected = {"schema_version", "source", "observed_at", "aircraft_seen_last_60_seconds",
                "aircraft_with_positions_last_60_seconds", "messages_last_15_minutes"}
    version = data.get("schema_version")
    if version == 2:
        expected.add("aircraft_seen_last_30_minutes")
    if set(data) != expected or version not in (1, 2) or data["source"] != "dump1090-fa":
        raise ValueError("unexpected ADS-B summary schema")
    timestamp(data["observed_at"], now, timedelta(minutes=15))
    counts = [data[key] for key in expected - {"schema_version", "source", "observed_at"}]
    if not all(nonnegative_int(value) for value in counts) or \
            data["aircraft_with_positions_last_60_seconds"] > data["aircraft_seen_last_60_seconds"]:
        raise ValueError("invalid ADS-B counts")
    if version == 2 and data["aircraft_seen_last_30_minutes"] < data["aircraft_seen_last_60_seconds"]:
        raise ValueError("30-minute count is below 60-second count")


def fetch_json(url: str, token: str, body: dict | None = None) -> dict:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("feed URL must be a plain HTTPS endpoint")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json",
               "User-Agent": PROFILE_USER_AGENT}
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=payload, headers=headers,
                                     method="POST" if payload is not None else "GET")
    with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
        return json.load(response)


def write_if_changed(path: Path, data: dict) -> bool:
    encoded = json.dumps(data, sort_keys=True, indent=2) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == encoded:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)
    return True


def refresh_source(name: str, url: str | None, token: str | None, path: Path,
                   validator, now: datetime) -> str:
    if not url or not token:
        return f"{name}: no feed configured; keeping previous snapshot"
    try:
        data = fetch_json(url, token)
        validator(data, now)
        changed = write_if_changed(path, data)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return f"{name}: refresh failed ({type(error).__name__}); keeping previous snapshot"
    return f"{name}: {'updated' if changed else 'unchanged'}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-only", action="store_true", help="render saved snapshots without network access")
    parser.add_argument("--gitlab-config", type=Path, help="ignored local GitLab configuration; Actions uses environment variables")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    activity_failed = False
    if not args.render_only:
        print("GitHub: preserving dated contribution and language snapshots")
        github_token = os.getenv("GITHUB_PROFILE_TOKEN") or os.getenv("GITHUB_ACTIVITY_TOKEN")
        if github_token:
            try:
                recent_path = DATA_DIR / "github-recent.json"
                previous_github = json.loads(recent_path.read_text()) if recent_path.is_file() else empty_github_snapshot()
                archive = json.loads((DATA_DIR / "github-history.json").read_text())
                recent = collect_github(github_token, os.getenv("GITHUB_PROFILE_LOGIN") or "davegudge",
                                        previous_github, archive, now)
                changed = write_if_changed(recent_path, recent)
                print(f"GitHub: recent monthly aggregates {'updated' if changed else 'unchanged'}; archive preserved")
            except Exception as error:
                print(f"GitHub: recent refresh failed ({type(error).__name__}); preserving previous aggregate")
                activity_failed = True
        else:
            print("GitHub: recent source not configured; preserving previous aggregate")
        config = None
        path = DATA_DIR / "gitlab-history.json"
        try:
            config = load_config(args.gitlab_config)
            if config is None:
                print("GitLab: not configured; preserving previous aggregate")
            else:
                previous = json.loads(path.read_text()) if path.is_file() else empty_snapshot(config["start_date"], config["timezone"])
                validate_snapshot(previous)
                changed = write_if_changed(path, collect(config, previous, now))
                print(f"GitLab: monthly aggregates {'updated' if changed else 'unchanged'}; current month included")
        except Exception as error:
            # API errors may contain employer hostnames, messages and credentials.
            print(f"GitLab: refresh failed ({type(error).__name__}); preserving previous archive")
            activity_failed = True
        if github_token and config is not None:
            try:
                signal = collect_signal(github_token, os.getenv("GITHUB_PROFILE_LOGIN") or "davegudge", config, now)
                changed = write_if_changed(DATA_DIR / "git-signal.json", signal)
                print(f"Git Signal: rolling aggregates {'updated' if changed else 'unchanged'}")
            except Exception as error:
                print(f"Git Signal: refresh failed ({type(error).__name__}); preserving previous aggregate")
                activity_failed = True
        else:
            print("Git Signal: both sources required; preserving previous aggregate")
        print(refresh_source("SMON", os.getenv("SMON_PROFILE_STATS_URL"),
                             os.getenv("SMON_PROFILE_STATS_TOKEN"), DATA_DIR / "smon-latest.json",
                             validate_smon, now))
        print(refresh_source("ADS-B", os.getenv("ADSB_PROFILE_STATS_URL"),
                             os.getenv("SMON_PROFILE_STATS_TOKEN"), DATA_DIR / "adsb-latest.json",
                             validate_adsb, now))
    subprocess.run([sys.executable, str(ROOT / "tools/profile/render.py")], check=True)
    return 1 if activity_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
