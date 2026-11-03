"""Unit tests for the framework-free core: validators, retry, cache logic.

Run with:  python -m unittest discover -s tests -v
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db, service  # noqa: E402
from app.errors import NotFoundUpstream, RetryableUpstream, UpstreamError  # noqa: E402
from app.retry import retry_with_backoff  # noqa: E402
from app.validators import is_valid_cep, is_valid_cnpj, normalize_cep, normalize_cnpj  # noqa: E402


class ValidatorTests(unittest.TestCase):
    def test_valid_cnpj_with_and_without_punctuation(self):
        self.assertTrue(is_valid_cnpj("00000000000191"))
        self.assertTrue(is_valid_cnpj("00.000.000/0001-91"))
        self.assertTrue(is_valid_cnpj("11.222.333/0001-81"))

    def test_invalid_cnpj(self):
        self.assertFalse(is_valid_cnpj("00000000000192"))  # wrong check digit
        self.assertFalse(is_valid_cnpj("11111111111111"))  # repeated digits
        self.assertFalse(is_valid_cnpj("123"))             # too short
        self.assertFalse(is_valid_cnpj(""))

    def test_normalizers(self):
        self.assertEqual(normalize_cnpj("00.000.000/0001-91"), "00000000000191")
        self.assertEqual(normalize_cep("01001-000"), "01001000")

    def test_cep(self):
        self.assertTrue(is_valid_cep("01001-000"))
        self.assertFalse(is_valid_cep("0100"))


class RetryTests(unittest.TestCase):
    def test_succeeds_after_temporary_failures(self):
        calls, sleeps = [], []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise RetryableUpstream("boom")
            return {"ok": True}

        result = retry_with_backoff(flaky, attempts=3, base_delay=1, sleep=sleeps.append)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(sleeps), 2)
        self.assertGreaterEqual(sleeps[1], sleeps[0])  # exponential backoff grows

    def test_gives_up_after_max_attempts(self):
        calls = []

        def always_fails():
            calls.append(1)
            raise RetryableUpstream("still down")

        with self.assertRaises(RetryableUpstream):
            retry_with_backoff(always_fails, attempts=3, base_delay=0, sleep=lambda s: None)
        self.assertEqual(len(calls), 3)

    def test_does_not_retry_non_retryable_errors(self):
        calls = []

        def not_found():
            calls.append(1)
            raise NotFoundUpstream()

        with self.assertRaises(NotFoundUpstream):
            retry_with_backoff(not_found, attempts=3, base_delay=0, sleep=lambda s: None)
        self.assertEqual(len(calls), 1)


class ServiceCacheTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.fetch_calls = []

    def fetch_ok(self, key):
        self.fetch_calls.append(key)
        return {"razao_social": "ACME LTDA", "uf": "RS"}

    def test_first_call_hits_api_second_uses_cache(self):
        first = service.get_or_fetch(self.conn, "cnpj", "00000000000191", self.fetch_ok, 3600)
        second = service.get_or_fetch(self.conn, "cnpj", "00000000000191", self.fetch_ok, 3600)
        self.assertEqual(first.source, "api")
        self.assertEqual(second.source, "cache")
        self.assertEqual(len(self.fetch_calls), 1)

    def test_expired_cache_is_refreshed(self):
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        db.save(self.conn, "cnpj", "00000000000191", {"razao_social": "OLD"}, now=old)
        result = service.get_or_fetch(self.conn, "cnpj", "00000000000191", self.fetch_ok, 3600)
        self.assertEqual(result.source, "api")
        self.assertEqual(result.payload["razao_social"], "ACME LTDA")

    def test_stale_cache_served_when_upstream_is_down(self):
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        db.save(self.conn, "cnpj", "00000000000191", {"razao_social": "OLD"}, now=old)

        def down(key):
            raise RetryableUpstream("upstream down")

        result = service.get_or_fetch(self.conn, "cnpj", "00000000000191", down, 3600)
        self.assertEqual(result.source, "cache-stale")
        self.assertEqual(result.payload["razao_social"], "OLD")

    def test_upstream_failure_without_cache_raises(self):
        def down(key):
            raise RetryableUpstream("upstream down")

        with self.assertRaises(UpstreamError):
            service.get_or_fetch(self.conn, "cnpj", "00000000000191", down, 3600)

    def test_not_found_is_never_served_from_stale_cache(self):
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        db.save(self.conn, "cnpj", "00000000000191", {"razao_social": "OLD"}, now=old)

        def gone(key):
            raise NotFoundUpstream()

        with self.assertRaises(NotFoundUpstream):
            service.get_or_fetch(self.conn, "cnpj", "00000000000191", gone, 3600)

    def test_list_returns_most_recent_first(self):
        db.save(self.conn, "cnpj", "A", {"n": 1}, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        db.save(self.conn, "cnpj", "B", {"n": 2}, now=datetime(2026, 2, 1, tzinfo=timezone.utc))
        keys = [r["key"] for r in db.list_kind(self.conn, "cnpj")]
        self.assertEqual(keys, ["B", "A"])


if __name__ == "__main__":
    unittest.main()
