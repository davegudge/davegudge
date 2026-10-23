import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

from render import render_history
from gitlab_snapshot import empty_snapshot


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


class UnifiedActivityTest(unittest.TestCase):
    def setUp(self):
        import copy, json
        self.archive=json.loads((Path(__file__).parent/"data/github-history.json").read_text())
        self.original=copy.deepcopy(self.archive)
        from github_snapshot import empty_snapshot as github_empty
        self.github=github_empty() | {"observed_at":"2026-10-23T12:00:00Z","current_month":{
            "month":"2026-10","contributions":162,"commits":12,"pull_requests":1,"restricted_contributions":149}}
        self.gitlab=empty_snapshot() | {"observed_at":"2026-10-23T12:00:01Z","current_month":{
            "month":"2026-10","commits":6,"merge_commits":3}}
        self.now=datetime(2026,10,23,12,30,tzinfo=timezone.utc)

    def merged(self):
        from render import merge_activity_history
        return merge_activity_history(self.archive,self.github,self.gitlab,self.now)

    def labels(self,data,mobile,kind="stats",signal=None):
        from render import render_stats
        with tempfile.TemporaryDirectory() as directory,patch("render.OUT",Path(directory)):
            function=render_stats if kind=="stats" else render_history
            function(data,mobile,signal=signal) if kind=="stats" else function(data,mobile)
            name="stats" if kind=="stats" else "contributions"
            path=Path(directory)/(name+("-mobile" if mobile else "")+".svg")
            root=ElementTree.parse(path).getroot()
            return [element.text or "" for element in root.iter() if element.tag.endswith("text")],root

    def test_new_activity_extends_the_same_month_and_preserves_all_earlier_months(self):
        data=self.merged()
        self.assertEqual(self.original,self.archive)
        self.assertEqual(106+162+6,data["monthly"]["2026-10"])
        self.assertEqual(39022+162+6,data["total_contributions"])
        for month,count in self.archive["monthly"].items():
            if month<"2026-10":self.assertEqual(count,data["monthly"][month])
        self.assertEqual(268,data["source_monthly"]["github"]["2026-10"])
        self.assertEqual(6,data["source_monthly"]["gitlab"]["2026-10"])
        self.assertEqual(3,data["source_monthly"]["gitlab_merges"]["2026-10"])

    def test_repeated_render_does_not_accumulate_counts_or_count_merges_twice(self):
        first=self.merged();second=self.merged()
        self.assertEqual(first,second)
        self.assertEqual(274,first["monthly"]["2026-10"])
        self.assertEqual(39190,first["total_contributions"])

    def test_compact_signal_has_one_timestamp_and_no_explanatory_footer(self):
        data=self.merged()
        for mobile in (False,True):
            signal={"schema_version":1,"observed_at":"2026-10-23T12:00:00Z","window_start":"2026-09-24T00:00:00Z","timezone":"UTC","contributions":220,"pull_requests":7,"merged_prs":9,"streak_days":3,"streak_lower_bound":False}
            labels,root=self.labels(data,mobile,signal=signal)
            self.assertIn("01 // GIT SIGNAL",labels)
            for value in ("220","7","9","3d","CONTRIBUTIONS / 30D","PULL REQUESTS / 30D","MERGED PRS / 30D","STREAK"):self.assertIn(value,labels)
            self.assertFalse(any("GITLAB MERGES" in label or "/ MONTH" in label for label in labels))
            self.assertEqual(1,sum("AS OF" in label for label in labels))
            for forbidden in ("Since ","Partial month","API-visible","Visible PRs","shared private","Integration branch","Snapshot:"):
                self.assertFalse(any(forbidden in label for label in labels))
            self.assertIn("GitLab",root.attrib["aria-label"])

    def test_existing_history_chart_includes_fresh_totals_and_year_highlight(self):
        data=self.merged()
        for mobile in (False,True):
            labels,root=self.labels(data,mobile,"history")
            self.assertIn("39,190 CONTRIBUTIONS",labels)
            self.assertIn("3,852",labels)
            self.assertIn("737",labels)
            self.assertEqual(1,sum("AS OF" in label for label in labels))
            self.assertFalse(any("ARCHIVE" in label for label in labels))
            self.assertIn("GitLab",root.attrib["aria-label"])
            self.assertIn("2007",root.attrib["aria-label"])

    def test_rollover_keeps_frozen_months_and_current_month_disjoint(self):
        from render import merge_activity_history
        self.github["monthly"]={"2026-10":{key:value for key,value in self.github["current_month"].items() if key!="month"}}
        self.github.update(through_month="2026-10",observed_at="2026-11-01T00:30:00Z",current_month={
            "month":"2026-11","contributions":5,"commits":3,"pull_requests":1,"restricted_contributions":1})
        self.gitlab.update(through_month="2026-10",observed_at="2026-11-01T00:30:00Z",
            monthly={"2026-10":{"commits":6,"merge_commits":3}},current_month={"month":"2026-11","commits":2,"merge_commits":1})
        data=merge_activity_history(self.archive,self.github,self.gitlab,datetime(2026,11,1,1,tzinfo=timezone.utc))
        self.assertEqual(274,data["monthly"]["2026-10"])
        self.assertEqual(7,data["monthly"]["2026-11"])
        self.assertEqual(39197,data["total_contributions"])

    def test_new_year_is_added_without_losing_the_earlier_years(self):
        from render import merge_activity_history
        self.github.update(through_month="2026-12",observed_at="2027-01-01T01:00:00Z",monthly={
            "2026-10":{"contributions":162,"commits":12,"pull_requests":1,"restricted_contributions":149},
            "2026-11":{"contributions":1,"commits":1,"pull_requests":0,"restricted_contributions":0},
            "2026-12":{"contributions":1,"commits":1,"pull_requests":0,"restricted_contributions":0}},
            current_month={"month":"2027-01","contributions":5,"commits":3,"pull_requests":1,"restricted_contributions":1})
        data=merge_activity_history(self.archive,self.github,None,datetime(2027,1,1,2,tzinfo=timezone.utc))
        self.assertEqual(2027,data["last_year"])
        self.assertEqual(5,data["monthly"]["2027-01"])
        self.assertEqual(self.archive["monthly"]["2012-03"],data["monthly"]["2012-03"])
        labels,_=self.labels(data,True,"history")
        self.assertIn("2027*",labels)

    def test_pending_sources_are_unknown_and_stale_sources_keep_a_stale_label(self):
        from render import merge_activity_history,activity_status
        from github_snapshot import empty_snapshot as github_empty
        pending=merge_activity_history(self.archive,github_empty(),empty_snapshot(),self.now)
        labels,_=self.labels(pending,False)
        self.assertIn("SOURCE PENDING",labels)
        self.assertIn("—",labels)
        self.assertNotIn("0",labels)
        data=self.merged()
        self.assertTrue(activity_status(data,datetime(2026,10,23,15,tzinfo=timezone.utc)).startswith("STALE · AS OF"))
        self.assertIn("12:00 UTC",activity_status(data,self.now))

    def test_overlap_invalid_archive_and_future_observation_are_rejected(self):
        from render import merge_activity_history
        with self.assertRaises(ValueError):
            merge_activity_history(self.archive|{"observed_at":"2026-10-07"},self.github,self.gitlab,self.now)
        with self.assertRaises(ValueError):
            merge_activity_history(self.archive|{"total_contributions":0},self.github,self.gitlab,self.now)
        with self.assertRaises(ValueError):
            merge_activity_history(self.archive,self.github,self.gitlab,datetime(2026,10,22,tzinfo=timezone.utc))


if __name__=="__main__":
    unittest.main()
