import unittest
from unittest.mock import patch

from adsb_publish import publish


class AdsbPublishTest(unittest.TestCase):
    def test_rejects_urls_that_could_expose_the_token(self):
        for url in ("http://example.test/api/profile_adsb",
                    "https://user@example.test/api/profile_adsb",
                    "https://example.test/api/profile_adsb?token=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                publish(url, "secret", {"aircraft_seen_last_60_seconds": 3})

    def test_sends_aggregate_with_bearer_token(self):
        class Response:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class Opener:
            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return Response()

        opener = Opener()
        with patch("adsb_publish.urllib.request.build_opener", return_value=opener):
            publish("https://smon.example.test/api/profile_adsb", "secret",
                    {"aircraft_seen_last_60_seconds": 3})
        self.assertEqual("Bearer secret", opener.request.get_header("Authorization"))
        self.assertTrue(opener.request.get_header("User-agent").startswith("profile-preview/1.0"))
        self.assertEqual(b'{"aircraft_seen_last_60_seconds":3}', opener.request.data)
        self.assertEqual(15, opener.timeout)


if __name__ == "__main__":
    unittest.main()
