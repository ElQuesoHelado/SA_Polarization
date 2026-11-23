import itertools
import unittest
import numpy as np
import pandas as pd

from polarization_pipeline.targeted.metrics import user_scores, partition_videos
from polarization_pipeline.targeted.publication.observational import EventScores, adverse_curve, interval, trimmed
from test_targeted import video


SETTINGS=dict(affinity_positive_share=2/3,minimum_positive_videos=2,evaluation_min_interactions=3,evaluation_min_videos=2)


def event(user,fold,i,group,valence,channel='c'):
    return dict(user_id=user,post_id=video(fold,i),comment_id=f'{user}-{fold}-{i}-{group}',target_group=group,
                valence=valence,channel_id=channel,party='neutral',corpus='main',comment_published_at='2026-04-01T00:00:00Z')


class ObservationalTests(unittest.TestCase):
    def frame(self):
        rows=[]
        for uid,own,other in [('u','izquierda','derecha'),('v','derecha','izquierda')]:
            rows.extend([event(uid,'A',1,own,'positive'),event(uid,'A',2,own,'positive'),
                         event(uid,'B',3,own,'positive'),event(uid,'B',4,other,'negative'),
                         event(uid,'B',5,other,'neutral')])
        return pd.DataFrame(rows)

    def test_vectorized_score_matches_existing_rule_including_channel_weights_and_balance(self):
        rng=np.random.default_rng(7);frame=self.frame()
        extras=[]
        for i in range(150):
            extras.append(event('u' if i%2 else 'v','A' if i%3 else 'B',i+10,
                'izquierda' if i%4 else 'derecha',rng.choice(['positive','negative','neutral','mixed']),
                'c' if i%5 else 'other'))
        frame=pd.concat([frame,pd.DataFrame(extras)],ignore_index=True)
        scorer=EventScores(frame,['u','v'],['c','other'])
        for reverse,balance,weights in itertools.product((False,True),(False,True),(None,{'c':2,'other':0})):
            expected=user_scores(frame,SETTINGS,reverse=reverse,balance_unit='post_id' if balance else None,channel_weights=weights).set_index('user_id')
            actual=scorer.score(None if weights is None else [2,0],reverse=reverse,balanced=balance).set_index('user_id')
            for column in ('AP_In','AP_Out','AP_target','spread','gap','N_in','N_out','evaluation_interactions','evaluation_videos'):
                np.testing.assert_allclose(actual[column],expected.loc[actual.index,column],equal_nan=True,atol=1e-12,err_msg=column)
            self.assertEqual(actual.paired.tolist(),expected.loc[actual.index,'paired'].tolist())

    def test_manual_gap_and_neutral_denominator(self):
        frame=self.frame();scorer=EventScores(frame,['u','v'],['c'])
        primary=scorer.score()
        self.assertTrue(primary.paired.all());self.assertTrue(primary.gap.eq(1.5).all())
        self.assertTrue(scorer.score(neutral_denominator=False).gap.eq(2).all())
        self.assertFalse(scorer.score(min_per_block=2).paired.any())

    def test_no_neutral_denominator_does_not_invent_values_for_empty_block(self):
        frame=self.frame();frame.loc[(frame.user_id=='u')&frame.valence.eq('negative'),'valence']='neutral'
        scorer=EventScores(frame,['u','v'],['c'])
        self.assertTrue(scorer.score().iloc[0].paired)
        self.assertFalse(scorer.score(neutral_denominator=False).iloc[0].paired)
        self.assertTrue(np.isnan(scorer.score(neutral_denominator=False).iloc[0].gap))

    def test_stricter_affinity_rechecks_eligibility(self):
        scorer=EventScores(self.frame(),['u','v'],['c'])
        self.assertTrue(scorer.score().paired.all())
        self.assertFalse(scorer.score(min_positive=3).paired.any())
        empty=EventScores(self.frame().iloc[:0],['u','v'],['c']).score()
        self.assertFalse(empty.paired.any());self.assertTrue(empty.gap.isna().all())

    def test_adverse_bound_matches_bruteforce_for_one_changed_event(self):
        frame=self.frame();scorer=EventScores(frame,['u','v'],['c']);primary=scorer.score()
        b=frame.loc[partition_videos(frame).eq('B')].index
        observed=[]
        for i in b:
            for label in ('positive','negative','neutral'):
                changed=frame.copy();changed.loc[i,'valence']=label
                observed.append(EventScores(changed,['u','v'],['c']).score().gap.mean())
        curve,tip=adverse_curve(scorer,primary,[0.,1/6])
        self.assertEqual(curve.iloc[1].changed_events,1)
        self.assertAlmostEqual(curve.iloc[1].worst_case_gap,min(observed))
        self.assertEqual(tip['minimum_event_changes_for_nonpositive_gap'],2)

    def test_intervals_require_valid_replicates_and_trim_handles_small_samples(self):
        self.assertEqual(interval([1,np.nan,2],3)[3],'insufficient_support')
        lo,hi,count,status=interval([1,2,3],2)
        self.assertEqual(count,3);self.assertEqual(status,'estimated');self.assertLess(lo,hi)
        self.assertEqual(trimmed([0,1,2]),1)

class DiagnosticIntegrityTests(unittest.TestCase):
    def test_configuration_cannot_select_a_favorable_subset_after_analysis(self):
        from polarization_pipeline.targeted.publication.observational import validate_config
        import tomllib
        from pathlib import Path
        cfg=tomllib.loads((Path(__file__).resolve().parents[1]/'config/targeted_observational.toml').read_text())
        validate_config(cfg,cfg['analysis_id'])
        for key,value in [('seed',43),('block_support_grid',[1,3]),('minimum_valid_fraction',.1),('trim_fraction',0)]:
            with self.subTest(key=key),self.assertRaises(ValueError):validate_config({**cfg,key:value},cfg['analysis_id'])

    def test_report_reuse_checks_current_config_and_annotations(self):
        import tempfile
        from pathlib import Path
        from polarization_pipeline.targeted.common import sha256
        from polarization_pipeline.targeted.publication.observational import verify_inputs
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);study=root/'study';study.mkdir();base=root/'base';base.mkdir()
            paths={'config':root/'config.toml','registry':root/'registry.json','freeze':study/'freeze.json','primary_manifest':base/'manifest.json','review.csv':study/'review.csv'}
            for path in paths.values():path.write_text('original')
            hashes={k:sha256(p) for k,p in paths.items()}
            verify_inputs(study,hashes,paths['config'],base,paths['registry'])
            paths['review.csv'].write_text('human changed')
            with self.assertRaises(ValueError):verify_inputs(study,hashes,paths['config'],base,paths['registry'])

    def test_final_stage_stops_before_loading_data(self):
        from polarization_pipeline.targeted.publication.observational import run
        with self.assertRaises(ValueError):run({},None,None,None,'x',stage='final')
