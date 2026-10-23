"""Collect rolling cross-service aggregates; daily activity exists only in memory."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

from adsb_publish import NoRedirect, PROFILE_USER_AGENT
from gitlab_snapshot import CollectionError, GitLabClient

QUERY = '''query ProfileSignal($login: String!, $from: DateTime!, $to: DateTime!, $opened: String!, $merged: String!) {
  user(login: $login) { contributionsCollection(from: $from, to: $to) {
    contributionCalendar { weeks { contributionDays { date contributionCount } } }
  } }
  opened: search(query: $opened, type: ISSUE, first: 1) { issueCount }
  merged: search(query: $merged, type: ISSUE, first: 1) { issueCount }
}'''
KEYS = {"schema_version", "observed_at", "window_start", "timezone", "contributions", "pull_requests", "merged_prs", "streak_days", "streak_lower_bound"}


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise CollectionError("activity timestamp lacks timezone")
    return result.astimezone(timezone.utc)


def integer(value):
    if type(value) is not int or not 0 <= value <= 1_000_000_000:
        raise CollectionError("invalid activity count")
    return value


def validate_snapshot(data):
    if not isinstance(data, dict) or set(data) != KEYS or data["schema_version"] != 1 or data["timezone"] != "UTC":
        raise ValueError("invalid rolling aggregate schema")
    now = instant(data["observed_at"])
    start = instant(data["window_start"])
    if start != now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=29):
        raise ValueError("invalid rolling window")
    for key in ("contributions", "pull_requests", "merged_prs", "streak_days"):
        integer(data[key])
    if type(data["streak_lower_bound"]) is not bool or data["streak_days"] > 365 or (data["streak_lower_bound"] and data["streak_days"] < 364):
        raise ValueError("invalid streak")


def github_activity(token, login, beginning, window, now):
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", login):
        raise CollectionError("invalid GitHub login")
    span = window.isoformat() + ".." + now.isoformat()
    variables = {"login": login, "from": beginning.isoformat(), "to": now.isoformat(),
                 "opened": f"author:{login} is:pr created:{span}",
                 "merged": f"author:{login} is:pr is:merged merged:{span}"}
    request = urllib.request.Request("https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", "User-Agent": PROFILE_USER_AGENT}, method="POST")
    with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors") or not payload.get("data", {}).get("user"):
        raise CollectionError("incomplete rolling GitHub response")
    data = payload["data"]
    days = {}
    for week in data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
        for day in week["contributionDays"]:
            date = datetime.strptime(day["date"], "%Y-%m-%d").date()
            if beginning.date() <= date <= now.date():
                if date in days:
                    raise CollectionError("duplicate GitHub activity day")
                days[date] = integer(day["contributionCount"])
    expected = {beginning.date() + timedelta(days=n) for n in range((now.date() - beginning.date()).days + 1)}
    if set(days) != expected:
        raise CollectionError("incomplete GitHub activity calendar")
    return days, integer(data["opened"]["issueCount"]), integer(data["merged"]["issueCount"])


def gitlab_activity(config, beginning, window, now, client=None):
    client = client or GitLabClient(config)
    user, _ = client.get("/user")
    if type(user.get("id")) is not int or (config.get("username") and user.get("username") != config["username"]):
        raise CollectionError("GitLab account mismatch")
    emails = {value.casefold() for value in config.get("author_emails", [])}
    if not emails:
        if not isinstance(user.get("email"), str) or "@" not in user["email"]:
            raise CollectionError("missing author email")
        emails = {user["email"].casefold()}
    selected = config.get("project_ids", [])
    projects = [client.get(f"/projects/{pid}")[0] for pid in sorted(set(selected))] if selected else list(client.pages("/projects", {"membership": "true", "simple": "true"}))
    ids = set()
    for project in projects:
        pid = project["id"]
        if type(pid) is not int or pid <= 0:
            raise CollectionError("invalid project")
        try:
            client.get(f"/projects/{pid}/repository/branches/" + quote(config["branch"], safe=""))
        except urllib.error.HTTPError as error:
            if error.code == 404 and not selected:
                continue
            raise
        ids.add(pid)
    if not ids:
        raise CollectionError("no readable integration branches")
    employment_start = datetime.fromisoformat(config["start_date"]).replace(tzinfo=ZoneInfo(config["timezone"])).astimezone(timezone.utc)
    lower = max(beginning, employment_start)
    if lower > now:
        raise CollectionError("GitLab start is in the future")
    commits = {}
    for pid in sorted(ids):
        for commit in client.pages(f"/projects/{pid}/repository/commits", {"ref_name": config["branch"], "since": lower.isoformat(), "until": now.isoformat()}):
            if str(commit.get("author_email", "")).casefold() not in emails:
                continue
            timestamp = instant(commit["committed_date"])
            if lower <= timestamp <= now:
                sha = commit["id"]
                if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha):
                    raise CollectionError("invalid commit identity")
                if sha in commits and commits[sha] != timestamp:
                    raise CollectionError("inconsistent duplicate commit")
                commits[sha] = timestamp
    days = {}
    for timestamp in commits.values():
        days[timestamp.date()] = days.get(timestamp.date(), 0) + 1
    mr_lower = max(window, employment_start)
    common = {"scope": "all", "author_id": user["id"]}
    def count_mrs(state, bound, field):
        seen = set()
        for mr in client.pages("/merge_requests", {**common, "state": state, **bound}):
            if mr.get("project_id") not in ids or mr.get("author", {}).get("id") != user["id"]:
                continue
            if field == "merged_at" and mr.get("state") != "merged":
                continue
            timestamp = instant(mr[field]) if mr.get(field) else None
            if timestamp and mr_lower <= timestamp <= now:
                seen.add(integer(mr["id"]))
        return len(seen)
    opened = count_mrs("all", {"created_after": mr_lower.isoformat(), "created_before": now.isoformat()}, "created_at")
    # A request created before the window can still be merged inside it.
    merged = count_mrs("merged", {"updated_after": mr_lower.isoformat()}, "merged_at")
    return days, opened, merged


def collect(token, login, config, now, github_reader=github_activity, gitlab_reader=gitlab_activity):
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    midnight = now.replace(hour=0, minute=0, second=0)
    window = midnight - timedelta(days=29)
    beginning = midnight - timedelta(days=364)
    gh, gh_opened, gh_merged = github_reader(token, login, beginning, window, now)
    gl, gl_opened, gl_merged = gitlab_reader(config, beginning, window, now)
    active = {day for source in (gh, gl) for day, count in source.items() if count > 0}
    cursor = now.date() if now.date() in active else now.date() - timedelta(days=1)
    streak = 0
    while cursor >= beginning.date() and cursor in active:
        streak += 1
        cursor -= timedelta(days=1)
    result = {"schema_version": 1, "observed_at": now.isoformat().replace("+00:00", "Z"),
              "window_start": window.isoformat().replace("+00:00", "Z"), "timezone": "UTC",
              "contributions": sum(count for source in (gh, gl) for day, count in source.items() if window.date() <= day <= now.date()),
              "pull_requests": gh_opened + gl_opened, "merged_prs": gh_merged + gl_merged,
              "streak_days": streak, "streak_lower_bound": cursor < beginning.date()}
    validate_snapshot(result)
    return result
