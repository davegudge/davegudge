#!/usr/bin/env python3
"""Collect current-month and archived GitLab aggregates without publishing identities."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit
from zoneinfo import ZoneInfo

from adsb_publish import NoRedirect, PROFILE_USER_AGENT


METRIC = "authored_commits_on_integration_branch"
DEFAULT_START = "2026-10-12"
DEFAULT_TIMEZONE = "Europe/London"


class CollectionError(ValueError):
    """An incomplete collection must never replace a verified aggregate."""


def month_after(value: str) -> str:
    parsed = date.fromisoformat(value + "-01")
    return f"{parsed.year + (parsed.month == 12):04d}-{parsed.month % 12 + 1:02d}"


def month_range(start: str, end: str):
    while start <= end:
        yield start
        start = month_after(start)


def empty_snapshot(start: str = DEFAULT_START, zone: str = DEFAULT_TIMEZONE) -> dict:
    date.fromisoformat(start)
    ZoneInfo(zone)
    return {"schema_version": 2, "source": "gitlab", "metric": METRIC,
            "start_date": start, "timezone": zone, "through_month": None,
            "observed_at": None, "monthly": {}, "current_month": None}


def validate_snapshot(data: dict) -> None:
    expected = {"schema_version", "source", "metric", "start_date", "timezone",
                "through_month", "observed_at", "monthly"}
    if isinstance(data, dict) and data.get("schema_version") == 2:
        expected.add("current_month")
    if not isinstance(data, dict) or set(data) != expected or \
            type(data["schema_version"]) is not int or data["schema_version"] not in (1, 2) or \
            data["source"] != "gitlab" or data["metric"] != METRIC:
        raise ValueError("invalid GitLab aggregate schema")
    start = date.fromisoformat(data["start_date"])
    if start.isoformat() != data["start_date"]:
        raise ValueError("invalid GitLab start date")
    zone = ZoneInfo(data["timezone"])
    monthly, through = data["monthly"], data["through_month"]
    if not isinstance(monthly, dict):
        raise ValueError("invalid GitLab months")
    if through is None:
        if monthly:
            raise ValueError("invalid GitLab coverage")
    elif not isinstance(through, str) or date.fromisoformat(through + "-01").strftime("%Y-%m") != through or \
            through < data["start_date"][:7] or \
            set(monthly) != set(month_range(data["start_date"][:7], through)):
        raise ValueError("invalid GitLab coverage")
    current = data.get("current_month")
    records = list(monthly.values())
    if current is not None:
        if not isinstance(current, dict) or set(current) != {"month", "commits", "merge_commits"}:
            raise ValueError("invalid GitLab current month")
        if current["month"] != (month_after(through) if through else data["start_date"][:7]):
            raise ValueError("overlapping or missing GitLab month")
        records.append({key: value for key, value in current.items() if key != "month"})
    for counts in records:
        if not isinstance(counts, dict) or set(counts) != {"commits", "merge_commits"} or \
                any(type(value) is not int or not 0 <= value <= 1_000_000_000 for value in counts.values()) or \
                counts["merge_commits"] > counts["commits"]:
            raise ValueError("invalid GitLab counts")
    if not monthly and current is None:
        if data["observed_at"] is not None:
            raise ValueError("pending GitLab aggregate has an observation")
        return
    observed = datetime.fromisoformat(data["observed_at"].replace("Z", "+00:00"))
    if observed.tzinfo is None:
        raise ValueError("invalid GitLab observation")
    observed_month = observed.astimezone(zone).strftime("%Y-%m")
    if (through and through >= observed_month) or (current and current["month"] != observed_month):
        raise ValueError("GitLab coverage does not match its observation")


def load_config(path: Path | None = None) -> dict | None:
    if path is not None:
        config = json.loads(path.read_text(encoding="utf-8"))
    else:
        token, url = os.getenv("GITLAB_PROFILE_TOKEN", ""), os.getenv("GITLAB_PROFILE_URL", "")
        if not token and not url:
            return None
        config = {
            "token": token, "base_url": url,
            "start_date": os.getenv("GITLAB_PROFILE_START_DATE") or DEFAULT_START,
            "timezone": os.getenv("GITLAB_PROFILE_TIMEZONE") or DEFAULT_TIMEZONE,
            "branch": os.getenv("GITLAB_PROFILE_BRANCH") or "develop",
            "username": os.getenv("GITLAB_PROFILE_USERNAME", ""),
            "author_emails": [email.strip() for email in os.getenv("GITLAB_PROFILE_AUTHOR_EMAILS", "").split(",") if email.strip()],
            "project_ids": json.loads(os.getenv("GITLAB_PROFILE_PROJECT_IDS") or "[]"),
        }
    for key in ("base_url", "token", "start_date", "timezone", "branch"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise CollectionError("incomplete GitLab configuration")
    config = dict(config)
    config["base_url"] = config["base_url"].rstrip("/")
    parts = urlsplit(config["base_url"])
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise CollectionError("GitLab URL must be a plain HTTPS instance URL")
    empty_snapshot(config["start_date"], config["timezone"])
    project_ids = config.get("project_ids", [])
    if not isinstance(project_ids, list) or any(type(value) is not int or value <= 0 for value in project_ids):
        raise CollectionError("invalid project selection")
    emails = config.get("author_emails", [])
    if not isinstance(emails, list) or any(not isinstance(email, str) or "@" not in email for email in emails):
        raise CollectionError("invalid author selection")
    return config


class GitLabClient:
    def __init__(self, config: dict):
        self.base_url = config["base_url"] + "/api/v4"
        self.token = config["token"].strip()
        self.opener = urllib.request.build_opener(NoRedirect)

    def get(self, path: str, params: dict | None = None):
        url = self.base_url + path + ("?" + urlencode(params) if params else "")
        request = urllib.request.Request(url, headers={
            "PRIVATE-TOKEN": self.token, "Accept": "application/json", "User-Agent": PROFILE_USER_AGENT,
        })
        with self.opener.open(request, timeout=20) as response:
            return json.load(response), response.headers

    def pages(self, path: str, params: dict | None = None):
        for page in range(1, 1001):
            batch, headers = self.get(path, {**(params or {}), "page": page, "per_page": 100})
            if not isinstance(batch, list):
                raise CollectionError("invalid paginated response")
            yield from batch
            following = headers.get("X-Next-Page")
            if following and int(following) != page + 1:
                raise CollectionError("invalid pagination")
            if not following and len(batch) < 100:
                return
        raise CollectionError("pagination limit exceeded")


def collect(config: dict, previous: dict, now: datetime, client=None) -> dict:
    validate_snapshot(previous)
    if previous["start_date"] != config["start_date"] or previous["timezone"] != config["timezone"]:
        raise CollectionError("GitLab coverage changed; review required")
    client = client or GitLabClient(config)
    user, _ = client.get("/user")
    if not isinstance(user.get("id"), int) or not user.get("username") or \
            (config.get("username") and user["username"] != config["username"]):
        raise CollectionError("GitLab account mismatch")
    emails = {email.casefold() for email in config.get("author_emails", [])}
    if not emails:
        primary = user.get("email")
        if not isinstance(primary, str) or "@" not in primary:
            raise CollectionError("configure author emails explicitly")
        emails = {primary.casefold()}
    zone = ZoneInfo(config["timezone"])
    current_month = now.astimezone(zone).strftime("%Y-%m")
    if previous["observed_at"] and datetime.fromisoformat(previous["observed_at"].replace("Z", "+00:00")) > now:
        raise CollectionError("GitLab archive observation is in the future")
    next_month = month_after(previous["through_month"]) if previous["through_month"] else config["start_date"][:7]
    if previous["through_month"] and previous["through_month"] >= current_month:
        raise CollectionError("GitLab archive contains an unclosed month")
    selected = config.get("project_ids", [])
    if selected:
        projects = []
        for project_id in sorted(set(selected)):
            project, _ = client.get(f"/projects/{project_id}")
            projects.append(project)
    else:
        projects = list(client.pages("/projects", {"membership": "true", "simple": "true"}))
    if not projects:
        raise CollectionError("no readable membership projects")
    project_ids = set()
    for project in projects:
        project_id = project.get("id")
        if type(project_id) is not int or project_id <= 0:
            raise CollectionError("invalid project response")
        try:
            client.get(f"/projects/{project_id}/repository/branches/" + quote(config["branch"], safe=""))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                if selected:
                    raise CollectionError("selected project has no readable integration branch") from None
                continue
            raise
        project_ids.add(project_id)
    if not project_ids:
        raise CollectionError("no readable integration branches")
    result = json.loads(json.dumps(previous))
    result["schema_version"] = 2
    result["current_month"] = None
    while next_month <= current_month:
        beginning = max(date.fromisoformat(next_month + "-01"), date.fromisoformat(config["start_date"]))
        following = month_after(next_month)
        lower = datetime.combine(beginning, datetime.min.time(), zone).astimezone(timezone.utc)
        upper = datetime.combine(date.fromisoformat(following + "-01"), datetime.min.time(), zone).astimezone(timezone.utc)
        is_current = next_month == current_month
        if is_current:
            upper = now.astimezone(timezone.utc)
        if lower > upper:
            raise CollectionError("GitLab start date is in the future")
        commits = {}
        for project_id in sorted(project_ids):
            for commit in client.pages(f"/projects/{project_id}/repository/commits", {
                "ref_name": config["branch"], "since": lower.isoformat(), "until": upper.isoformat(),
            }):
                if str(commit.get("author_email", "")).casefold() not in emails:
                    continue
                committed = datetime.fromisoformat(commit["committed_date"].replace("Z", "+00:00"))
                if committed.tzinfo is None:
                    raise CollectionError("commit timestamp is missing its timezone")
                if lower <= committed < upper or (is_current and committed == upper):
                    sha, parents = commit["id"], commit["parent_ids"]
                    if not isinstance(sha, str) or len(sha) not in (40, 64) or any(c not in "0123456789abcdef" for c in sha) or \
                            not isinstance(parents, list) or any(not isinstance(p, str) for p in parents):
                        raise CollectionError("invalid commit response")
                    is_merge = len(parents) > 1
                    if sha in commits and commits[sha] != is_merge:
                        raise CollectionError("conflicting duplicate commit")
                    commits[sha] = is_merge
        counts = {"commits": len(commits), "merge_commits": sum(commits.values())}
        if is_current:
            result["current_month"] = {"month": next_month, **counts}
        else:
            result["monthly"][next_month] = counts
            result["through_month"] = next_month
        next_month = following
    result["observed_at"] = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    validate_snapshot(result)
    return result
