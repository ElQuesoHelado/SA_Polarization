import io
import json
import shutil
import tarfile
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import test_development
from polarization_pipeline.targeted.common import LABELS, atomic_json, read_csv, sha256
from polarization_pipeline.targeted.development import development_data, export_experiment, freeze_experiment
from polarization_pipeline.targeted.refinement import (CONTROLS, check_classifier_config, validate_human_training,
    validate_plan, verify, tune)
from polarization_pipeline.targeted.remote import prepare_job


class RefinementTests(unittest.TestCase):
    def fixture(self, base):
        settings, run = test_development.DevelopmentTests().fixture(base)
        gold, pairs = development_data(settings, run)
        pairs["label_origin"] = "human_confirmed"
        parent = run / "experiments/development_ai_augmentation_v1"; parent.mkdir(parents=True)
        gold.to_csv(parent / "human_development.csv", index=False)
        pairs.to_csv(parent / "human_pairs.csv", index=False)
        manifest = json.loads((run / "annotations/manifest.json").read_text())
        atomic_json(parent / "source.json", {"study_gold_sha256": manifest["gold_sha256"],
            "registry_sha256": sha256(settings["registry"]), "development_gold_sha256": sha256(parent / "human_development.csv"),
            "quality": settings["quality"], "annotation_protocol": "ai_assisted_single_human_v1",
            "annotation_limitation": "synthetic human fixture", "sampling_probability_scope": "fixture"})
        model = parent / "finalists/beto_ai_augmented/model"; hashes = {}
        for seed in (42, 43, 44):
            folder = model / str(seed); folder.mkdir(parents=True)
            atomic_json(folder / "config.json", {"model_type": "bert", "id2label": dict(enumerate(LABELS)),
                "label2id": {v: i for i, v in enumerate(LABELS)}})
            (folder / "model.safetensors").write_bytes(b"synthetic fixture only")
            for file in folder.iterdir(): hashes[str(file.relative_to(model))] = sha256(file)
        atomic_json(model / "training_manifest.json", {"registry_sha256": sha256(settings["registry"]), "checkpoint_hashes": hashes})
        files = {str(p.relative_to(parent)): sha256(p) for p in parent.rglob("*") if p.is_file()}
        atomic_json(parent / "export_tune.json", {"files": files})
        atomic_json(parent / "execution_report.json", {"export_sha256": sha256(parent / "export_tune.json"),
            "source_sha256": sha256(parent / "source.json"), "human_final_test_evaluated": False})
        comparison = run / "experiments/development_blend_20261116_v1"; artifacts = {}
        for name in CONTROLS.values():
            folder = comparison / "candidates" / name; folder.mkdir(parents=True)
            for filename in ("validation_predictions.csv", "cross_calibrated_predictions.csv"):
                pairs.loc[pairs.split.eq("validation")].to_csv(folder / filename, index=False)
            atomic_json(folder / "reports.json", {"full_development": {}, "cross_calibrated": {}})
            artifacts.update({str(p.relative_to(comparison)): sha256(p) for p in folder.iterdir()})
        atomic_json(comparison / "execution_report.json", {"artifacts": artifacts, "final_test_evaluated": False})
        root = freeze_experiment(settings, run, "refinement_fixture", settings["_root"] / "config/targeted_human_refinement.toml")
        return settings, run, root

    def test_budget_is_fixed_and_checkpoint_labels_cannot_be_reset(self):
        plan = tomllib.loads(Path("config/targeted_human_refinement.toml").read_text()); validate_plan(plan)
        for k, v in (("maximum_fits", 6), ("maximum_epochs", 3), ("fixed_epochs", False), ("learning_rates", [1e-5])):
            with self.assertRaises(ValueError): validate_plan(plan | {k: v})
        good = {"model_type": "bert", "id2label": {str(i): l for i, l in enumerate(LABELS)}, "label2id": {l: i for i, l in enumerate(LABELS)}}
        check_classifier_config(good)
        with self.assertRaises(ValueError): check_classifier_config(good | {"id2label": {"0": "LABEL_0"}})

    def test_freeze_preserves_originals_and_human_only_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, run, root = self.fixture(Path(tmp))
            gold, pairs = verify(settings, run, root)
            self.assertTrue(gold.split.isin(["train", "validation"]).all())
            self.assertTrue(pairs.label_origin.eq("human_confirmed").all())
            validate_human_training(pairs.loc[pairs.split.eq("train")])
            with self.assertRaises(ValueError): validate_human_training(pairs.assign(label_origin="ai_auxiliary"))
            for name, digest in json.loads((root / "protected_originals.json").read_text()).items():
                self.assertEqual(sha256(Path(name)), digest)
            self.assertFalse((run / "model/test_opened.json").exists())

    def test_modified_human_data_or_warmstart_blocks_before_gpu(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, run, root = self.fixture(Path(tmp))
            path = root / "warmstart/42/model.safetensors"; path.write_bytes(b"altered")
            with self.assertRaisesRegex(ValueError, "alterada"): verify(settings, run, root)

    def test_remote_payload_contains_only_development_and_initial_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, run, root = self.fixture(Path(tmp))
            stage = prepare_job(settings, run, "tune", experiment_id=root.name,
                                training_config=settings["_root"] / "config/targeted_human_refinement.toml")
            with tarfile.open(stage / "dataset/targeted_payload.tar.gz") as archive:
                names = archive.getnames()
                self.assertTrue(any("warmstart/42/model.safetensors" in n for n in names))
                self.assertFalse(any("cohorts/" in n or "ai_annotations.json" in n or "sample.csv" in n for n in names))
                gold = archive.extractfile("run/annotations/gold.csv").read().decode()
                self.assertNotIn(",test,", gold)
                self.assertFalse(any("corpus_main.csv" in n for n in names))

    def test_export_omits_warmstart_not_final_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, run, root = self.fixture(Path(tmp))
            folder = root / "finalists/new/model/42"; folder.mkdir(parents=True)
            (folder / "model.safetensors").write_bytes(b"new fixture")
            export = json.loads(export_experiment(settings, run, root.name, "tune").read_text())
            self.assertFalse(any(n.startswith("warmstart/") for n in export["files"]))
            self.assertIn("finalists/new/model/42/model.safetensors", export["files"])

    def test_three_corresponding_seed_initializations_and_no_repeated_round(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, run, root = self.fixture(Path(tmp)); gold, pairs = verify(settings, run, root)
            plan = json.loads((root / "plan.json").read_text()); source = json.loads((root / "source.json").read_text())
            with patch("polarization_pipeline.targeted.development.verify_accumulation"), \
                 patch("polarization_pipeline.targeted.refinement.verify_fixed_training"), \
                 patch("polarization_pipeline.targeted.development.fit_seed", return_value=({}, np.zeros((1, 5)))) as fit, \
                 patch("polarization_pipeline.targeted.development.finish_model"), \
                 patch("polarization_pipeline.targeted.refinement.render"):
                tune(settings, run, root, gold, pairs, plan, source)
            self.assertEqual(fit.call_count, 3)
            for call, seed in zip(fit.call_args_list, (42, 43, 44)):
                self.assertEqual(call.kwargs["initial_checkpoint"], root / "warmstart" / str(seed))
                self.assertEqual(call.args[-1], seed)
                self.assertTrue(call.args[1].label_origin.eq("human_confirmed").all())
            self.assertEqual(json.loads((root / "progress.json").read_text())["fits_completed"], 3)
            (root / "finalists").mkdir()
            with self.assertRaisesRegex(ValueError, "No repetir"):
                tune(settings, run, root, gold, pairs, plan, source)
