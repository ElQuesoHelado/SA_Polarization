"""Frozen-development diagnostics and read-only evaluation gates."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import test_publication as fixtures
from polarization_pipeline.targeted.common import atomic_json, read_csv, sha256
from polarization_pipeline.targeted.learning import LABELS, classification_metrics
from polarization_pipeline.targeted.publication import annotations
from polarization_pipeline.targeted.publication.development_diagnostics import (
    align_pairs, prediction_details, scope_reference, coverage_rows, diagnose)
from polarization_pipeline.targeted.publication.evaluation_preflight import preflight, exposure_audit
from polarization_pipeline.targeted.publication.state import seal


class DiagnosticsTests(unittest.TestCase):
    def trained_fixture(self, root):
        setting, plan, parent, study, reg = fixtures.PublicationTests().fixture(root)
        rows=[]
        for cid, split, items in [
            ('train','train',[dict(target_id='a',valence='positive')]),
            ('c1','validation',[dict(target_id='a',valence='positive'),dict(target_id='b',valence='negative')]),
            ('c2','validation',[dict(target_id='a',valence='neutral')]),
            ('c3','validation',[dict(target_id='a',valence='negative')]),
            ('sealed','test',None)]:
            rows.append(dict(sample_id=cid,comment_id=cid,post_id=cid,split=split,text='Actor A '+cid,
                sampling_probability=.5,party='neutral',comment_type='top_level',comment_published_at='2026-04-01',
                annotation_json='INVALID SEALED JSON' if items is None else json.dumps(items)))
        pd.DataFrame(rows).to_csv(parent/'annotations/gold.csv',index=False)
        atomic_json(parent/'annotations/manifest.json',dict(status='human_reviewed_assisted',gold_sha256=sha256(parent/'annotations/gold.csv')))
        manifest=json.loads((study/'study.json').read_text())
        manifest['inputs'][str((parent/'annotations/gold.csv').resolve())]=sha256(parent/'annotations/gold.csv')
        manifest['inputs'][str((parent/'annotations/manifest.json').resolve())]=sha256(parent/'annotations/manifest.json')
        atomic_json(study/'study.json',manifest)
        source, trained=study/'training_input',study/'training';source.mkdir();trained.mkdir()
        pd.DataFrame([dict(comment_id='train',target_id='a',post_id='train',text='Actor A',label='positive',weight=2,split='train')]).to_csv(source/'train.csv',index=False)
        pd.DataFrame([dict(comment_id=cid,target_id='a',post_id=cid,text='Actor A '+cid,label=label,weight=2,split='validation') for cid,label in [('c1','positive'),('c2','neutral'),('c3','negative')]]).to_csv(source/'validation.csv',index=False)
        seal(source,['train.csv','validation.csv'])
        pd.DataFrame([dict(comment_id='c3',target_id='a'),dict(comment_id='c1',target_id='a')]).to_csv(trained/'shared_validation_pairs.csv',index=False)
        pd.DataFrame([dict(comment_id='train',target_id='a')]).to_csv(trained/'shared_training_pairs.csv',index=False)
        logits=np.array([[8.,0,0,0,0],[8.,0,0,0,0]])
        calibration=dict(temperature=1.,thresholds={label:.5 if label=='positive' else 1.01 for label in LABELS})
        models=[]
        for name in ['robertuito','beto','bertin','xlm_roberta']:
            folder=trained/name/'model';folder.mkdir(parents=True)
            for seed in [42,43,44]: np.save(folder/f'validation_logits_{seed}.npy',logits)
            atomic_json(folder/'training_manifest.json',dict(revisions=[dict(seed=s) for s in [42,43,44]],calibration=calibration,
                shared_validation_pairs_sha256=sha256(trained/'shared_validation_pairs.csv')))
            models.append(dict(model_id=name,metrics=classification_metrics(['negative','positive'],['positive','positive'],[2,2])))
        atomic_json(trained/'comparison.json',dict(models=models,completed_fits=12,production_enabled=False))
        seal(trained,[str(p.relative_to(trained)) for p in trained.rglob('*') if p.is_file()])
        return setting,plan,parent,study,reg

    def test_alignment_reorders_and_rejects_missing_or_duplicate_pairs(self):
        frame=pd.DataFrame([dict(comment_id='a',target_id='x',label='positive'),dict(comment_id='b',target_id='x',label='negative')])
        keys=frame[['comment_id','target_id']].iloc[::-1]
        self.assertEqual(list(align_pairs(frame,keys).label),['negative','positive'])
        with self.assertRaises(ValueError): align_pairs(frame,pd.concat([keys,keys]))
        with self.assertRaises(ValueError): align_pairs(frame,pd.DataFrame([dict(comment_id='z',target_id='x')]))

    def test_prediction_uses_fixed_threshold_and_auxiliary_not_coverage(self):
        frame=pd.DataFrame(dict(label=['positive','negative'],weight=[1,3]))
        values=np.array([[9.,0,0,0,0],[0,0,0,9.,0]])
        calibration=dict(temperature=1.,thresholds={label:.5 for label in LABELS})
        detail,result=prediction_details(frame,[values]*3,calibration)
        self.assertEqual(list(detail.status),['accepted','accepted_auxiliary'])
        self.assertEqual(result['candidate_pair_coverage'],.25)
        with self.assertRaises(ValueError): prediction_details(frame,[values]*2,calibration)
        with self.assertRaises(ValueError): prediction_details(frame,[values*np.nan]*3,calibration)
        with self.assertRaises(ValueError): prediction_details(frame.assign(weight=[0,1]),[values]*3,calibration)

    def test_diagnostic_reproduces_scores_and_counts_omissions_without_test_decode(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting,plan,parent,study,reg=self.trained_fixture(Path(tmp))
            original=sha256(parent/'annotations/gold.csv'); trained=sha256(study/'training/manifest.json')
            dest=diagnose(setting,plan,parent,study,reg)
            summary=json.loads((dest/'summary.json').read_text())
            self.assertEqual(summary['validation_human_targets'],4)
            self.assertEqual(summary['extraction_missed_targets'],1)
            self.assertEqual(summary['context_excluded_candidates'],1)
            self.assertFalse(summary['development_provenance']['test_labels_decoded'])
            breakdown=read_csv(dest/'coverage_breakdown.csv')
            self.assertEqual(sum(breakdown.loc[breakdown.model.eq('beto'),'weighted_share'].astype(float)),1.)
            inventory=read_csv(dest/'error_inventory.csv')
            self.assertNotIn('sealed',set(inventory.comment_id))
            self.assertEqual(original,sha256(parent/'annotations/gold.csv'))
            self.assertEqual(trained,sha256(study/'training/manifest.json'))
            with self.assertRaises(FileExistsError): diagnose(setting,plan,parent,study,reg)

    def test_preflight_waits_for_snapshot_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting,plan,parent,study,reg=fixtures.PublicationTests().fixture(Path(tmp))
            before={str(p):sha256(p) for p in study.rglob('*') if p.is_file()}
            result=preflight(setting,plan,study,reg)
            self.assertEqual(result['status'],'waiting_snapshot')
            self.assertFalse(result['ready_for_prediction'])
            self.assertEqual(before,{str(p):sha256(p) for p in study.rglob('*') if p.is_file()})

    def test_preflight_after_freeze_reports_missing_annotations(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting,plan,parent,study,reg=fixtures.PublicationTests().freeze_fixture(Path(tmp))
            result=preflight(setting,plan,study,reg)
            self.assertTrue(result['requirements']['snapshot_frozen'])
            self.assertFalse(result['requirements']['benchmark_initialized'])
            annotations.init_benchmark(study)
            annotations.next_batch(setting,plan,study,reg)
            result=preflight(setting,plan,study,reg)
            self.assertFalse(result['requirements']['benchmark_human_review_complete'])
            self.assertFalse(result['ready_for_final_benchmark'])

    def test_preflight_rejects_new_labels_even_before_predictions(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting,plan,parent,study,reg=fixtures.PublicationTests().freeze_fixture(Path(tmp))
            pd.DataFrame([dict(comment_id='extra0',target_id='a',post_id='extra0',label='positive')]).to_csv(study/'prediction_input.csv',index=False)
            pd.DataFrame([dict(comment_id='extra0',post_id='extra0')]).to_csv(study/'prediction_scope.csv',index=False)
            with self.assertRaisesRegex(ValueError,'etiquetas nuevas'): preflight(setting,plan,study,reg)
            frame=read_csv(study/'prediction_input.csv').drop(columns='label');frame.to_csv(study/'prediction_input.csv',index=False)
            payload=study/'kaggle/infer/payload/publication';payload.mkdir(parents=True)
            (payload/'gold.csv').write_text('forbidden synthetic file')
            with self.assertRaisesRegex(ValueError,'lista permitida'): preflight(setting,plan,study,reg)

    def test_exposure_distinguishes_recorded_and_potential_overlap(self):
        sample=pd.DataFrame([dict(sample_id='s',comment_id='same',text='Same text')])
        form=pd.DataFrame([dict(sample_id='s',review_complete='true',reviewer_id='human',reviewed_at='2026-11-18T10:00:00Z')])
        benchmark=pd.DataFrame([dict(comment_id='other',text='Same text',reviewer_id='human',reviewed_at='2026-11-18T11:00:00Z')])
        result=exposure_audit(benchmark,[('cohort_0001',sample,form)])
        self.assertEqual(result['recorded_prior_exposure'],1)
        result=exposure_audit(benchmark.drop(columns='reviewed_at'),[('cohort_0001',sample,form)])
        self.assertEqual(result['recorded_prior_exposure'],0)
        self.assertEqual(result['potential_exposure_unknown'],1)

    def test_preflight_rejects_zero_probability(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting,plan,parent,study,reg=fixtures.PublicationTests().freeze_fixture(Path(tmp))
            sample=read_csv(study/'benchmark.csv'); sample.loc[0,'sampling_probability']='0'
            sample.to_csv(study/'benchmark.csv',index=False)
            freeze=json.loads((study/'freeze.json').read_text());freeze['files']['benchmark.csv']=sha256(study/'benchmark.csv')
            atomic_json(study/'freeze.json',freeze)
            with self.assertRaisesRegex(ValueError,'Probabilidades'): preflight(setting,plan,study,reg)

    def test_preflight_rejects_incomplete_predictions_and_accepts_complete_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting,plan,parent,study,reg=fixtures.PublicationTests().freeze_fixture(Path(tmp))
            annotations.init_benchmark(study);annotations.next_batch(setting,plan,study,reg)
            (study/'training_input').mkdir();seal(study/'training_input',[])
            (study/'training').mkdir();atomic_json(study/'training/comparison.json',dict(completed_fits=12,production_enabled=False))
            seal(study/'training',['comparison.json'])
            samples=[read_csv(study/'benchmark.csv'),read_csv(study/'annotations/cohort_0001/sample.csv')]
            wanted=pd.concat(samples).drop_duplicates('comment_id')
            inputs=wanted[['comment_id','post_id']].assign(target_id='a')
            inputs.to_csv(study/'prediction_input.csv',index=False)
            wanted[['comment_id','post_id']].to_csv(study/'prediction_scope.csv',index=False)
            folder=study/'predictions';folder.mkdir()
            models=['robertuito','beto','bertin','xlm_roberta']
            for model in models:
                frame=inputs.assign(model_id=model)
                (frame.iloc[:-1] if model=='beto' else frame).to_csv(folder/f'{model}.csv',index=False)
            def close():
                seal(folder,[f'{m}.csv' for m in models],diagnostic_only=True,
                     prediction_input_sha256=sha256(study/'prediction_input.csv'),prediction_scope_sha256=sha256(study/'prediction_scope.csv'),
                     training_sha256=sha256(study/'training/manifest.json'))
            close()
            with self.assertRaisesRegex(ValueError,'incompletas'):preflight(setting,plan,study,reg)
            inputs.assign(model_id='beto').to_csv(folder/'beto.csv',index=False);close()
            result=preflight(setting,plan,study,reg)
            self.assertTrue(result['ready_for_prediction'])
            self.assertTrue(result['requirements']['prediction_scope_complete'])
            self.assertFalse(result['ready_for_final_benchmark'])
            batch=fixtures.PublicationTests().proposals(study,'benchmark',reg)
            proposals={r['sample_id']:r['annotations'] for r in batch['proposals']}
            form=read_csv(study/'annotations/benchmark/human_review.csv')
            form['annotation_json']=form.sample_id.map(lambda k:json.dumps(proposals[k]))
            form['review_complete']='true';form['reviewer_id']='synthetic-reviewer'
            form['reviewed_at']='2026-11-18T10:00:00Z';form['decision']='blind'
            form.to_csv(study/'annotations/benchmark/human_review.csv',index=False)
            result=preflight(setting,plan,study,reg)
            self.assertTrue(result['requirements']['benchmark_human_review_complete'])
            self.assertFalse(result['requirements']['cohort_human_review_complete'])
            self.assertFalse(result['ready_for_final_benchmark'])
            self.assertFalse(result['ready_for_provisional_benchmark'])
