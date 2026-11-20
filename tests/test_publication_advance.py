"""Capture continuation must stop at quota, data errors and human annotation gates."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from polarization_pipeline.targeted.common import atomic_json, sha256
from polarization_pipeline.targeted.publication import advance
from polarization_pipeline.targeted.publication.state import lock
import test_publication as fixtures


class AdvanceTests(unittest.TestCase):
    def fixture(self, root, frozen=False):
        helper = fixtures.PublicationTests()
        return helper.freeze_fixture(root) if frozen else helper.fixture(root)

    def test_active_collector_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture(Path(tmp))
            with lock(args[0]['workspace'] / 'publication_collection.lock'):
                with patch.object(advance.data, 'collect', side_effect=AssertionError('duplicate collector')):
                    self.assertEqual(advance.step(*args, 9000), {'status': 'waiting_active_capture'})
            self.assertFalse((args[3] / 'freeze.json').exists())

    def test_exhausted_local_budget_waits_without_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture(Path(tmp))
            budget = dict(local_remaining=0, quota_day='2026-11-19', next_reset_utc='2026-11-20T08:00:00Z')
            with patch.object(advance.BudgetedAPI, 'budget_status', return_value=budget):
                with patch.object(advance.data, 'collect', side_effect=AssertionError('spent quota')):
                    result = advance.step(*args, 9000)
            self.assertEqual(result['status'], 'waiting_quota')
            self.assertEqual(result['reason'], 'local_budget')
            self.assertFalse((args[3] / 'annotations').exists())

    def test_official_quota_waits_even_with_local_balance_then_resumes_next_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture(Path(tmp))
            previous = dict(outcome='youtube_quota', budget_after={'quota_day': '2026-11-19'})
            budget = dict(local_remaining=1000, quota_day='2026-11-19')
            with patch.object(advance, 'latest_collection', return_value=previous):
                with patch.object(advance.BudgetedAPI, 'budget_status', return_value=budget):
                    with patch.object(advance.data, 'collect') as collect:
                        result = advance.step(*args, 9000)
                        collect.assert_not_called()
                        self.assertEqual(result['reason'], 'youtube_quota')
                        budget['quota_day'] = '2026-11-20'
                        collect.return_value = {'collection': {'outcome': 'local_budget', 'budget_after': budget}}
                        result = advance.step(*args, 9000)
                        collect.assert_called_once_with(args[0], args[1], args[3], daily_api_budget=9000)
                        self.assertEqual(result['status'], 'waiting_quota')

    def test_closed_capture_freezes_and_initializes_only_first_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture(Path(tmp), frozen=True)
            result = advance.step(*args, 9000)
            study = args[3]
            self.assertEqual(result['status'], 'waiting_annotations')
            self.assertEqual(result['benchmark_comments'], 4)
            self.assertEqual(result['cohort_users'], 1)
            self.assertEqual(result['cohort_comments'], 5)
            self.assertFalse(result['production_enabled'])
            self.assertEqual(result['human_decisions_written'], 0)
            self.assertFalse((args[2] / 'model/test_opened.json').exists())
            forms = list((study/'annotations').glob('*/human_review.csv'))
            before = {str(p): (sha256(p), p.stat().st_mtime_ns) for p in forms}
            second = advance.run(*args, daily_api_budget=9000)
            self.assertEqual(second['status'], 'waiting_annotations')
            self.assertEqual(before, {str(p): (sha256(p), p.stat().st_mtime_ns) for p in forms})
            for form in forms:
                from polarization_pipeline.targeted.common import read_csv
                self.assertTrue(read_csv(form).review_complete.eq('').all())

    def test_completed_collection_freezes_before_sampling(self):
        from polarization_pipeline.targeted.common import read_csv
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture(Path(tmp))
            def complete(*_, **kwargs):
                for video in read_csv(args[3] / 'videos.csv').to_dict('records'):
                    atomic_json(args[3] / 'raw_capture' / (video['post_id'] + '.json'),
                                dict(status='complete', video=video, comments={}, finished_at='2026-11-19'))
                return {'collection': {'outcome': 'completed'}}
            with patch.object(advance.BudgetedAPI, 'budget_status', return_value=dict(local_remaining=100, quota_day='2026-11-19')):
                with patch.object(advance.data, 'collect', side_effect=complete):
                    result = advance.step(*args, 9000)
            self.assertTrue((args[3] / 'freeze.json').exists())
            self.assertEqual(result['status'], 'waiting_annotations')

    def test_failed_capture_needs_attention_without_retrying(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture(Path(tmp))
            with patch.object(advance, 'latest_collection', return_value=dict(outcome='transport_error')):
                with patch.object(advance.data, 'collect', side_effect=AssertionError('automatic retry')):
                    result = advance.step(*args, 9000)
            self.assertEqual(result['status'], 'needs_attention')

    def test_watch_waits_without_duplicate_reports_and_exits_before_reviews(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture(Path(tmp))
            states = [dict(status='waiting_active_capture'), dict(status='waiting_active_capture'), dict(status='waiting_annotations')]
            with patch.object(advance, 'step', side_effect=states):
                with patch.object(advance.time, 'sleep') as sleep:
                    result = advance.run(*args, daily_api_budget=9000, watch=True)
            self.assertEqual(result['status'], 'waiting_annotations')
            self.assertEqual(sleep.call_count, 2)
            folder = args[0]['outputs'] / args[3].name / 'advancement'
            self.assertEqual(len(list(folder.glob('*.json'))), 3)  # two transitions plus latest state
            with lock(args[3] / 'advancement.lock'):
                with self.assertRaises(BlockingIOError):
                    advance.run(*args)

    def test_errors_save_only_type_and_preserve_protected_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture(Path(tmp))
            before = sha256(args[3] / 'study.json')
            with patch.object(advance, 'step', side_effect=RuntimeError('sensitive external URL')):
                with self.assertRaises(RuntimeError) as error:
                    advance.run(*args)
            self.assertNotIn('sensitive', str(error.exception))
            state = args[0]['outputs'] / args[3].name / 'advancement/state.json'
            self.assertNotIn('sensitive', state.read_text())
            self.assertEqual(json.loads(state.read_text())['error_type'], 'RuntimeError')
            self.assertEqual(before, sha256(args[3] / 'study.json'))
