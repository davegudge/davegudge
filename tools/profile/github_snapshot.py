#!/usr/bin/env python3
"""Refresh post-archive GitHub monthly aggregates without requesting daily data."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta, timezone

from adsb_publish import NoRedirect, PROFILE_USER_AGENT
from gitlab_snapshot import CollectionError, month_after, month_range


START_DATE = "2026-10-07"
COUNTS = {"contributions", "commits", "pull_requests", "restricted_contributions"}
QUERY = """query ProfileActivity($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { totalContributions }
      totalCommitContributions
      totalPullRequestContributions(excludeFirst: false, excludePopular: false)
      restrictedContributionsCount
    }
  }
}"""


def empty_snapshot() -> dict:
    return {"schema_version": 1, "source": "github", "metric": "profile_contributions",
            "scope": "api_visible", "start_date": START_DATE, "timezone": "UTC",
            "through_month": None, "observed_at": None, "monthly": {}, "current_month": None}


def validate_snapshot(data: dict) -> None:
    if not isinstance(data, dict) or set(data) != set(empty_snapshot()) or \
            type(data["schema_version"]) is not int or data["schema_version"] != 1 or \
            any(data[key] != empty_snapshot()[key] for key in ("source", "metric", "scope", "start_date", "timezone")):
        raise ValueError("invalid recent GitHub aggregate schema")
    monthly, through, current = data["monthly"], data["through_month"], data["current_month"]
    if not isinstance(monthly, dict):
        raise ValueError("invalid recent GitHub months")
    if through is None:
        if monthly:
            raise ValueError("invalid recent GitHub coverage")
    elif not isinstance(through, str) or datetime.fromisoformat(through + "-01").strftime("%Y-%m") != through or \
            through < START_DATE[:7] or set(monthly) != set(month_range(START_DATE[:7], through)):
        raise ValueError("invalid recent GitHub coverage")
    records = list(monthly.values())
    if current is not None:
        if not isinstance(current, dict) or set(current) != COUNTS | {"month"} or \
                current["month"] != (month_after(through) if through else START_DATE[:7]):
            raise ValueError("overlapping or missing recent GitHub month")
        records.append({key:value for key,value in current.items() if key != "month"})
    for counts in records:
        if not isinstance(counts, dict) or set(counts) != COUNTS or \
                any(type(value) is not int or not 0 <= value <= 1_000_000_000 for value in counts.values()) or \
                any(counts[key] > counts["contributions"] for key in COUNTS - {"contributions"}):
            raise ValueError("invalid recent GitHub counts")
    if not monthly and current is None:
        if data["observed_at"] is not None:
            raise ValueError("pending recent GitHub aggregate has an observation")
        return
    observed = datetime.fromisoformat(data["observed_at"].replace("Z", "+00:00"))
    if observed.tzinfo is None:
        raise ValueError("invalid recent GitHub observation")
    observed_month = observed.astimezone(timezone.utc).strftime("%Y-%m")
    if (through and through >= observed_month) or (current and current["month"] != observed_month):
        raise ValueError("recent GitHub coverage does not match its observation")


class GitHubClient:
    def __init__(self, token: str):
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect)

    def counts(self, login: str, beginning: datetime, end: datetime) -> dict:
        payload = {"query": QUERY, "variables": {"login": login,
            "from": beginning.isoformat(), "to": end.isoformat()}}
        request = urllib.request.Request("https://api.github.com/graphql", data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + self.token, "Accept": "application/json",
                     "Content-Type": "application/json", "User-Agent": PROFILE_USER_AGENT}, method="POST")
        with self.opener.open(request, timeout=20) as response:
            data = json.load(response)
        if data.get("errors") or not data.get("data", {}).get("user"):
            raise CollectionError("GitHub returned an incomplete aggregate")
        collection = data["data"]["user"]["contributionsCollection"]
        return {"contributions": collection["contributionCalendar"]["totalContributions"],
                "commits": collection["totalCommitContributions"],
                "pull_requests": collection["totalPullRequestContributions"],
                "restricted_contributions": collection["restrictedContributionsCount"]}


def collect(token: str, login: str, previous: dict, archive: dict, now: datetime, client=None) -> dict:
    validate_snapshot(previous)
    # The original capture has a date, not a complete cutoff timestamp. Begin on
    # the following UTC day and display this period separately from the archive.
    if datetime.fromisoformat(archive["observed_at"]).date().isoformat() >= START_DATE:
        raise CollectionError("recent GitHub period overlaps the preserved archive")
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    if previous["observed_at"] and datetime.fromisoformat(previous["observed_at"].replace("Z", "+00:00")) > now:
        raise CollectionError("recent GitHub observation is in the future")
    current_month = now.strftime("%Y-%m")
    if previous["through_month"] and previous["through_month"] >= current_month:
        raise CollectionError("recent GitHub archive contains an unclosed month")
    client = client or GitHubClient(token)
    result = json.loads(json.dumps(previous))
    month = month_after(previous["through_month"]) if previous["through_month"] else START_DATE[:7]
    while month <= current_month:
        beginning = max(datetime.fromisoformat(month + "-01").replace(tzinfo=timezone.utc),
                        datetime.fromisoformat(START_DATE).replace(tzinfo=timezone.utc))
        following = datetime.fromisoformat(month_after(month) + "-01").replace(tzinfo=timezone.utc)
        is_current = month == current_month
        # GraphQL's to bound is inclusive. Whole seconds keep adjacent months
        # disjoint at midnight without relying on API fractional precision.
        end = now if is_current else following - timedelta(seconds=1)
        if end < beginning:
            raise CollectionError("recent GitHub start date is in the future")
        counts = client.counts(login, beginning, end)
        if is_current:
            result["current_month"] = {"month": month, **counts}
        else:
            result["monthly"][month] = counts
            result["through_month"] = month
        month = month_after(month)
    result["observed_at"] = now.isoformat().replace("+00:00", "Z")
    validate_snapshot(result)
    return result
