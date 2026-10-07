#!/usr/bin/env python3
"""Push a safe dump1090 aggregate from the receiver to SMON over HTTPS."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from adsb_snapshot import DEFAULT_JSON_DIR, DEFAULT_STATE_FILE, snapshot

PROFILE_USER_AGENT = "profile-preview/1.0 (+https://github.com/davegudge/profile-preview)"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def publish(url: str, token: str, payload: dict) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("publish URL must be a plain HTTPS endpoint")
    if not token:
        raise ValueError("missing ingest token")
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "User-Agent": PROFILE_USER_AGENT},
    )
    with urllib.request.build_opener(NoRedirect).open(request, timeout=15) as response:
        if response.status != 204:
            raise ValueError(f"unexpected response status {response.status}")


def main() -> int:
    try:
        publish(
            os.environ["SMON_PROFILE_ADSB_URL"],
            os.environ["SMON_PROFILE_ADSB_INGEST_TOKEN"],
            snapshot(DEFAULT_JSON_DIR, state_file=DEFAULT_STATE_FILE),
        )
    except (KeyError, OSError, ValueError, urllib.error.URLError) as error:
        print(f"ADS-B publish failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
