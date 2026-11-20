from __future__ import annotations

import io
import json
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

import test_assisted
from polarization_pipeline.targeted.assisted import initialize, import_review
from polarization_pipeline.targeted.common import atomic_json, config, read_csv, sha256
from polarization_pipeline.targeted.development import (development_data, experiment_directory, freeze_experiment,
    loss_weights, maximum_length, rank_report, write_diagnostics, export_experiment)
from polarization_pipeline.targeted.remote import prepare_job, import_job, job_stage, start_job, KERNEL


class DevelopmentTests(unittest.TestCase):
    def fixture(self, root):
        case = test_assisted.AssistedTests()
        run, annotation_settings = case.fixture(root)
        initialize(annotation_settings, run)
        case.proposals(run, annotation_settings)
        case.review_all(run, annotation_settings)
        with redirect_stdout(io.StringIO()):
            import_review(annotation_settings, run, pilot_only=True)
        import_review(annotation_settings, run)
        settings = config("config/targeted_v2.toml")
        settings["registry"] = annotation_settings["registry"]
        atomic_json(run / "model/calibration.json", {"thresholds": {label: 1.01 for label in ["positive", "negative", "neutral", "mixed", "not_evaluable"]}})
        atomic_json(run / "model/training_manifest.json", {"checkpoint_hashes": {"calibration.json": sha256(run / "model/calibration.json")}})
        return settings, run

    def freeze(self, settings, run):
        with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps({"sha": "a" * 40}).encode())):
            return freeze_experiment(settings, run, "test_comparison", settings["_root"] / "config/targeted_training.toml")

    def test_length_capacity_is_architecture_specific(self):
        tokenizer = SimpleNamespace(model_max_length=10**30)
        roberta = SimpleNamespace(model_type="roberta", max_position_embeddings=130, pad_token_id=1)
        bert = SimpleNamespace(model_type="bert", max_position_embeddings=512, pad_token_id=1)
        self.assertEqual(maximum_length(roberta, tokenizer, 512), 128)
        self.assertEqual(maximum_length(bert, tokenizer, 512), 512)

    def test_objectives_normalize_training_only_and_do_not_combine_weights(self):
        frame = pd.DataFrame({"label": ["negative", "negative", "positive"], "weight": [1.0, 3.0, 8.0]})
        balanced = loss_weights(frame, "class_balanced")
        sampled = loss_weights(frame, "sampling_weighted")
        self.assertAlmostEqual(balanced.mean(), 1)
        self.assertAlmostEqual(sampled.mean(), 1)
        self.assertEqual(balanced[0], balanced[1])
        self.assertAlmostEqual(sampled[2] / sampled[0], 8)
        with self.assertRaisesRegex(ValueError, "inválidos"):
            loss_weights(frame.assign(weight=[0, 1, 1]), "sampling_weighted")

    def test_development_excludes_reserved_targets_before_matching(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, run = self.fixture(Path(tmp))
            gold, pairs = development_data(settings, run)
            self.assertEqual(set(gold.split), {"train", "validation"})
            self.assertEqual(set(pairs.sample_id), {"s1", "s2"})
            self.assertFalse((run / "model/test_opened.json").exists())

    def test_diagnostic_is_not_final_evaluation_and_reports_disabled_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, run = self.fixture(Path(tmp))
            settings["bootstrap_iterations"] = 3
            gold, pairs = development_data(settings, run)
            gold = gold.loc[gold.split.eq("validation")]
            predicted = pairs.loc[pairs.split.eq("validation")].assign(valence="positive", accepted=False,
                confidence=0.7, context_windowed=False)
            calibration = {"thresholds": {label: 1.01 for label in ["positive", "negative", "neutral", "mixed", "not_evaluable"]}}
            report = write_diagnostics(settings, gold, predicted, run / "diagnostic", calibration, 128, 0.5)
            self.assertFalse(report["final_test_evaluated"])
            self.assertFalse(report["ready_for_reserved_test"])
            self.assertNotIn("test_comments", report)
            self.assertEqual(report["calibration_diagnosis"]["negative"], "insufficient_support")
            self.assertFalse((run / "model/evaluation.json").exists())
            with self.assertRaisesRegex(ValueError, "exclusivamente validación"):
                write_diagnostics(settings, gold.assign(split="test"), predicted, run / "bad", calibration, 128, 0.5)

    def test_search_ranking_prioritizes_eligible_models_then_f1_and_coverage(self):
        def candidate(key, ready, f1, coverage):
            return {"id": key, "report": {"ready_for_reserved_test": ready, "raw": {"macro_f1": f1}, "coverage": coverage, "weighted_loss": 0.5}}
        items = [candidate("bad", False, 0.99, 0.99), candidate("b", True, 0.8, 0.7), candidate("a", True, 0.8, 0.8)]
        self.assertEqual(sorted(items, key=rank_report)[0]["id"], "a")

    def test_changed_frozen_plan_is_rejected(self):
        from polarization_pipeline.targeted.development import verify_source
        with tempfile.TemporaryDirectory() as tmp:
            settings, run = self.fixture(Path(tmp))
            root = self.freeze(settings, run)
            plan = json.loads((root / "plan.json").read_text())
            plan["maximum_fits"] = 100
            atomic_json(root / "plan.json", plan)
            with self.assertRaisesRegex(ValueError, "desarrollo congelado"):
                verify_source(settings, run, root)

    def test_valid_import_is_isolated_from_canonical_model_and_reviews(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, run = self.fixture(Path(tmp))
            root = self.freeze(settings, run)
            old_model = sha256(run / "model/training_manifest.json")
            old_human = sha256(run / "annotations/human_review.csv")
            incoming_run = Path(tmp) / "incoming/run"
            incoming = experiment_directory(incoming_run, "test_comparison")
            incoming.mkdir(parents=True)
            for name in ("source.json", "plan.json"):
                (incoming / name).write_bytes((root / name).read_bytes())
            atomic_json(incoming / "baseline/manifest.json", {"scope": "synthetic validation"})
            export_experiment(settings, incoming_run, "test_comparison", "validate")
            archive = Path(tmp) / "result.tar.gz"
            with tarfile.open(archive, "w:gz") as handle:
                handle.add(incoming_run, arcname="run")
            import_job(settings, run, archive)
            self.assertTrue((root / "baseline/manifest.json").exists())
            self.assertEqual(old_model, sha256(run / "model/training_manifest.json"))
            self.assertEqual(old_human, sha256(run / "annotations/human_review.csv"))
            self.assertFalse((run / "model/test_opened.json").exists())

    def test_experiment_and_job_paths_cannot_redirect_reserved_test(self):
        with self.assertRaises(ValueError):
            experiment_directory(Path("run"), "../model")
        with self.assertRaises(ValueError):
            job_stage(Path("run"), "evaluate", "comparison")
        with self.assertRaises(ValueError):
            job_stage(Path("run"), "tune")
        self.assertEqual(job_stage(Path("run"), "train"), Path("run/kaggle/train"))

    def test_diagnostic_payload_withholds_all_reserved_labels_and_source_forms(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, run = self.fixture(Path(tmp))
            self.freeze(settings, run)
            human_before = sha256(run / "annotations/human_review.csv")
            stage = prepare_job(settings, run, "validate", experiment_id="test_comparison")
            with tarfile.open(stage / "dataset/targeted_payload.tar.gz") as archive:
                names = archive.getnames()
                self.assertNotIn("run/corpus_main.csv", names)
                self.assertFalse(any("human_review" in name or "inheritance_source" in name for name in names))
                frame = pd.read_csv(archive.extractfile("run/annotations/gold.csv"), dtype=str)
                self.assertNotIn("test", set(frame.split))
                destination = Path(tmp) / "remote"
                archive.extractall(destination, filter="data")
            remote_settings = {**settings, "registry": destination / "config/political_targets.json"}
            gold, pairs = development_data(remote_settings, destination / "run")
            self.assertEqual(len(gold), 2)
            self.assertEqual(len(pairs), 2)
            self.assertEqual(human_before, sha256(run / "annotations/human_review.csv"))
            compile((stage / "kernel/kernel.py").read_text(), "kernel.py", "exec")

    def test_import_rejects_modified_artifacts_before_copying(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, run = self.fixture(Path(tmp))
            root = self.freeze(settings, run)
            original_model = sha256(run / "model/training_manifest.json")
            incoming_run = Path(tmp) / "incoming/run"
            incoming = experiment_directory(incoming_run, "test_comparison")
            incoming.mkdir(parents=True)
            for name in ("source.json", "plan.json"):
                (incoming / name).write_bytes((root / name).read_bytes())
            atomic_json(incoming / "baseline/manifest.json", {"scope": "synthetic validation"})
            export_experiment(settings, incoming_run, "test_comparison", "validate")
            (incoming / "baseline/manifest.json").write_text("tampered")
            archive = Path(tmp) / "result.tar.gz"
            with tarfile.open(archive, "w:gz") as handle:
                handle.add(incoming_run, arcname="run")
            with self.assertRaisesRegex(ValueError, "alterado"):
                import_job(settings, run, archive)
            self.assertFalse((root / "baseline").exists())
            self.assertEqual(original_model, sha256(run / "model/training_manifest.json"))

    def test_new_remote_jobs_pin_kernel_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, run = self.fixture(Path(tmp))
            self.freeze(settings, run)
            stage = prepare_job(settings, run, "validate", experiment_id="test_comparison")
            path = stage / "job_manifest.json"
            job = json.loads(path.read_text()); job.update(published=True, expected_version=2); atomic_json(path, job)
            with patch("polarization_pipeline.targeted.remote._kaggle", side_effect=[json.dumps({"status": "ready", "current_version_number": 2}), "Kernel version 2 successfully pushed."]):
                start_job(settings, run, "validate", experiment_id="test_comparison")
            self.assertTrue(json.loads(path.read_text())["kernel_ref"].endswith("/2"))


if __name__ == "__main__":
    unittest.main()
