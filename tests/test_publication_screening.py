"""Exact rejection certificates must preserve full-history user selection."""
import itertools
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import test_publication as fixtures
from polarization_pipeline.targeted.common import atomic_json, read_csv, sha256
from polarization_pipeline.targeted.publication import annotations, analysis, screening, training
from polarization_pipeline.targeted.publication.prediction_scope import benchmark_view
from polarization_pipeline.targeted.publication.state import seal
from polarization_pipeline.targeted.metrics import partition_videos
from test_targeted import registry as registry_fixture, settings, video


class ScreeningTests(unittest.TestCase):
    def fixture(self,root):
        reg=root/'registry.json';atomic_json(reg,registry_fixture())
        rows=[]
        for u in range(24):
            for j in range(9):
                fold='A' if j<6 else 'B'
                rows.append(dict(sample_id=f'{u}_{j}',comment_id=f'{u}_{j}',user_id=f'u{u}',
                    post_id=video(fold, j if j<3 else 3 if j<6 else j), text='Actor A Actor B',
                    channel_id='channel',party='neutral',comment_published_at='2026-04-02',corpus='main'))
        f=pd.DataFrame(rows);f['fold']=partition_videos(f,42)
        return settings(),reg,f

    def item(self,target,label='positive'):
        return dict(target_id=target,valence=label,mention_start=0 if target=='a' else 8,mention_end=7 if target=='a' else 15)

    def test_sequential_matches_full_selection_and_never_labels_skips(self):
        with tempfile.TemporaryDirectory() as tmp:
            s,r,f=self.fixture(Path(tmp));rng=np.random.default_rng(42)
            truth={row.sample_id:([self.item('a',rng.choice(['positive','negative','neutral'])),self.item('b',rng.choice(['positive','negative','neutral']))]) for row in f.itertuples()}
            known={}
            for _ in range(len(f)+1):
                result=screening.assess(f,known,r,s)
                if result['complete']:break
                for sid in result['required_sample_ids']:known[sid]=truth[sid]
            self.assertTrue(result['complete']);self.assertLess(len(known),len(f))
            def score(values):
                a=f.assign(annotation_json=f.sample_id.map(lambda sid:json.dumps(values[sid]) if sid in values else None))
                return analysis.scores(analysis.events_from_annotations(a,r),s).set_index('user_id')
            full=score(truth);fast=score(known).reindex(full.index)
            self.assertEqual(full.paired.tolist(),fast.paired.eq(True).tolist())
            primary=set(full.loc[full.paired].index)
            self.assertTrue(all(sid in known for sid in f.loc[f.user_id.isin(primary),'sample_id']))
            for metric in ['gap','AP_target','spread']:
                np.testing.assert_allclose(full.loc[list(primary),metric],fast.loc[list(primary),metric],equal_nan=True)
            self.assertTrue(set(result['skipped_sample_ids']).isdisjoint(known))

    def test_exclusion_bound_holds_for_every_possible_unread_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            s,r,f=self.fixture(Path(tmp));f=f.loc[f.user_id.eq('u0')].copy()
            # The two first single-comment videos have no positive; all remaining A is one video.
            known={f.iloc[i].sample_id:[] for i in [0,1,2]}
            result=screening.assess(f,known,r,s)
            self.assertEqual(result['users'][0]['status'],'excluded_affinity')
            unread=f.loc[f.fold.eq('A')&~f.sample_id.isin(known),'sample_id'].tolist()
            options=[[],[self.item('a')],[self.item('b')],[self.item('a'),self.item('b')]]
            for choices in itertools.product(options,repeat=len(unread)):
                filled={**known,**dict(zip(unread,choices))}
                self.assertEqual(screening.assess(f,filled,r,s)['users'][0]['status'],'excluded_affinity')

    def test_human_correction_reopens_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            s,r,f=self.fixture(Path(tmp));f=f.loc[f.user_id.eq('u0')].copy()
            a=f.loc[f.fold.eq('A')];known={sid:[] for sid in a.sample_id}
            self.assertTrue(screening.assess(f,known,r,s)['complete'])
            for sid in a.iloc[:2].sample_id:known[sid]=[self.item('a')]
            result=screening.assess(f,known,r,s)
            self.assertFalse(result['complete']);self.assertEqual(result['users'][0]['status'],'waiting_evaluation')
            self.assertEqual(set(result['required_sample_ids']),set(f.loc[f.fold.eq('B'),'sample_id']))

    def test_mixed_collapse_and_missing_target_hints_cannot_exclude(self):
        with tempfile.TemporaryDirectory() as tmp:
            s,r,f=self.fixture(Path(tmp));f=f.loc[f.user_id.eq('u0')].copy();f['candidates_json']='[]'
            result=screening.assess(f,{},r,s)
            self.assertEqual(result['users'][0]['status'],'waiting_affinity')
            known={sid:[self.item('a','mixed')] for sid in f.loc[f.fold.eq('A'),'sample_id']}
            self.assertEqual(screening.assess(f,known,r,s)['users'][0]['positive_counts']['izquierda'],0)
            self.assertTrue(screening.assess(f,known,r,s)['complete'])

    def test_policy_does_not_change_samples_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            s,p,_,d,r=fixtures.PublicationTests().freeze_fixture(Path(tmp))
            annotations.next_batch(s,p,d,r);before=sha256(d/'annotations/cohort_0001/sample.csv')
            screening.enable(s,d,r);screening.enable(s,d,r)
            self.assertEqual(before,sha256(d/'annotations/cohort_0001/sample.csv'))
            self.assertTrue(screening.enabled(d))
            (d/'affinity_screening/policy.json').write_text('{}')
            with self.assertRaises(ValueError):screening.enabled(d)

    def test_final_review_reopens_and_never_imputes_skipped_annotations(self):
        from polarization_pipeline.targeted.assisted import annotation_digest
        from polarization_pipeline.targeted.publication.evaluation_preflight import sample_readiness
        with tempfile.TemporaryDirectory() as tmp:
            s,p,_,d,r=fixtures.PublicationTests().freeze_fixture(Path(tmp))
            annotations.next_batch(s,p,d,r);fixtures.PublicationTests().proposals(d,'cohort_0001',r)
            screening.enable(s,d,r);folder=d/'annotations/cohort_0001'
            sample=read_csv(folder/'sample.csv');form=read_csv(folder/'human_review.csv')
            proposals=json.loads((folder/'ai_proposals.json').read_text())
            for i,row in sample.iterrows():
                if row.fold!='A':continue
                form.loc[i,['review_complete','annotation_json','reviewer_id','reviewed_at','decision','proposal_sha256']]=[
                    'true','[]','synthetic reviewer','2026-11-21','modified',annotation_digest(proposals[row.sample_id]['annotations'])]
            form.to_csv(folder/'human_review.csv',index=False)
            self.assertTrue(sample_readiness(d,'cohort_0001',r)[2]['human_review_complete'])
            excluded=annotations.decisions(d,'cohort_0001',r,'final')
            self.assertEqual(excluded.annotation_json.isna().sum(),3)
            self.assertTrue(excluded.affinity_excluded.all())
            initial=form.copy()
            for i,row in sample.iterrows():
                if row.fold=='A':
                    form.loc[i,'annotation_json']=json.dumps(proposals[row.sample_id]['annotations'])
                    form.loc[i,'decision']='accepted'
            form.to_csv(folder/'human_review.csv',index=False)
            self.assertFalse(sample_readiness(d,'cohort_0001',r)[2]['human_review_complete'])
            with self.assertRaisesRegex(ValueError,'incompleto'):
                annotations.decisions(d,'cohort_0001',r,'final')
            self.assertFalse((folder/'reference.json').exists())
            initial.to_csv(folder/'human_review.csv',index=False)
            annotations.close_reference(d,'cohort_0001',r)
            manifest=json.loads((folder/'reference.json').read_text())
            self.assertIn('affinity_exclusions.json',manifest['files'])
            self.assertEqual(read_csv(folder/'human_review.csv').review_complete.eq('').sum(),3)

    def test_benchmark_view_is_independent_of_pending_cohort(self):
        with tempfile.TemporaryDirectory() as tmp:
            s,p,_,d,r=fixtures.PublicationTests().freeze_fixture(Path(tmp))
            annotations.init_benchmark(d);annotations.next_batch(s,p,d,r)
            (d/'training').mkdir();atomic_json(d/'training/model.json',dict(fits=12));seal(d/'training',['model.json'])
            p['kaggle']={'inference_kernel_id':'owner/predict','dataset_id':'owner/data'}
            before=sha256(d/'training/manifest.json');view,newplan=benchmark_view(d,p,create=True)
            self.assertNotEqual(newplan['kaggle']['inference_kernel_id'],p['kaggle']['inference_kernel_id'])
            self.assertEqual(set(training.prediction_comments(view).comment_id),set(read_csv(d/'benchmark.csv').comment_id))
            self.assertFalse(list((view/'annotations').glob('cohort_*')))
            self.assertEqual(before,sha256(d/'training/manifest.json'))
            self.assertEqual(benchmark_view(d,p)[0],view)


if __name__=='__main__':unittest.main()
