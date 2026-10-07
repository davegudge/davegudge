import json
import tempfile
import unittest
from pathlib import Path

from adsb_snapshot import snapshot


class AdsbSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.aircraft = {
            "now": 1_000,
            "aircraft": [
                {"hex": "abc123", "flight": "PRIVATE", "lat": 51.5, "lon": -0.1,
                 "seen": 5, "seen_pos": 8, "messages": 4},
                {"hex": "def456", "seen": 20, "messages": 3},
                {"hex": "ghi789", "seen": 90, "messages": 40},
                {"hex": "jkl012", "seen": 2, "messages": 1},
            ],
        }
        self.stats = {"last15min": {"end": 980, "messages": 123_456},
                      "total": {"messages": 999_999_999}}
        self.write_inputs()

    def write_inputs(self):
        (self.path / "aircraft.json").write_text(json.dumps(self.aircraft))
        (self.path / "stats.json").write_text(json.dumps(self.stats))

    def test_exports_only_recent_aggregates(self):
        result = snapshot(self.path, now=1_010)
        self.assertEqual(2, result["aircraft_seen_last_60_seconds"])
        self.assertEqual(1, result["aircraft_with_positions_last_60_seconds"])
        self.assertEqual(123_456, result["messages_last_15_minutes"])
        self.assertNotIn("abc123", json.dumps(result))
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertNotIn("999999999", json.dumps(result))

    def test_rejects_stale_aircraft(self):
        with self.assertRaisesRegex(ValueError, "aircraft data is stale"):
            snapshot(self.path, now=1_121)

    def test_rejects_stale_statistics(self):
        self.stats["last15min"]["end"] = 800
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "receiver statistics are stale"):
            snapshot(self.path, now=1_010)

    def test_rolling_count_waits_for_complete_window_and_stores_hashes_only(self):
        state = self.path / "private/window.json"
        first = snapshot(self.path, now=1_010, state_file=state)
        self.assertEqual(1, first["schema_version"])
        saved = state.read_text()
        self.assertNotIn("abc123", saved)
        self.assertNotIn("def456", saved)
        self.assertNotIn("PRIVATE", saved)
        self.assertEqual(0o600, state.stat().st_mode & 0o777)

        self.aircraft["now"] = 2_800
        self.aircraft["aircraft"] = [{"hex": "abc123", "seen": 1, "messages": 4}]
        self.stats["last15min"]["end"] = 2_780
        self.write_inputs()
        # A long polling gap restarts warm-up rather than publishing an undercount.
        self.assertEqual(1, snapshot(self.path, now=2_810, state_file=state)["schema_version"])

        for observed_at in range(2_860, 4_601, 60):
            self.aircraft["now"] = observed_at
            self.stats["last15min"]["end"] = observed_at - 20
            self.write_inputs()
            result = snapshot(self.path, now=observed_at + 10, state_file=state)
        self.assertEqual(2, result["schema_version"])
        self.assertEqual(1, result["aircraft_seen_last_30_minutes"])


if __name__ == "__main__":
    unittest.main()
