import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from github_snapshot import (CollectionError, GitHubClient, collect, empty_snapshot,
                             validate_snapshot, QUERY)


def counts(contributions=8, commits=4):
    return {"contributions":contributions,"commits":commits,"pull_requests":1,"restricted_contributions":2}


class Client:
    def __init__(self, values=None):
        self.calls=[]
        self.values=values or {"2026-10":counts()}

    def counts(self, login, beginning, end):
        self.calls.append((login,beginning,end))
        value=self.values.get(beginning.strftime("%Y-%m"),counts(0,0)|{"pull_requests":0,"restricted_contributions":0})
        if isinstance(value,Exception):
            raise value
        return value


class GitHubSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,23,12,tzinfo=timezone.utc)
        self.archive={"observed_at":"2026-10-06"}

    def test_current_month_is_published_after_archive_cutoff(self):
        client=Client()
        result=collect("token","test-user",empty_snapshot(),self.archive,self.now,client)
        self.assertEqual({"month":"2026-10",**counts()},result["current_month"])
        self.assertEqual({},result["monthly"])
        self.assertEqual(datetime(2026,10,7,tzinfo=timezone.utc),client.calls[0][1])
        self.assertEqual(self.now,client.calls[0][2])
        self.assertEqual("2026-10-06",self.archive["observed_at"])

    def test_running_month_updates_and_closed_months_are_disjoint(self):
        first=collect("token","test-user",empty_snapshot(),self.archive,self.now,Client())
        current=collect("token","test-user",first,self.archive,self.now.replace(hour=13),Client({"2026-10":counts(9,5)}))
        self.assertEqual(9,current["current_month"]["contributions"])
        self.assertEqual(8,first["current_month"]["contributions"])
        client=Client({"2026-10":counts(10,6),"2026-11":counts(3,1)})
        next_month=collect("token","test-user",current,self.archive,datetime(2026,11,1,12,tzinfo=timezone.utc),client)
        self.assertEqual(counts(10,6),next_month["monthly"]["2026-10"])
        self.assertEqual("2026-11",next_month["current_month"]["month"])
        self.assertEqual(datetime(2026,10,31,23,59,59,tzinfo=timezone.utc),client.calls[0][2])
        self.assertEqual(datetime(2026,11,1,tzinfo=timezone.utc),client.calls[1][1])

    def test_completed_month_is_preserved_after_rollover(self):
        previous=collect("token","test-user",empty_snapshot(),self.archive,datetime(2026,11,2,tzinfo=timezone.utc),Client())
        client=Client({"2026-10":counts(100,50),"2026-11":counts(3,1)})
        result=collect("token","test-user",previous,self.archive,datetime(2026,11,3,tzinfo=timezone.utc),client)
        self.assertEqual(previous["monthly"],result["monthly"])
        self.assertEqual(1,len(client.calls))

    def test_partial_failure_keeps_previous_object_intact(self):
        previous=empty_snapshot()
        client=Client({"2026-10":counts(),"2026-11":ValueError("PRIVATE_ERROR")})
        with self.assertRaises(ValueError):
            collect("token","test-user",previous,self.archive,datetime(2026,11,2,tzinfo=timezone.utc),client)
        self.assertEqual(empty_snapshot(),previous)

    def test_overlap_and_future_observations_are_rejected(self):
        with self.assertRaises(CollectionError):
            collect("token","test-user",empty_snapshot(),{"observed_at":"2026-10-07"},self.now,Client())
        previous=collect("token","test-user",empty_snapshot(),self.archive,self.now,Client())
        with self.assertRaises(CollectionError):
            collect("token","test-user",previous,self.archive,self.now.replace(day=22),Client())

    def test_only_monthly_aggregates_are_accepted(self):
        valid=collect("token","test-user",empty_snapshot(),self.archive,self.now,Client())
        for invalid in (valid|{"daily":[]},valid|{"repository":"PRIVATE"},
                        valid|{"current_month":valid["current_month"]|{"commits":True}},
                        valid|{"current_month":valid["current_month"]|{"commits":100}},
                        valid|{"current_month":valid["current_month"]|{"month":"2026-11"}}):
            with self.assertRaises(ValueError):
                validate_snapshot(invalid)

    def test_query_requests_no_daily_calendar_or_repository_details(self):
        for forbidden in ("weeks", "contributionDays", "repositories", "email", "commitContributionsByRepository"):
            self.assertNotIn(forbidden,QUERY)
        self.assertIn("totalCommitContributions",QUERY)

    def test_http_client_rejects_partial_graphql_data_and_keeps_token_out_of_url(self):
        class Opener:
            def __init__(self,data):
                self.data=data
            def open(self,request,timeout):
                self.request=request
                return io.BytesIO(json.dumps(self.data).encode())
        data={"data":{"user":{"contributionsCollection":{
            "contributionCalendar":{"totalContributions":8},"totalCommitContributions":4,
            "totalPullRequestContributions":1,"restrictedContributionsCount":2}}}}
        opener=Opener(data)
        with patch("github_snapshot.urllib.request.build_opener",return_value=opener):
            client=GitHubClient("PRIVATE_TOKEN")
            self.assertEqual(counts(),client.counts("test-user",self.now,self.now))
            self.assertEqual("Bearer PRIVATE_TOKEN",opener.request.get_header("Authorization"))
            self.assertNotIn("PRIVATE_TOKEN",opener.request.full_url)
            opener.data=data|{"errors":[{"message":"PRIVATE_ERROR"}]}
            with self.assertRaises(CollectionError):
                client.counts("test-user",self.now,self.now)


if __name__ == "__main__":
    unittest.main()
