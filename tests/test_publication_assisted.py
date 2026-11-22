"""Prospective review amendments never create real human decisions."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import test_publication as fixtures
from polarization_pipeline.targeted.common import atomic_json, read_csv, sha256
from polarization_pipeline.targeted.publication import annotations, batches, benchmark, training
from polarization_pipeline.targeted.publication.state import seal
from polarization_pipeline.targeted.publication.proposal_progress import report as progress
from polarization_pipeline.targeted.publication.evaluation_preflight import exposure_audit, sample_readiness


class AssistedBenchmarkTests(unittest.TestCase):
    def fixture(self, root):
        args = fixtures.PublicationTests().freeze_fixture(root)
        annotations.init_benchmark(args[3])
        return args

    def test_amendment_preserves_original_seal_and_blind_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, study, _ = self.fixture(Path(tmp))
            folder = study / 'annotations/benchmark'
            original = {n: sha256(folder/n) for n in ['sample.csv', 'manifest.json', 'human_review.csv']}
            blind = Path(batches.export(study, 'benchmark')['folder'])
            blind_hash = sha256(blind/'reading.json')
            result = annotations.enable_assisted_review(study, 'benchmark')
            self.assertTrue(result['changed'])
            self.assertEqual(original, {n: sha256(folder/n) for n in original})
            self.assertEqual(json.loads((folder/'manifest.json').read_text())['human_mode'], 'blind')
            self.assertEqual(annotations.checked(study, 'benchmark')[2]['human_mode'], 'assisted')
            assisted = Path(batches.export(study, 'benchmark')['folder'])
            self.assertNotEqual(assisted, blind)
            self.assertTrue((assisted/'proposal_template.json').exists())
            self.assertEqual(sha256(blind/'reading.json'), blind_hash)
            state_hash = sha256(folder/'proposal_state.json')
            self.assertFalse(annotations.enable_assisted_review(study, 'benchmark')['changed'])
            self.assertEqual(state_hash, sha256(folder/'proposal_state.json'))

    def test_refuses_existing_human_decisions_and_closed_references(self):
        for closed in [False, True]:
            with self.subTest(closed=closed), tempfile.TemporaryDirectory() as tmp:
                _, _, _, study, _ = self.fixture(Path(tmp))
                folder = study/'annotations/benchmark'
                if closed:
                    atomic_json(folder/'reference.json', {})
                else:
                    form = read_csv(folder/'human_review.csv')
                    form.loc[0, 'annotation_json'] = '[]'
                    form.to_csv(folder/'human_review.csv', index=False)
                with self.assertRaisesRegex(ValueError, 'cerrada|humanas'):
                    annotations.enable_assisted_review(study, 'benchmark')
                self.assertFalse((folder/'review_policy').exists())

    def test_recovers_interrupted_state_link_and_rejects_policy_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, study, _ = self.fixture(Path(tmp))
            folder = study/'annotations/benchmark'
            annotations.enable_assisted_review(study, 'benchmark')
            shutil.copy2(folder/'review_policy/original_proposal_state.json', folder/'proposal_state.json')
            with self.assertRaisesRegex(ValueError, 'incompleta'):
                annotations.checked(study, 'benchmark')
            annotations.enable_assisted_review(study, 'benchmark')
            self.assertEqual(annotations.checked(study, 'benchmark')[2]['human_mode'], 'assisted')
            (folder/'review_policy/policy.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'alterado'):
                annotations.checked(study, 'benchmark')

    def test_assisted_review_records_digest_and_closes_effective_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, study, reg = self.fixture(Path(tmp))
            folder = study/'annotations/benchmark'
            annotations.enable_assisted_review(study, 'benchmark')
            fixtures.PublicationTests().proposals(study, 'benchmark', reg)
            self.assertTrue(read_csv(folder/'human_review.csv').review_complete.eq('').all())
            with patch('builtins.input', side_effect=['synthetic reviewer']+['a', 's']*4):
                annotations.review(study, 'benchmark', reg)
            form = read_csv(folder/'human_review.csv')
            self.assertTrue(form.decision.eq('accepted').all())
            self.assertTrue(form.proposal_sha256.ne('').all())
            self.assertFalse(annotations.enable_assisted_review(study, 'benchmark')['changed'])
            self.assertEqual(sample_readiness(study, 'benchmark')[2]['mode'], 'assisted')
            annotations.close_reference(study, 'benchmark', reg)
            reference = json.loads((folder/'reference.json').read_text())
            self.assertEqual(reference['human_mode'], 'assisted')
            self.assertIn('review_policy/policy.json', reference['files'])

    def test_indexed_exposure_deduplicates_id_and_text_matches(self):
        benchmark = pd.DataFrame([
            dict(comment_id='same', text='Hello', reviewer_id='r', reviewed_at='2026-11-22'),
            dict(comment_id='different', text=' Hello ', reviewer_id='', reviewed_at=''),
            dict(comment_id='other', text='unseen', reviewer_id='', reviewed_at='')])
        sample = pd.DataFrame([
            dict(sample_id='a', comment_id='same', text='Hello'),
            dict(sample_id='b', comment_id='dup', text='Hello')])
        form = pd.DataFrame([
            dict(sample_id='a', review_complete='true', reviewer_id='r', reviewed_at='2026-11-21'),
            dict(sample_id='b', review_complete='', reviewer_id='', reviewed_at='')])
        from polarization_pipeline.targeted.annotations import text_key
        with patch('polarization_pipeline.targeted.publication.evaluation_preflight.text_key', wraps=text_key) as key:
            result = exposure_audit(benchmark, [('cohort_0001', sample, form)])
        self.assertEqual(key.call_count, len(sample)+len(benchmark))
        self.assertEqual(result['overlapping_benchmark_comments'], 2)
        self.assertEqual(result['recorded_prior_exposure'], 1)
        self.assertEqual(result['potential_exposure_unknown'], 1)
        self.assertEqual(result['rows'][0]['cohorts'], ['cohort_0001'])

    def test_progress_waits_for_all_proposals_and_stops_at_comparability(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, _, study, reg = self.fixture(Path(tmp))
            annotations.next_batch(setting, plan, study, reg)
            fixtures.PublicationTests().proposals(study, 'benchmark', reg)
            result = progress(setting, plan, study, reg)
            self.assertEqual(result['status'], 'waiting_cohort_proposals')
            self.assertEqual(result['provisional_comparable_users'], 0)
            fixtures.PublicationTests().proposals(study, 'cohort_0001', reg)
            result = progress(setting, plan, study, reg)
            self.assertEqual(result['status'], 'provisional_scope_ready')
            self.assertTrue(result['target_reached'])
            self.assertNotIn('gap', result)
            self.assertEqual(result['samples']['cohort_0001']['human_confirmed'], 0)
            self.assertTrue((setting['outputs']/study.name/'proposal_progress/latest.json').exists())

    def test_progress_reports_exhaustion_without_reaching_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, _, study, reg = self.fixture(Path(tmp))
            plan['comparable_users'] = 800
            fixtures.PublicationTests().proposals(study, 'benchmark', reg)
            for name in ['cohort_0001', 'cohort_0002']:
                annotations.next_batch(setting, plan, study, reg)
                fixtures.PublicationTests().proposals(study, name, reg)
            result = progress(setting, plan, study, reg)
            self.assertTrue(result['frame_exhausted'])
            self.assertFalse(result['target_reached'])
            self.assertEqual(result['status'], 'provisional_scope_ready')
            self.assertEqual(result['fully_proposed_users'], 2)

    def test_final_comparison_labels_assisted_reference_truthfully(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, _, study, reg = self.fixture(Path(tmp))
            annotations.enable_assisted_review(study, 'benchmark')
            annotations.next_batch(setting, plan, study, reg)
            for name in ['benchmark', 'cohort_0001']:
                fixtures.PublicationTests().proposals(study, name, reg)
                n = len(read_csv(study/'annotations'/name/'sample.csv'))
                with patch('builtins.input', side_effect=['synthetic reviewer']+['a', 's']*n):
                    annotations.review(study, name, reg)
            pairs = training.prediction_pairs(study, reg)
            pairs.to_csv(study/'prediction_input.csv', index=False)
            training.prediction_comments(study)[['comment_id', 'post_id']].to_csv(study/'prediction_scope.csv', index=False)
            pred = study/'predictions'; pred.mkdir()
            for model in benchmark.MODEL_IDS:
                rows = pairs[['sample_id', 'comment_id', 'post_id', 'target_id']].assign(
                    valence='neutral', accepted=True, context_complete=True, model_id=model)
                rows.to_csv(pred/f'{model}.csv', index=False)
            seal(pred, [f'{m}.csv' for m in benchmark.MODEL_IDS], diagnostic_only=True,
                 prediction_input_sha256=sha256(study/'prediction_input.csv'),
                 prediction_scope_sha256=sha256(study/'prediction_scope.csv'))
            result = benchmark.compare(setting, plan, study, reg, stage='final')
            summary = json.loads((result/'summary.json').read_text())
            self.assertEqual(summary['reference'], 'single_human_assisted')
            self.assertFalse(summary['independently_validated'])
            self.assertFalse(summary['reserved_test_opened'])


if __name__ == '__main__':
    unittest.main()
