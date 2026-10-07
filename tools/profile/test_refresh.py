import json
import io
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from refresh import fetch_json, main, refresh_source, validate_adsb, validate_smon


class RefreshTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "latest.json"
        self.now = datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc)
        self.adsb = {
            "schema_version": 1, "source": "dump1090-fa", "observed_at": "2026-10-05T19:59:00Z",
            "aircraft_seen_last_60_seconds": 42,
            "aircraft_with_positions_last_60_seconds": 37,
            "messages_last_15_minutes": 123_456,
        }

    def test_accepts_aggregate_and_preserves_it_after_failed_refresh(self):
        with patch("refresh.fetch_json", return_value=self.adsb):
            self.assertIn("updated", refresh_source("ADS-B", "https://example.test/feed", "token",
                                                     self.path, validate_adsb, self.now))
        saved = self.path.read_text()
        with patch("refresh.fetch_json", side_effect=OSError("feed down")):
            self.assertIn("keeping previous", refresh_source("ADS-B", "https://example.test/feed", "token",
                                                              self.path, validate_adsb, self.now))
        self.assertEqual(saved, self.path.read_text())

    def test_rejects_identifiers_and_old_snapshot(self):
        with self.assertRaisesRegex(ValueError, "schema"):
            validate_adsb(self.adsb | {"hex": "abc123"}, self.now)
        with self.assertRaisesRegex(ValueError, "timestamp"):
            validate_adsb(self.adsb | {"observed_at": "2026-10-05T19:40:00Z"}, self.now)

    def test_accepts_complete_30_minute_count(self):
        complete = self.adsb | {"schema_version": 2, "aircraft_seen_last_30_minutes": 180}
        validate_adsb(complete, self.now)
        with self.assertRaisesRegex(ValueError, "30-minute count"):
            validate_adsb(complete | {"aircraft_seen_last_30_minutes": 41}, self.now)

    def test_rejects_inconsistent_smon_counts(self):
        data = {"schema_version": 1, "generated_at": "2026-10-05T19:59:00Z",
                "instance": "current", "services_healthy": 3, "services_monitored": 2,
                "active_projects": 4, "successful_deployments_last_30_days": 1}
        with self.assertRaisesRegex(ValueError, "counts"):
            validate_smon(data, self.now)

    def test_accepts_extended_smon_aggregate(self):
        data = {"schema_version": 2, "generated_at": "2026-10-05T19:59:00Z",
                "instance": "current", "services_healthy": 3, "services_monitored": 3,
                "active_projects": 4, "successful_deployments_last_30_days": 1,
                "successful_deployments_total": 8, "monitoring_checks_last_24_hours": 600}
        validate_smon(data, self.now)
        with self.assertRaisesRegex(ValueError, "deployment counts"):
            validate_smon(data | {"successful_deployments_total": 0}, self.now)

    def test_feed_request_uses_named_client_signature(self):
        class Opener:
            def open(self, request, timeout):
                self.request = request
                return io.BytesIO(b'{"schema_version":1}')

        opener = Opener()
        with patch("refresh.urllib.request.build_opener", return_value=opener):
            self.assertEqual({"schema_version": 1}, fetch_json("https://example.test/feed", "token"))
        self.assertEqual("Bearer token", opener.request.get_header("Authorization"))
        self.assertTrue(opener.request.get_header("User-agent").startswith("profile-preview/1.0"))

    def test_scheduled_refresh_preserves_github_archive_even_with_token(self):
        data_dir = Path(self.directory.name)
        archived = data_dir / "github-preview.json"
        archived.write_text('{"frozen": true}\n')
        with patch.dict(os.environ, {"GITHUB_PROFILE_TOKEN": "token"}, clear=True), \
             patch("refresh.DATA_DIR", data_dir), \
             patch("refresh.sys.argv", ["refresh.py"]), \
             patch("refresh.fetch_json", side_effect=AssertionError("unexpected GitHub fetch")), \
             patch("refresh.subprocess.run"):
            self.assertEqual(0, main())
        self.assertEqual('{"frozen": true}\n', archived.read_text())

    def test_committed_github_snapshot_contains_aggregates_only(self):
        snapshot = json.loads((Path(__file__).parent / "data/github-preview.json").read_text())
        calendar = snapshot["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        self.assertEqual({"totalContributions"}, set(calendar))
        self.assertNotIn("contributionDays", json.dumps(snapshot))


if __name__ == "__main__":
    unittest.main()
