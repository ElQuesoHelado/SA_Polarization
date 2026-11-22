"""Resource ceiling freezes the prefix, never stops according to significance."""
import json
import tempfile
import unittest
from pathlib import Path

import test_publication as fixtures
from polarization_pipeline.targeted.common import sha256
from polarization_pipeline.targeted.publication import annotations,analysis,fixed_scope
from polarization_pipeline.targeted.publication.proposal_progress import report

class FixedScopeTests(unittest.TestCase):
    def test_policy_idempotent_and_cannot_revise_or_ignore_tamper(self):
        with tempfile.TemporaryDirectory() as t:
            s,p,_,d,r=fixtures.PublicationTests().freeze_fixture(Path(t))
            fixed_scope.enable(d,2,1);h=sha256(d/'fixed_user_scope/manifest.json')
            fixed_scope.enable(d,2,1);self.assertEqual(h,sha256(d/'fixed_user_scope/manifest.json'))
            with self.assertRaises(ValueError):fixed_scope.enable(d,1,1)
            (d/'fixed_user_scope/policy.json').write_text('{}')
            with self.assertRaises(ValueError):fixed_scope.policy(d)

    def test_ceiling_replaces_comparable_target_and_initial_cut_skips_pending(self):
        with tempfile.TemporaryDirectory() as t:
            s,p,_,d,r=fixtures.PublicationTests().freeze_fixture(Path(t));p['comparable_users']=800
            annotations.init_benchmark(d);fixed_scope.enable(d,2,1)
            annotations.next_batch(s,p,d,r);fixtures.PublicationTests().proposals(d,'cohort_0001',r)
            annotations.next_batch(s,p,d,r)
            # Initial prefix analyzes even though second selected cohort is unannotated.
            out=analysis.analyze(s,p,d,r,screened_users=1)
            initial_hash=sha256(out/'summary.json')
            j=json.loads((out/'summary.json').read_text());self.assertEqual(j['screened_users'],1)
            self.assertEqual(j['comparable_users'],1);self.assertTrue(j['is_initial_report'])
            with self.assertRaises(ValueError):analysis.analyze(s,p,d,r,stage='final',screened_users=1)
            with self.assertRaises(ValueError):analysis.analyze(s,p,d,r,screened_users=3)
            with self.assertRaises(ValueError):annotations.next_batch(s,p,d,r)
            fixtures.PublicationTests().proposals(d,'cohort_0002',r)
            fixtures.PublicationTests().proposals(d,'benchmark',r)
            result=annotations.next_batch(s,p,d,r);self.assertEqual(result['status'],'fixed_user_scope_reached')
            self.assertFalse((d/'annotations/cohort_0003').exists())
            progress=report(s,p,d,r);self.assertTrue(progress['target_reached']);self.assertEqual(progress['stopping_rule'],'fixed_screened_users')
            out2=analysis.analyze(s,p,d,r,screened_users=2)
            self.assertNotEqual(out,out2);self.assertEqual(json.loads((out2/'summary.json').read_text())['comparable_users'],2)
            self.assertEqual(sha256(out/'summary.json'),initial_hash)

    def test_human_final_closes_fixed_prefix_with_zero_comparables(self):
        from test_publication_measurement import MeasurementTests
        from polarization_pipeline.targeted.publication.measurement import preflight
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            settings,plan,_,study,registry=fixtures.PublicationTests().freeze_fixture(root)
            plan['comparable_users']=800
            fixed_scope.enable(study,1,1)
            annotations.next_batch(settings,plan,study,registry)
            pending=preflight(settings,plan,study,registry)
            self.assertEqual(pending['status'],'waiting_human_review')
            self.assertEqual(pending['screened_users_ceiling'],1)
            # Confirmations exist exclusively inside this temporary synthetic fixture.
            MeasurementTests().complete_synthetic_batch(study,registry,empty=True)
            ready=preflight(settings,plan,study,registry)
            self.assertTrue(ready['ready_for_analysis'])
            self.assertFalse(ready['frame_exhausted'])
            self.assertEqual(ready['comparable_users'],0)
            (root/'AGENTS.md').write_text('<!-- BEGIN GENERATED RESULTS COMPARISON -->\nhistorical sentinel\n<!-- END GENERATED RESULTS COMPARISON -->\n')
            result=analysis.analyze(settings,plan,study,registry,stage='final')
            summary=json.loads((result/'summary.json').read_text())
            self.assertEqual(summary['comparable_users'],0)
            self.assertEqual(summary['precision']['gap_evidence'],'not_estimable')
            self.assertEqual(annotations.next_batch(settings,plan,study,registry,stage='final')['status'],'fixed_user_scope_reached')

    def test_cannot_set_ceiling_below_allocated_or_above_frame(self):
        with tempfile.TemporaryDirectory() as t:
            s,p,_,d,r=fixtures.PublicationTests().freeze_fixture(Path(t));p['comparable_users']=800
            annotations.next_batch(s,p,d,r);fixtures.PublicationTests().proposals(d,'cohort_0001',r)
            annotations.next_batch(s,p,d,r)
            with self.assertRaises(ValueError):fixed_scope.enable(d,1,1)
            with self.assertRaises(ValueError):fixed_scope.enable(d,3,1)

if __name__=='__main__':unittest.main()
