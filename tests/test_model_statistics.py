"""Common-panel bootstrap preserves the sample and immutable source reports."""
import tempfile
import unittest
from pathlib import Path
import pandas as pd

from polarization_pipeline.targeted.common import sha256
from polarization_pipeline.targeted.publication.state import seal, verify_seal
from polarization_pipeline.targeted.publication import model_statistics as stats


class ModelStatisticsTests(unittest.TestCase):
    def fixture(self, root):
        report=root/'report';report.mkdir()
        sample=root/'sample.csv'
        pd.DataFrame(dict(comment_id=['a','b','c','d'],post_id=['v1','v2','v2','v3'])).to_csv(sample,index=False)
        rows=[]
        for model in stats.MODELS:
            frame=pd.DataFrame(dict(comment_id=['a','b','c','d'],target_id=['t']*4,
                post_id=['v1','v2','v2','v3'],label=['positive','negative','neutral','positive'],
                valence=['positive','negative','neutral','omitted'],weight=[1.,3.,2.,4.],
                context_complete=[True,model!='mdeberta_v3',True,False],candidate_present=[True,True,True,False]))
            frame.to_csv(report/f'{model}_pairs.csv',index=False)
            rows.append(dict(model_id=model,panel='common_complete_candidates',pairs=2,macro_f1=2/3))
        pd.DataFrame(rows).to_csv(report/'comparison.csv',index=False)
        seal(report,['comparison.csv',*[f'{m}_pairs.csv' for m in stats.MODELS]])
        return report,sample

    def test_intersection_reproduces_point_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            report,sample=self.fixture(Path(tmp));before=sha256(report/'manifest.json')
            result=stats.prepare(report,sample,iterations=20)
            ci=stats.intervals(report)
            self.assertEqual(set(ci.model_id),set(stats.MODELS))
            self.assertTrue(ci.estimate.astype(float).sub(2/3).abs().lt(1e-12).all())
            self.assertTrue(ci.ci_low.astype(float).between(0,1).all())
            self.assertTrue(ci.ci_high.astype(float).between(0,1).all())
            self.assertEqual(sha256(report/'manifest.json'),before);verify_seal(report)
            self.assertEqual(stats.prepare(report,sample,iterations=20),result)
            with self.assertRaises(ValueError):stats.prepare(report,sample,seed=43,iterations=20)

    def test_same_seed_is_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'a').mkdir();(root/'b').mkdir()
            a,sa=self.fixture(root/'a');b,sb=self.fixture(root/'b')
            stats.prepare(a,sa,iterations=20);stats.prepare(b,sb,iterations=20)
            pd.testing.assert_frame_equal(stats.intervals(a),stats.intervals(b))

    def test_tampering_or_point_mismatch_is_rejected(self):
        for kind in ['tamper','wrong_panel','wrong_video']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                report,sample=self.fixture(Path(tmp))
                if kind=='tamper':(report/'beto_pairs.csv').write_text('altered')
                elif kind=='wrong_panel':
                    f=pd.read_csv(report/'comparison.csv');f.loc[0,'macro_f1']=.5
                    f.to_csv(report/'comparison.csv',index=False)
                    seal(report,['comparison.csv',*[f'{m}_pairs.csv' for m in stats.MODELS]])
                else:
                    f=pd.read_csv(sample);f.loc[0,'post_id']='another_video';f.to_csv(sample,index=False)
                with self.assertRaises(ValueError):stats.prepare(report,sample,iterations=20)
                self.assertFalse((report.parent/'manuscript_statistics').exists())
