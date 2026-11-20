"""Scientific invariants and resumable publication workflow on isolated fixtures."""
import copy
import io
import json
import tarfile
import tempfile
import unittest
import sys
import types
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from polarization_pipeline.targeted.common import atomic_json, read_csv, sha256
from polarization_pipeline.targeted.registry import registry_fingerprint
from polarization_pipeline.targeted.publication import annotations, analysis, benchmark, data, remote, training
from polarization_pipeline.targeted.publication.state import seal, verify
from test_targeted import PERIODS, registry, settings, video


class PublicationTests(unittest.TestCase):
    def test_training_report_uses_saved_thresholds_and_explicit_coverage_denominator(self):
        from polarization_pipeline.targeted.publication.training_report import summarize
        logits = np.array([[8., 0., 0., 0., 0.], [0., 8., 0., 0., 0.], [0., 0., 8., 0., 0.], [8., 0., 0., 0., 0.]])
        calibration = dict(temperature=1., thresholds=dict(positive=.5, negative=1.01, neutral=.5, mixed=1.01, not_evaluable=1.01))
        result = summarize(["positive", "negative", "neutral", "not_evaluable"], [1., 2., 3., 4.], [logits]*3, calibration)
        self.assertAlmostEqual(result["candidate_pair_coverage"], .8)
        self.assertAlmostEqual(result["evaluable_candidate_coverage"], 4/6)
        self.assertAlmostEqual(result["classes"]["positive"]["precision"], .2)
        self.assertIsNone(result["classes"]["negative"]["precision"])
        self.assertEqual(result["abstained_pairs"], 1)

    def test_training_report_rejects_missing_seeds_or_nonfinite_logits(self):
        from polarization_pipeline.targeted.publication.training_report import summarize
        calibration = dict(temperature=1., thresholds={label: .5 for label in ("positive", "negative", "neutral", "mixed", "not_evaluable")})
        with self.assertRaises(ValueError):
            summarize(["positive"], [1.], [np.zeros((1, 5))]*2, calibration)
        with self.assertRaises(ValueError):
            summarize(["positive"], [1.], [np.full((1, 5), np.nan)]*3, calibration)

    def test_training_report_aligns_common_pairs_and_preserves_sealed_artifacts(self):
        from polarization_pipeline.targeted.publication.training_report import report, summarize
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, parent, study, reg = self.fixture(Path(tmp))
            source, trained = study / "training_input", study / "training"
            source.mkdir(); trained.mkdir()
            pd.DataFrame([dict(comment_id="a", target_id="a", split="validation", label="positive", weight=1),
                          dict(comment_id="b", target_id="b", split="validation", label="negative", weight=2)]).to_csv(source / "validation.csv", index=False)
            seal(source, ["validation.csv"])
            pd.DataFrame([dict(comment_id="b", target_id="b"), dict(comment_id="a", target_id="a")]).to_csv(trained / "shared_validation_pairs.csv", index=False)
            atomic_json(trained / "common_context.json", dict(train_shared=2, train_total=2, validation_shared=2, validation_total=2))
            logits = np.array([[0., 8., 0., 0., 0.], [8., 0., 0., 0., 0.]])
            calibration = dict(temperature=1., thresholds={label: .5 for label in ("positive", "negative", "neutral", "mixed", "not_evaluable")})
            metrics = summarize(["negative", "positive"], [2., 1.], [logits]*3, calibration)["metrics"]
            models = []
            for name in ("robertuito", "beto", "bertin", "xlm_roberta"):
                folder = trained / name / "model"; folder.mkdir(parents=True)
                for seed in (42, 43, 44):
                    np.save(folder / f"validation_logits_{seed}.npy", logits)
                atomic_json(folder / "training_manifest.json", dict(calibration=calibration, revisions=[dict(seed=s) for s in (42, 43, 44)],
                    shared_validation_pairs_sha256=sha256(trained / "shared_validation_pairs.csv")))
                models.append(dict(model_id=name, metrics=metrics))
            atomic_json(trained / "comparison.json", dict(models=models, completed_fits=12, production_enabled=False))
            seal(trained, [str(p.relative_to(trained)) for p in trained.rglob("*") if p.is_file()])
            before = sha256(trained / "manifest.json")
            destination = report(setting, study)
            result = json.loads((destination / "comparison.json").read_text())
            self.assertEqual(result["models"]["beto"]["candidate_pair_coverage"], 1.)
            self.assertEqual(result["models"]["beto"]["metrics"]["macro_f1"], 2/3)
            self.assertFalse(result["production_enabled"])
            self.assertEqual(sha256(trained / "manifest.json"), before)
            with self.assertRaises(FileExistsError):
                report(setting, study)

    def fixture(self, root):
        config = root / "publication.toml"; config.write_text("frozen")
        source = root / "source.toml"; source.write_text("source")
        previous_config = root / "parent.toml"; previous_config.write_text("parent")
        reg = root / "registry.json"
        actors = registry()
        actors["targets"].append({**actors["targets"][0], "target_id": "x", "name": "Actor X", "aliases": ["Actor X"], "target_group": "unknown"})
        actors["publication_audit"] = {"status": "complete"}
        atomic_json(reg, actors)
        parent = root / "parent"; (parent / "annotations").mkdir(parents=True)
        pd.DataFrame([dict(post_id="sealed", comment_id="sealed_c", text="Actor A sealed", split="test", annotation_json="NOT JSON")]).to_csv(parent / "annotations/sampling_manifest.csv", index=False)
        (parent / "annotations/gold.csv").write_text("sealed labels: invalid CSV; do not decode")
        (parent / "annotations/manifest.json").write_text("{}")
        rows = []
        # Two real user histories meet both structural and affective requirements.
        for uid, group in (("u1", "a"), ("u2", "b")):
            opposite = "b" if group == "a" else "a"
            for i, (fold, target, label) in enumerate((("A", group, "positive"), ("A", group, "positive"),
                                                      ("B", group, "positive"), ("B", opposite, "negative"), ("B", opposite, "neutral"))):
                rows.append(dict(comment_id=f"{uid}_{i}", post_id=video(fold, i+1), user_id=uid, text="Actor "+target.upper()+" "+str(i), valence=label))
        for i, text in enumerate(("Actor A extra", "Actor B extra", "Actor X extra", "Sin candidatos")):
            rows.append(dict(comment_id=f"extra{i}", post_id=f"extra{i}", user_id="other", text=text, valence="neutral"))
        rows.append(dict(comment_id="sealed_c", post_id="sealed", user_id="sealed_user", text="Actor A sealed", valence="positive"))
        for row in rows:
            row.update(channel_id="channel", channel_handle="@fixture", channel="Fixture", party="neutral",
                       video_published_at="2026-04-01T00:00:00Z", comment_published_at="2026-04-02T00:00:00Z",
                       post_title="title", parent_id="", comment_type="top_level", corpus="main", provenance="original",
                       sentimiento="neutral")
        pd.DataFrame(rows).to_csv(parent / "corpus_main.csv", index=False)
        setting = {**settings(), "workspace": root, "outputs": root / "outputs", "_root": root,
                   "_config_path": previous_config, "registry": reg, "source_config": source,
                   "source": {"youtube": {"channels": {"neutral_local": ["@fixture"]}, "periods": PERIODS}}}
        plan = dict(seed=42, selection_seed=57, comparable_users=1, batch_users=1, benchmark_counts=[1, 1, 1, 1],
                    bootstrap_iterations=20, daily_api_budget=1, planned_design_effect=2, planned_half_width=.2)
        study = root / "study"
        data.prepare(setting, plan, parent, study, reg, config)
        return setting, plan, parent, study, reg

    def freeze_fixture(self, root):
        setting, plan, parent, study, reg = self.fixture(root)
        for row in read_csv(study / "videos.csv").to_dict("records"):
            atomic_json(study / "raw_capture" / f"{row['post_id']}.json", dict(status="complete", video=row, comments={}, finished_at="2026-11-17"))
        data.freeze(setting, plan, parent, study, reg)
        return setting, plan, parent, study, reg

    def proposals(self, study, name, reg):
        sample = read_csv(study / "annotations" / name / "sample.csv")
        batch = dict(sample_sha256=sha256(study / "annotations" / name / "sample.csv"), origin="synthetic test only", proposals=[])
        for row in sample.to_dict("records"):
            items = []
            for letter in ("A", "B", "X"):
                mention = "Actor "+letter
                if mention in row["text"]:
                    start = row["text"].index(mention)
                    items.append(dict(target_id=letter.lower(), mention_start=start, mention_end=start+len(mention), valence=row["valence"]))
            batch["proposals"].append(dict(sample_id=row["sample_id"], annotations=items, note="Synthetic unit test"))
        annotations.import_proposals(study, name, batch, reg)
        return batch

    def test_prepare_excludes_sealed_videos_without_decoding_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, parent, study, reg = self.fixture(Path(tmp))
            self.assertNotIn("sealed", set(read_csv(study / "videos.csv").post_id))
            self.assertNotIn("sealed_c", set(read_csv(study / "historical.csv").comment_id))
            self.assertFalse((parent / "model/test_opened.json").exists())
            self.assertFalse(json.loads((study / "study.json").read_text())["final_test_labels_decoded"])

    def test_freeze_rejects_partial_and_unstarted_captures(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, parent, study, reg = self.fixture(Path(tmp))
            with self.assertRaisesRegex(ValueError, "pendiente"):
                data.freeze(setting, plan, parent, study, reg)
            for v in read_csv(study / "videos.csv").post_id:
                atomic_json(study / "raw_capture" / f"{v}.json", dict(status="incomplete"))
            with self.assertRaisesRegex(ValueError, "incompleta"):
                data.freeze(setting, plan, parent, study, reg)
            self.assertFalse((study / "freeze.json").exists())

    def test_dedup_preserves_first_version_and_rejects_identity_conflicts(self):
        old = dict(comment_id="c", post_id="v", user_id="u", text="old", component="historical_main")
        new = {**old, "text": "edited", "component": "api_capture"}
        frame, versions = data.merge_comments([old], [new])
        self.assertEqual(frame.text.tolist(), ["old"])
        self.assertTrue(versions.text_changed.iloc[0])
        with self.assertRaisesRegex(ValueError, "identidad"):
            data.merge_comments([old], [{**new, "user_id": "another"}])

    def test_new_corpus_adapter_and_omitted_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, _, study, reg = self.freeze_fixture(Path(tmp))
            annotations.next_batch(setting, plan, study, reg)
            self.proposals(study, "cohort_0001", reg)
            frame = annotations.decisions(study, "cohort_0001", reg, "provisional")
            events = analysis.events_from_annotations(frame, reg)
            self.assertTrue(events.corpus.eq("publication_union").all())
            result = analysis.scores(events, setting)
            self.assertEqual(int(result.paired.sum()), 1)
            self.assertGreater(float(result.gap.iloc[0]), 0)
            self.assertEqual(annotations.next_batch(setting, plan, study, reg)["status"], "target_reached")
            with self.assertRaisesRegex(ValueError, "incompleta"):
                annotations.decisions(study, "cohort_0001", reg, "final")

    def test_proposals_never_confirm_human_and_reject_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, _, study, reg = self.freeze_fixture(Path(tmp))
            annotations.next_batch(setting, plan, study, reg)
            batch = self.proposals(study, "cohort_0001", reg)
            self.assertTrue(read_csv(study / "annotations/cohort_0001/human_review.csv").review_complete.eq("").all())
            with self.assertRaisesRegex(ValueError, "duplicado"):
                annotations.import_proposals(study, "cohort_0001", batch, reg)

    def test_blind_benchmark_reference_rejects_assisted_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, study, reg = self.freeze_fixture(Path(tmp))
            folder = annotations.init_benchmark(study)
            human = read_csv(folder / "human_review.csv")
            human["review_complete"], human["reviewer_id"], human["reviewed_at"] = "true", "test human", "2026-11-17"
            human["annotation_json"], human["decision"], human["proposal_sha256"] = "[]", "accepted", "hash"
            human.to_csv(folder / "human_review.csv", index=False)
            with self.assertRaisesRegex(ValueError, "ciega"):
                annotations.decisions(study, "benchmark", reg, "final")
            human["decision"], human["proposal_sha256"] = "blind", ""
            human.to_csv(folder / "human_review.csv", index=False)
            self.assertEqual(len(annotations.decisions(study, "benchmark", reg, "final")), 4)

    def test_frozen_inputs_tampering_and_zero_probability_strata_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, study, reg = self.freeze_fixture(Path(tmp))
            reg.write_text("changed")
            with self.assertRaisesRegex(ValueError, "protegida"):
                verify(study, frozen=True)
        frame = pd.DataFrame(dict(comment_id=["a", "b"], party=["left", "right"], month=["2026-01"]*2, comment_type=["top_level"]*2))
        with self.assertRaisesRegex(ValueError, "estratos"):
            data.proportional_sample(frame, 1, 57)
        with self.assertRaisesRegex(ValueError, "soporte"):
            data.proportional_sample(frame, 3, 57)

    def test_end_to_end_penalizes_omitted_human_target(self):
        sample = pd.DataFrame([dict(comment_id="c", post_id="v", sampling_probability=1,
            annotation_json=json.dumps([dict(target_id="a", valence="positive"), dict(target_id="b", valence="negative")]))])
        pred = pd.DataFrame([dict(comment_id="c", target_id="a", valence="positive", accepted=True, context_complete=True)])
        joined = benchmark.joined_reference(sample, pred)
        self.assertEqual(len(joined), 2)
        self.assertEqual(benchmark.measure(joined)["coverage"], .5)
        self.assertIn("omitted", set(joined.valence))

    def test_development_skips_test_json_before_decoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); reg=root/"r.json"; atomic_json(reg,registry())
            (root/"annotations").mkdir()
            rows=[]
            for split in ("train", "validation", "test"):
                rows.append(dict(sample_id=split,comment_id=split,post_id=split,text="Actor A", split=split,
                    comment_published_at="2026-04-01",sampling_probability=1,
                    annotation_json="SEALED INVALID JSON" if split=="test" else json.dumps([dict(target_id="a",valence="positive")])))
            pd.DataFrame(rows).to_csv(root/"annotations/gold.csv", index=False)
            atomic_json(root/"annotations/manifest.json",dict(status="human_reviewed_assisted",gold_sha256=sha256(root/"annotations/gold.csv"),registry_sha256=registry_fingerprint(reg)))
            gold,pairs=training.development_pairs(dict(registry=reg),root)
            self.assertEqual(set(pairs.split),{"train","validation"})
            self.assertEqual(len(gold),2)

    def test_private_payload_allowlist_and_exact_budget(self):
        import tomllib
        plan=tomllib.loads(Path('config/targeted_publication.toml').read_text())
        training.validate_plan(plan)
        changed=copy.deepcopy(plan);changed['maximum_fits']=24
        with self.assertRaises(ValueError):training.validate_plan(changed)
        self.assertEqual(len(plan['models'])*len(plan['model_seeds']),12)

    def test_archive_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            study=Path(tmp)/"study";(study/"kaggle/train").mkdir(parents=True)
            archive_path=Path(tmp)/"bad.tar.gz"
            with tarfile.open(archive_path,"w:gz") as archive:
                member=tarfile.TarInfo("../../escape");member.size=1;archive.addfile(member,io.BytesIO(b"x"))
            with self.assertRaisesRegex(ValueError,"insegura"):
                remote.import_result(study,archive_path,"train")
            self.assertFalse((Path(tmp)/"escape").exists())

    def test_training_worker_shared_pairs_and_exact_twelve_completed_fits(self):
        import tomllib
        plan=tomllib.loads(Path('config/targeted_publication.toml').read_text())
        plan['models']=[{**m,'revision':'a'*40} for m in plan['models']]
        with tempfile.TemporaryDirectory() as tmp:
            study=Path(tmp); source=study/'training_input';source.mkdir()
            rows=[dict(comment_id=str(i),post_id=str(i),target_id='a',target_name='A',text='short' if i<3 else 'LONG',
                       mention_start=0,mention_end=1,label=label,weight=1) for i,label in enumerate(['positive','negative','neutral','positive'])]
            pd.DataFrame(rows).assign(split='train').to_csv(source/'train.csv',index=False)
            pd.DataFrame([{**r,'post_id':'val'+r['post_id']} for r in rows]).assign(split='validation').to_csv(source/'validation.csv',index=False)
            atomic_json(source/'plan.json',plan);seal(source,['train.csv','validation.csv','plan.json'])
            module=types.ModuleType('transformers')
            module.AutoTokenizer=types.SimpleNamespace(from_pretrained=lambda *a,**k: types.SimpleNamespace(model_max_length=512))
            module.AutoConfig=types.SimpleNamespace(from_pretrained=lambda *a,**k: types.SimpleNamespace(max_position_embeddings=512,model_type='bert'))
            seen=[]
            def fit(setting,train,val,folder,spec,trial,recipe,seed):
                self.assertIsInstance(folder,Path)
                self.assertEqual(train.comment_id.tolist(),['0','1','2'])
                self.assertEqual(val.comment_id.tolist(),['0','1','2'])
                self.assertEqual(trial['learning_rate'],2e-5)
                checkpoint=folder/str(seed);checkpoint.mkdir();(checkpoint/'weights').write_text('synthetic test only')
                logits=np.eye(5)[:3]*5
                np.save(folder/f'validation_logits_{seed}.npy',logits)
                seen.append((spec['id'],seed))
                return {'seed':seed},logits
            with patch.dict(sys.modules,{'transformers':module}),patch.object(training,'model_frame',side_effect=lambda f,m:f),\
                 patch.object(training,'complete_context',side_effect=lambda t,f,n:f.text.ne('LONG').to_numpy()),\
                 patch.object(training,'fit_seed',side_effect=fit):
                training.train_worker(dict(quality=dict(valence_precision=.85)),study)
                training.train_worker(dict(quality=dict(valence_precision=.85)),study)
            self.assertEqual(len(seen),12)
            self.assertEqual(len(set(seen)),12)
            self.assertFalse(json.loads((study/'training/comparison.json').read_text())['production_enabled'])

    def test_benchmark_and_provisional_user_analysis_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting,plan,_,study,reg=self.freeze_fixture(Path(tmp))
            annotations.next_batch(setting,plan,study,reg);self.proposals(study,'cohort_0001',reg)
            annotations.init_benchmark(study);self.proposals(study,'benchmark',reg)
            pairs=training.prediction_pairs(study,reg);pairs.to_csv(study/'prediction_input.csv',index=False)
            training.prediction_comments(study)[['comment_id','post_id']].to_csv(study/'prediction_scope.csv',index=False)
            pred_dir=study/'predictions';pred_dir.mkdir()
            for model in benchmark.MODEL_IDS:
                preds=pairs[['sample_id','comment_id','post_id','target_id']].copy()
                preds['valence']='neutral';preds['accepted']=True;preds['context_complete']=True;preds['model_id']=model
                preds.to_csv(pred_dir/f'{model}.csv',index=False)
            seal(pred_dir,[f'{m}.csv' for m in benchmark.MODEL_IDS],prediction_input_sha256=sha256(study/'prediction_input.csv'),
                 prediction_scope_sha256=sha256(study/'prediction_scope.csv'),diagnostic_only=True)
            result=benchmark.compare(setting,plan,study,reg)
            self.assertEqual(json.loads((result/'summary.json').read_text())['reference'],'ai_proposals_agreement_only')
            self.assertTrue((result/'cohort_measurement_errors.csv').exists())
            result=analysis.analyze(setting,plan,study,reg)
            self.assertEqual(json.loads((result/'summary.json').read_text())['comparable_users'],1)
            self.assertFalse((study/'annotations/cohort_0001/reference.json').exists())

    def test_kernel_reference_uses_actual_returned_slug_without_second_push(self):
        from polarization_pipeline.targeted.remote import start_job
        with tempfile.TemporaryDirectory() as tmp:
            study=Path(tmp);folder=study/'kaggle/train';(folder/'kernel').mkdir(parents=True)
            code=folder/'kernel/kernel.py';code.write_text('pass\n')
            job=dict(published=True,started=False,expected_version=1,dataset_id='owner/data',kernel_id='owner/requested-training',kernel_sha256=sha256(code))
            atomic_json(folder/'job_manifest.json',job)
            response='Kernel version 1 successfully pushed. Please check progress at https://www.kaggle.com/code/owner/canonical-train'
            with patch('polarization_pipeline.targeted.remote.validate_job'),patch('polarization_pipeline.targeted.remote._kaggle',side_effect=[json.dumps(dict(status='ready',current_version_number=1)),response]) as mocked:
                start_job({},study,'train')
            stored=json.loads((folder/'job_manifest.json').read_text())
            self.assertEqual(stored['kernel_ref'],'owner/canonical-train/1')
            self.assertEqual(stored['kernel_id'],'owner/requested-training')
            self.assertEqual(mocked.call_count,2)
