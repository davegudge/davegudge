import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

from render import render_history


class HistoryHighlightsTest(unittest.TestCase):
    def test_current_year_record_and_top_month_are_derived_from_history(self):
        months = {f"2025-{month:02d}": 100 for month in range(1, 13)}
        months.update({f"2026-{month:02d}": 110 for month in range(1, 11)})
        months["2026-03"] = 300
        history = {
            "schema_version": 1, "first_year": 2025, "last_year": 2026,
            "observed_at": "2026-10-06", "monthly": months,
            "total_contributions": sum(months.values()),
        }
        with tempfile.TemporaryDirectory() as directory, patch("render.OUT", Path(directory)):
            for mobile in (False, True):
                render_history(history, mobile)
                suffix = "-mobile" if mobile else ""
                root = ElementTree.parse(Path(directory) / f"contributions{suffix}.svg").getroot()
                labels = [element.text or "" for element in root.iter() if element.tag.endswith("text")]
                self.assertIn("1,290", labels)
                self.assertIn("300", labels)
                self.assertTrue(any("TOP MONTH · MAR 2026" in label for label in labels))
                self.assertTrue(any("TOP YEAR ·" in label for label in labels))


if __name__ == "__main__":
    unittest.main()
