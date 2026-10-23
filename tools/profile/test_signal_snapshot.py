import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from signal_snapshot import collect, gitlab_activity, github_activity, validate_snapshot, CollectionError

NOW = datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc)
CONFIG = {"base_url": "https://example.test", "token": "secret", "username": "Dave", "author_emails": ["dave@example.test"], "branch": "develop", "start_date": "2026-10-12", "timezone": "Europe/London"}


class SignalTest(unittest.TestCase):
    def snapshot(self, gh, gl, opened=(2, 3), merged=(4, 5)):
        return collect("secret", "davegudge", CONFIG, NOW,
            github_reader=lambda *args: (gh, opened[0], merged[0]),
            gitlab_reader=lambda *args: (gl, opened[1], merged[1]))

    def test_direct_rolling_counts_and_cross_provider_streak(self):
        today = NOW.date()
        result = self.snapshot({today: 3, today-timedelta(days=2): 4, today-timedelta(days=29): 10, today-timedelta(days=30): 100},
                               {today: 2, today-timedelta(days=1): 1})
        self.assertEqual(20, result["contributions"])
        self.assertEqual(5, result["pull_requests"])
        self.assertEqual(9, result["merged_prs"])
        self.assertEqual(3, result["streak_days"])
        self.assertFalse(result["streak_lower_bound"])
        self.assertEqual("2026-09-24T00:00:00Z", result["window_start"])
        for private in ("secret", "example.test", "contributionDays", "author", "project", "daily"):
            self.assertNotIn(private, json.dumps(result))

    def test_streak_can_end_yesterday_and_stops_at_gap(self):
        yesterday = NOW.date()-timedelta(days=1)
        self.assertEqual(2, self.snapshot({yesterday: 1}, {yesterday-timedelta(days=1): 1, yesterday-timedelta(days=3): 1})["streak_days"])
        self.assertEqual(0, self.snapshot({}, {})["streak_days"])

    def test_long_streak_has_honest_lower_bound(self):
        result = self.snapshot({NOW.date()-timedelta(days=n): 1 for n in range(365)}, {})
        self.assertEqual(365, result["streak_days"])
        self.assertTrue(result["streak_lower_bound"])

    def test_rejects_daily_data_or_invalid_window(self):
        result = self.snapshot({}, {})
        with self.assertRaises(ValueError): validate_snapshot({**result, "daily": []})
        with self.assertRaises(ValueError): validate_snapshot({**result, "window_start": "2026-09-23T00:00:00Z"})

    def test_failure_does_not_return_partial_total(self):
        def fail(*args): raise OSError("secret private response")
        with self.assertRaises(OSError): collect("secret", "davegudge", CONFIG, NOW, github_reader=fail)

    def test_gitlab_dedup_authorship_merge_dates_and_project_scope(self):
        class Client:
            def get(self, path):
                return ({"id": 7, "username": "Dave"} if path == "/user" else {}, {})
            def pages(self, path, params):
                if path == "/projects": return [{"id": 11}, {"id": 12}]
                if "commits" in path:
                    return [{"id": "a"*40, "committed_date": "2026-10-22T12:00:00Z", "author_email": "DAVE@example.test"},
                            {"id": "b"*40, "committed_date": "2026-10-22T12:00:00Z", "author_email": "someone@example.test"}]
                base = {"id": 1, "project_id": 11, "author": {"id": 7}, "state": "merged", "created_at": "2026-09-01T12:00:00Z", "merged_at": "2026-10-22T12:00:00Z"}
                if params["state"] == "merged":
                    assert "created_after" not in params
                    return [base, base, {**base, "id": 2, "merged_at": "2026-09-01T12:00:00Z"}, {**base, "id": 3, "project_id": 999}, {**base, "id": 4, "author": {"id": 8}}]
                return [base, {**base, "id": 5, "created_at": "2026-10-23T12:00:00Z"}]
        days, opened, merged = gitlab_activity(CONFIG, NOW-timedelta(days=364), NOW-timedelta(days=29), NOW, Client())
        self.assertEqual({datetime(2026, 10, 22).date(): 1}, days)
        self.assertEqual((1, 1), (opened, merged))

    def test_github_calendar_and_search_are_complete_and_exact(self):
        beginning = NOW.replace(hour=0)-timedelta(days=2)
        calendar = [{"date": (beginning+timedelta(days=n)).date().isoformat(), "contributionCount": n} for n in range(3)]
        payload = {"data": {"user": {"contributionsCollection": {"contributionCalendar": {"weeks": [{"contributionDays": calendar}]}}}, "opened": {"issueCount": 2}, "merged": {"issueCount": 3}}}
        class Opener:
            def open(self, request, timeout):
                self.request = json.loads(request.data)
                return io.BytesIO(json.dumps(payload).encode())
        opener = Opener()
        with patch("signal_snapshot.urllib.request.build_opener", return_value=opener):
            days, opened, merged = github_activity("secret", "davegudge", beginning, beginning, NOW)
            self.assertEqual((3, 2, 3), (sum(days.values()), opened, merged))
            self.assertIn("is:merged merged:", opener.request["variables"]["merged"])
            self.assertNotIn("created:", opener.request["variables"]["merged"])
            calendar.pop()
            with self.assertRaises(CollectionError): github_activity("secret", "davegudge", beginning, beginning, NOW)
            payload["errors"] = [{"message": "private"}]
            with self.assertRaises(CollectionError): github_activity("secret", "davegudge", beginning, beginning, NOW)


if __name__ == "__main__": unittest.main()
