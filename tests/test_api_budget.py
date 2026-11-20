"""Persistent Pacific quota accounting and publication capture overrides."""
import json
import multiprocessing
import tempfile
import unittest
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_publication as fixtures
from polarization_pipeline.targeted.collection import BudgetedAPI, CollectionPaused, APIRequestFailed
from polarization_pipeline.targeted.common import atomic_json, sha256
from polarization_pipeline.targeted.publication import data


class FakeAPI:
    def __init__(self, error=None):
        self.requests = 0
        self.error = error

    def videos(self):
        return self

    def commentThreads(self):
        return self

    def list(self, **params):
        return self

    def execute(self):
        self.requests += 1
        if self.error is not None:
            raise self.error
        return {"items": []}


def reserve_in_process(ledger):
    client = BudgetedAPI(FakeAPI(), Path(ledger), 12,
        clock=lambda: datetime.fromisoformat("2026-11-19T04:00:00+00:00"))
    try:
        client.call("videos")
        return True
    except CollectionPaused:
        return False


class BudgetTests(unittest.TestCase):
    def client(self, root, now="2026-11-19T04:00:00+00:00", budget=9000, api=None):
        return BudgetedAPI(api or FakeAPI(), root / "api_usage.json", budget,
            clock=lambda: datetime.fromisoformat(now))

    def test_conservative_migration_and_utc_history_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            atomic_json(root / "api_usage.json", {"2026-11-17":906,"2026-11-18":2500,"2026-11-19":2500})
            client = self.client(root)
            self.assertEqual(client.budget_status()["local_remaining"], 4000)
            client.call("videos")
            pt = json.loads(client.pt_ledger.read_text())
            self.assertEqual(pt["days"], {"2026-11-18":5001})
            self.assertEqual(pt["migration"]["overlapping_utc_days"], ["2026-11-18","2026-11-19"])
            self.assertEqual(json.loads(client.ledger.read_text()), {"2026-11-17":906,"2026-11-18":2500,"2026-11-19":2501})
            self.assertFalse(client.budget_status()["official_google_balance_verified"])

    def test_utc_midnight_does_not_reset_but_pacific_midnight_does(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.client(root, "2026-11-18T23:59:59+00:00", 1).call("videos")
            with self.assertRaises(CollectionPaused) as caught:
                self.client(root, "2026-11-19T00:00:00+00:00", 1).call("videos")
            self.assertEqual(caught.exception.reason, "local_budget")
            with self.assertRaises(CollectionPaused):
                self.client(root, "2026-11-19T07:59:59+00:00", 1).call("videos")
            self.client(root, "2026-11-19T08:00:00+00:00", 1).call("videos")
            self.assertEqual(json.loads((root / "api_usage_pt.json").read_text())["days"], {"2026-11-18":1,"2026-11-19":1})

    def test_dst_days_have_correct_next_reset(self):
        for now, reset in [("2026-03-08T09:00:00+00:00", "2026-03-09T07:00:00+00:00"),
                           ("2026-11-01T08:00:00+00:00", "2026-11-02T08:00:00+00:00")]:
            with self.subTest(now=now), tempfile.TemporaryDirectory() as tmp:
                client = self.client(Path(tmp), now)
                self.assertEqual(client.budget_status()["next_reset_utc"], reset)

    def test_multiprocess_shared_budget_has_no_lost_reservations(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = str(Path(tmp) / "api_usage.json")
            with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("fork")) as pool:
                outcomes = list(pool.map(reserve_in_process, [ledger]*30))
            self.assertEqual(sum(outcomes), 12)
            self.assertEqual(json.loads(Path(ledger).read_text()), {"2026-11-19":12})
            self.assertEqual(json.loads((Path(tmp)/"api_usage_pt.json").read_text())["days"], {"2026-11-18":12})

    def test_transport_retries_all_count_and_no_key_is_exposed(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = FakeAPI(OSError("SECRET_TEST_KEY_URL"))
            client = self.client(Path(tmp), api=api)
            with patch("polarization_pipeline.targeted.collection.time.sleep"), self.assertRaises(APIRequestFailed) as caught:
                client.call("videos")
            self.assertEqual(api.requests, 4)
            self.assertEqual(client.budget_status()["locally_accounted_requests"], 4)
            self.assertEqual(caught.exception.reason, "transport_error")
            self.assertNotIn("SECRET_TEST_KEY_URL", str(caught.exception))

    def test_remote_quota_is_distinct_and_is_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            error = RuntimeError("SECRET_TEST_KEY_URL")
            error.resp = SimpleNamespace(status=403)
            error.content = b'{"error":"quotaExceeded"}'
            api = FakeAPI(error)
            client = self.client(Path(tmp), api=api)
            with self.assertRaises(CollectionPaused) as caught:
                client.call("videos")
            self.assertEqual(caught.exception.reason, "youtube_quota")
            self.assertEqual(api.requests, 1)
            self.assertEqual(client.budget_status()["locally_accounted_requests"], 1)

    def test_failed_utc_mirror_never_releases_pt_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self.client(Path(tmp), budget=1)
            original = atomic_json
            def fail_mirror(path, value):
                if path == client.ledger:
                    raise OSError("synthetic disk failure")
                return original(path, value)
            with patch("polarization_pipeline.targeted.collection.atomic_json", side_effect=fail_mirror), self.assertRaises(OSError):
                client.call("videos")
            self.assertEqual(client.api.requests, 0)
            with self.assertRaises(CollectionPaused):
                client.call("videos")
            self.assertEqual(client.budget_status()["local_remaining"], 0)

    def test_invalid_ledger_or_budget_fails_before_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for budget in [0, -1, True, 1.5]:
                with self.assertRaises(ValueError): self.client(root, budget=budget)
            client = self.client(root)
            atomic_json(client.ledger, {"2026-11-19":-1})
            with self.assertRaises(ValueError): client.call("videos")
            self.assertEqual(client.api.requests, 0)

    def test_publication_override_preserves_protected_config_and_skips_complete_videos(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, _, study, _ = fixtures.PublicationTests().fixture(Path(tmp))
            config_hash = sha256(Path(tmp)/"publication.toml")
            original_plan = plan.copy()
            api = FakeAPI()
            result = data.collect(setting, plan, study, api=api, max_videos=2, daily_api_budget=9)
            self.assertEqual(api.requests, 2)
            self.assertEqual(result["collection"]["effective_daily_budget"], 9)
            self.assertEqual(result["collection"]["outcome"], "max_videos")
            self.assertEqual(result["capture_status"]["complete"], 2)
            resumed = data.collect(setting, plan, study, api=api)  # configured cap is only 1
            self.assertEqual(resumed["collection"]["outcome"], "local_budget")
            self.assertEqual(api.requests, 2)
            self.assertEqual(resumed["capture_status"]["complete"], 2)
            self.assertEqual(config_hash, sha256(Path(tmp)/"publication.toml"))
            self.assertEqual(original_plan, plan)
            self.assertEqual(len(list((setting["outputs"]/study.name/"collection_runs").glob("*.json"))), 2)

    def test_publication_remote_quota_preserves_partial_capture_and_records_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, _, study, _ = fixtures.PublicationTests().fixture(Path(tmp))
            error = RuntimeError("secret")
            error.resp = SimpleNamespace(status=403); error.content=b'quotaExceeded'
            result = data.collect(setting, plan, study, api=FakeAPI(error), daily_api_budget=9)
            self.assertEqual(result["collection"]["outcome"], "youtube_quota")
            self.assertEqual(result["capture_status"]["incomplete"], 1)
            self.assertEqual(result["collection"]["budget_after"]["locally_accounted_requests"], 1)


if __name__ == "__main__":
    unittest.main()
