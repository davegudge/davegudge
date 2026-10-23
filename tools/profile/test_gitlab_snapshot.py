import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from gitlab_snapshot import (CollectionError, GitLabClient, collect, empty_snapshot,
                             load_config, validate_snapshot)
from refresh import main


NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def commit(number, email="author@example.test", date="2026-10-20T09:00:00Z", merge=False):
    return {"id": f"{number:040x}", "author_email": email, "committed_date": date,
            "parent_ids": ["a" * 40, "b" * 40] if merge else ["a" * 40],
            "message": "PRIVATE_MESSAGE", "web_url": "https://private.example.test/PRIVATE_REPOSITORY"}


class Client:
    def __init__(self, commits=None, projects=None):
        self.commits = commits or []
        self.projects = projects if projects is not None else [{"id": 1}]
        self.calls = []
        self.missing = set()
        self.failure_project = None

    def get(self, path, params=None):
        self.calls.append((path, params))
        if path == "/user":
            return {"id": 42, "username": "test-user", "email": "author@example.test"}, {}
        if "/branches/" in path:
            if int(path.split("/")[2]) in self.missing:
                raise urllib.error.HTTPError("PRIVATE_URL", 404, "PRIVATE_ERROR", {}, None)
            return {"name": "integration"}, {}
        return {"id": int(path.split("/")[2])}, {}

    def pages(self, path, params=None):
        self.calls.append((path, params))
        if path == "/projects":
            return iter(self.projects)
        if self.failure_project and f"/projects/{self.failure_project}/" in path:
            raise urllib.error.HTTPError("PRIVATE_URL", 403, "PRIVATE_ERROR", {}, None)
        return iter(self.commits)


class GitLabSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.config = {"base_url": "https://gitlab.example.test", "token": "PRIVATE_TOKEN",
                       "start_date": "2026-10-12", "timezone": "Europe/London",
                       "branch": "integration", "username": "test-user", "author_emails": []}

    def test_open_month_is_collected_and_published_immediately(self):
        client = Client([commit(1)])
        previous = empty_snapshot()
        result = collect(self.config, previous, datetime(2026, 10, 23, tzinfo=timezone.utc), client)
        self.assertEqual({"month":"2026-10","commits":1,"merge_commits":0}, result["current_month"])
        self.assertEqual({}, result["monthly"])
        self.assertIsNone(previous["current_month"])
        self.assertTrue(any(path.endswith("/commits") for path,_ in client.calls))

    def test_running_count_changes_without_overlapping_the_archive(self):
        now = datetime(2026,10,23,10,tzinfo=timezone.utc)
        first = collect(self.config,empty_snapshot(),now,Client([commit(1)]))
        second = collect(self.config,first,now.replace(hour=11),Client([commit(1),commit(2,merge=True)]))
        self.assertEqual(1,first["current_month"]["commits"])
        self.assertEqual(2,second["current_month"]["commits"])
        self.assertEqual(1,second["current_month"]["merge_commits"])
        self.assertEqual({},second["monthly"])

    def test_legacy_monthly_snapshot_migrates_without_losing_archived_counts(self):
        legacy={"schema_version":1,"source":"gitlab","metric":"authored_commits_on_integration_branch",
                "start_date":"2026-10-12","timezone":"Europe/London","through_month":"2026-10",
                "observed_at":"2026-11-01T00:00:00Z","monthly":{"2026-10":{"commits":6,"merge_commits":3}}}
        result=collect(self.config,legacy,datetime(2026,11,2,tzinfo=timezone.utc),Client([commit(1,date="2026-11-01T10:00:00Z")]))
        self.assertEqual(2,result["schema_version"])
        self.assertEqual(legacy["monthly"],result["monthly"])
        self.assertEqual(1,result["current_month"]["commits"])

    def test_collects_exact_author_email_deduplicates_projects_and_separates_merges(self):
        client = Client([commit(1), commit(2, email="AUTHOR@example.test", merge=True),
                         commit(3, email="other@example.test")], projects=[{"id":1}, {"id":2}])
        result = collect(self.config, empty_snapshot(), NOW, client)
        self.assertEqual({"2026-10": {"commits": 2, "merge_commits": 1}}, result["monthly"])
        self.assertEqual("2026-10", result["through_month"])
        encoded = json.dumps(result)
        for private in ("PRIVATE", "author@", "test-user", "integration\"", "parent_ids", "committed_date", "2026-10-20"):
            self.assertNotIn(private, encoded)

    def test_partial_first_month_respects_local_midnight_and_exclusive_end(self):
        client = Client([commit(1, date="2026-10-11T22:59:59Z"),
                         commit(2, date="2026-10-11T23:00:00Z"),
                         commit(3, date="2026-11-01T00:00:00Z")])
        result = collect(self.config, empty_snapshot(), NOW, client)
        self.assertEqual(1, result["monthly"]["2026-10"]["commits"])
        params = next(params for path, params in client.calls if path.endswith("/commits"))
        self.assertEqual("2026-10-11T23:00:00+00:00", params["since"])
        self.assertEqual("2026-11-01T00:00:00+00:00", params["until"])
        self.assertEqual("integration", params["ref_name"])

    def test_london_month_boundary_during_summer_time(self):
        config = self.config | {"start_date": "2027-04-12"}
        client = Client([commit(1, date="2027-04-30T22:59:59Z"), commit(2, date="2027-04-30T23:00:00Z")])
        result = collect(config, empty_snapshot("2027-04-12"), datetime(2027,4,30,23,tzinfo=timezone.utc), client)
        self.assertEqual({"2027-04":{"commits":1,"merge_commits":0}}, result["monthly"])

    def test_published_month_is_immutable_while_current_month_refreshes(self):
        previous = collect(self.config, empty_snapshot(), NOW, Client([commit(1)]))
        result=collect(self.config,previous,datetime(2026,11,15,tzinfo=timezone.utc),
                       Client([commit(2,date="2026-11-12T09:00:00Z")]))
        self.assertEqual(previous["monthly"],result["monthly"])
        self.assertEqual(1,result["current_month"]["commits"])
        self.assertEqual(0,previous["current_month"]["commits"])
        with self.assertRaises(CollectionError):
            collect(self.config,previous,NOW,Client(projects=[]))

    def test_backfills_only_closed_months_without_changing_previous_counts(self):
        previous = collect(self.config, empty_snapshot(), NOW, Client([commit(1)]))
        result = collect(self.config, previous, datetime(2027,1,1,tzinfo=timezone.utc),
                         Client([commit(2, date="2026-12-12T09:00:00Z")]))
        self.assertEqual({"2026-10":{"commits":1,"merge_commits":0},
                          "2026-11":{"commits":0,"merge_commits":0},
                          "2026-12":{"commits":1,"merge_commits":0}}, result["monthly"])
        self.assertEqual("2026-10", previous["through_month"])

    def test_partial_project_failure_aborts_the_entire_candidate(self):
        previous = empty_snapshot()
        client = Client([commit(1)], projects=[{"id":1},{"id":2}])
        client.failure_project = 2
        with self.assertRaises(urllib.error.HTTPError):
            collect(self.config, previous, NOW, client)
        self.assertEqual(empty_snapshot(), previous)

    def test_missing_integration_branch_is_skipped_but_not_an_explicit_project(self):
        client = Client([commit(1)], projects=[{"id":1},{"id":2}])
        client.missing = {2}
        result = collect(self.config, empty_snapshot(), NOW, client)
        self.assertEqual(1, result["monthly"]["2026-10"]["commits"])
        with self.assertRaises(CollectionError):
            collect(self.config | {"project_ids":[2]}, empty_snapshot(), NOW, client)

    def test_no_projects_or_no_integration_branches_never_publishes_zero(self):
        client = Client(projects=[])
        with self.assertRaises(CollectionError):
            collect(self.config, empty_snapshot(), NOW, client)
        client = Client()
        client.missing = {1}
        with self.assertRaises(CollectionError):
            collect(self.config, empty_snapshot(), NOW, client)

    def test_rejects_wrong_identity_changed_period_and_future_archive(self):
        with self.assertRaises(CollectionError):
            collect(self.config | {"username":"someone-else"}, empty_snapshot(), NOW, Client())
        with self.assertRaises(CollectionError):
            collect(self.config | {"start_date":"2026-10-13"}, empty_snapshot(), NOW, Client())
        future = empty_snapshot() | {"through_month":"2026-11", "observed_at":"2026-12-01T00:00:00Z", "monthly":{
            "2026-10":{"commits":1,"merge_commits":0}, "2026-11":{"commits":1,"merge_commits":0}}}
        with self.assertRaises(CollectionError):
            collect(self.config, future, NOW, Client())

    def test_schema_rejects_daily_records_identifiers_and_inconsistent_counts(self):
        valid = collect(self.config, empty_snapshot(), NOW, Client([commit(1)]))
        for invalid in (valid | {"repository":"PRIVATE"}, valid | {"observed_at":"2026-11-01"},
                        valid | {"monthly":{"2026-10-20":{"commits":1,"merge_commits":0}}},
                        valid | {"monthly":{"2026-10":{"commits":1,"merge_commits":2}}},
                        valid | {"monthly":{"2026-10":{"commits":True,"merge_commits":0}}}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_snapshot(invalid)

    def test_config_uses_environment_without_publishing_credentials(self):
        with patch.dict(os.environ, {"GITLAB_PROFILE_TOKEN":"PRIVATE_TOKEN", "GITLAB_PROFILE_URL":"https://example.test"}, clear=True):
            config = load_config()
        self.assertEqual("develop", config["branch"])
        self.assertEqual("2026-10-12", config["start_date"])
        self.assertEqual([], config["author_emails"])
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(load_config())
        for url in ("http://example.test", "https://token@example.test", "https://example.test?token=secret"):
            with patch.dict(os.environ, {"GITLAB_PROFILE_TOKEN":"PRIVATE_TOKEN", "GITLAB_PROFILE_URL":url}, clear=True):
                with self.assertRaises(CollectionError):
                    load_config()

    def test_pagination_follows_all_pages_even_without_total_headers(self):
        client = GitLabClient(self.config)
        with patch.object(client, "get", side_effect=[([1]*100,{"X-Next-Page":"2"}),([2],{})]):
            self.assertEqual(101,len(list(client.pages("/items"))))
        with patch.object(client, "get", side_effect=[([1]*100,{}),([2],{})]):
            self.assertEqual(101,len(list(client.pages("/items"))))
        with patch.object(client, "get", return_value=([1],{"X-Next-Page":"1"})):
            with self.assertRaises(CollectionError):
                list(client.pages("/items"))

    def test_http_client_passes_token_in_header_and_disables_redirects(self):
        class Opener:
            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                class Response(io.BytesIO):
                    headers = {}
                return Response(b'{"id":42}')
        opener = Opener()
        with patch("gitlab_snapshot.urllib.request.build_opener", return_value=opener) as build:
            client = GitLabClient(self.config)
            self.assertEqual({"id":42},client.get("/user")[0])
        self.assertEqual("NoRedirect", build.call_args.args[0].__name__)
        self.assertEqual("PRIVATE_TOKEN",opener.request.get_header("Private-token"))
        self.assertNotIn("PRIVATE_TOKEN",opener.request.full_url)

    def test_refresh_failure_preserves_file_and_redacts_error_details(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "gitlab-history.json"
            path.write_text(json.dumps(empty_snapshot()) + "\n")
            previous = path.read_bytes()
            output = io.StringIO()
            with patch("refresh.DATA_DIR",Path(folder)), patch("refresh.load_config",return_value=self.config), \
                 patch("refresh.collect",side_effect=ValueError("PRIVATE_TOKEN PRIVATE_REPOSITORY")), \
                 patch("refresh.subprocess.run"), patch("refresh.refresh_source",return_value="unchanged"), \
                 patch("refresh.sys.argv",["refresh.py"]), contextlib.redirect_stdout(output):
                self.assertEqual(1,main())
            self.assertEqual(previous,path.read_bytes())
            self.assertNotIn("PRIVATE",output.getvalue())
            self.assertIn("preserving previous",output.getvalue())

    def test_unchanged_refresh_does_not_rewrite_monthly_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "gitlab-history.json"
            data = empty_snapshot()
            path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
            before = path.stat().st_mtime_ns
            with patch("refresh.DATA_DIR",Path(folder)), patch("refresh.load_config",return_value=self.config), \
                 patch("refresh.collect",return_value=data), patch("refresh.subprocess.run"), \
                 patch("refresh.refresh_source",return_value="unchanged"), patch("refresh.sys.argv",["refresh.py"]):
                self.assertEqual(0,main())
            self.assertEqual(before,path.stat().st_mtime_ns)


if __name__ == "__main__":
    unittest.main()
