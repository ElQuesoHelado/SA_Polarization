from __future__ import annotations

import importlib.util
import io
import json
import shutil
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import numpy as np

import test_development
from polarization_pipeline.targeted.common import atomic_json, sha256
from polarization_pipeline.targeted.development import (development_data, freeze_experiment, verify_source,
    write_diagnostics, export_experiment)
from polarization_pipeline.targeted.learning import complete_context
from polarization_pipeline.targeted.remote import prepare_job
from polarization_pipeline.targeted.targetaware import (MARKERS, marked_example, input_lengths,
    validate_plan, tune_targetaware)


class CharacterTokenizer:
    """Transparent tokens to check exact offsets, special markers, and truncation."""
    init_kwargs = {"target_representation": "marked_target_max"}
    unk_token_id = -1
    def encode(self, text, **kwargs):
        return [ord(char) for char in text]
    def convert_tokens_to_ids(self, tokens):
        return [9001 if token == MARKERS[0] else 9002 for token in tokens]
    def build_inputs_with_special_tokens(self, first, second):
        return [2] + first + [3] + second + [3]
    def create_token_type_ids_from_sequences(self, first, second):
        return [0] * (len(first) + 2) + [1] * (len(second) + 1)
    def num_special_tokens_to_add(self, **kwargs):
        return 3


class TargetAwareTests(unittest.TestCase):
    def row(self, text, mention):
        start = text.index(mention)
        return {"text": text, "target_name": mention, "mention_start": start, "mention_end": start + len(mention)}

    def fixture(self, directory):
        case = test_development.DevelopmentTests()
        settings, run = case.fixture(directory)
        parent = case.freeze(settings, run)
        gold, pairs = development_data(settings, run)
        gold, pairs = gold.loc[gold.split.eq("validation")], pairs.loc[pairs.split.eq("validation")]
        predicted = pairs.assign(valence="positive", accepted=False, confidence=0.7, context_windowed=False)
        calibration = {"thresholds": dict.fromkeys(["positive", "negative", "neutral", "mixed", "not_evaluable"], 1.01)}
        write_diagnostics(settings, gold, predicted, parent / "baseline", calibration, 128, 0.5)
        atomic_json(parent / "baseline/manifest.json", {"final_test_evaluated": False})
        shutil.copytree(parent / "baseline", parent / "finalists/beto")
        atomic_json(parent / "selection.json", {"fits_completed": 12, "final_test_evaluated": False})
        export_experiment(settings, run, parent.name, "tune")
        atomic_json(parent / "import_tune.json", {"final_test_evaluated": False})
        training_config = directory / "targetaware.toml"
        template = (settings["_root"] / "config/targeted_targetaware.toml").read_text()
        training_config.write_text(template.replace('"development_20261115_v1"', '"test_comparison"'))
        root = freeze_experiment(settings, run, "marked_experiment", training_config)
        return settings, run, root, training_config

    def test_marks_automatic_unicode_offsets_and_ignores_human_positions(self):
        tokenizer = CharacterTokenizer()
        row = self.row("🙂 apoyo a Sa\u0301nchez y rechazo a Luis", "Sa\u0301nchez")
        example = marked_example(tokenizer, row)
        selected = [token for token, mask in zip(example["input_ids"], example["target_mask"]) if mask]
        self.assertEqual(selected, tokenizer.encode(row["target_name"]))
        self.assertEqual(example, marked_example(tokenizer, {**row, "annotation_json": '[{"mention_start":0,"mention_end":1}]'}))

    def test_switching_target_changes_markers_and_mask_without_removing_other_actor(self):
        tokenizer = CharacterTokenizer(); text = "Ana apoya a Luis y Ana critica a Pedro."
        ana = marked_example(tokenizer, self.row(text, "Ana"))
        luis = marked_example(tokenizer, self.row(text, "Luis"))
        self.assertNotEqual(ana["target_mask"], luis["target_mask"])
        self.assertNotEqual(ana["input_ids"], luis["input_ids"])
        self.assertEqual(sum(ana["target_mask"]), 3)
        opening = ana["input_ids"].index(9001)
        self.assertEqual(ana["input_ids"][opening + 1:opening + 4], tokenizer.encode("Ana"))

    def test_literal_markers_do_not_steal_target_mask(self):
        tokenizer = CharacterTokenizer()
        example = marked_example(tokenizer, self.row("[TGT] no es Ana [/TGT]", "Ana"))
        self.assertEqual([i for i, m in zip(example["input_ids"], example["target_mask"]) if m], tokenizer.encode("Ana"))

    def test_lengths_include_markers_and_long_context_remains_ineligible(self):
        import pandas as pd
        tokenizer = CharacterTokenizer()
        row = self.row("x" * 400 + " Ana " + "y" * 400, "Ana")
        frame = pd.DataFrame([row])
        self.assertEqual(input_lengths(tokenizer, frame)[0], len(row["text"]) + len("Ana") + 5)
        self.assertFalse(complete_context(tokenizer, frame, 512)[0])
        diagnostic = marked_example(tokenizer, row, 512)
        self.assertLessEqual(len(diagnostic["input_ids"]), 512)
        self.assertEqual(sum(diagnostic["target_mask"]), 3)

    def test_invalid_spans_fail_before_encoding(self):
        row = self.row("Ana", "Ana")
        for start, end in [(-1, 2), (0, 4), (2, 2)]:
            with self.assertRaisesRegex(ValueError, "Offsets"):
                marked_example(CharacterTokenizer(), {**row, "mention_start": start, "mention_end": end})

    def test_parent_reports_are_bound_and_changed_references_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            settings, run, root, _ = self.fixture(Path(directory))
            source = json.loads((root / "source.json").read_text())
            self.assertTrue(source["parent_reference"]["files"])
            (root / "reference_beto/validation_report.json").write_text("altered")
            with self.assertRaisesRegex(ValueError, "padre alterada"):
                verify_source(settings, run, root)

    def test_new_protocol_requires_six_fits_and_frozen_model_revision(self):
        import tomllib
        plan = tomllib.loads(Path("config/targeted_targetaware.toml").read_text())
        validate_plan(plan)
        with self.assertRaisesRegex(ValueError, "seis ajustes"):
            validate_plan({**plan, "maximum_fits": 7})
        plan["models"][0]["revision"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "revisión"):
            validate_plan(plan)

    def test_payload_reuses_parent_reports_without_weights_or_reserved_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            settings, run, root, training_config = self.fixture(Path(directory))
            human_hash = sha256(run / "annotations/human_review.csv")
            stage = prepare_job(settings, run, "tune", experiment_id=root.name, training_config=training_config)
            with tarfile.open(stage / "dataset/targeted_payload.tar.gz") as archive:
                import pandas as pd
                gold = pd.read_csv(archive.extractfile("run/annotations/gold.csv"), dtype=str)
                names = archive.getnames()
                self.assertEqual(set(gold.split), {"train", "validation"})
                self.assertTrue(any("reference_beto/validation_predictions.csv" in name for name in names))
                self.assertFalse(any("safetensors" in name or "human_review.csv" in name or "corpus_main.csv" in name for name in names))
                remote = Path(directory) / "remote"
                archive.extractall(remote, filter="data")
            remote_settings = {**settings, "registry": remote / "config/political_targets.json"}
            verify_source(remote_settings, remote / "run", remote / "run/experiments" / root.name)
            self.assertEqual(human_hash, sha256(run / "annotations/human_review.csv"))
            self.assertFalse((run / "model/test_opened.json").exists())

    def test_six_fit_schedule_and_no_repeat_after_start(self):
        with tempfile.TemporaryDirectory() as directory:
            settings, run, root, _ = self.fixture(Path(directory))
            gold, pairs = development_data(settings, run)
            plan, source = [json.loads((root / name).read_text()) for name in ["plan.json", "source.json"]]
            def fit(*args):
                return {"seed": args[-1]}, np.zeros((1, 5))
            def finish(*args):
                path = args[3];path.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / "reference_beto/validation_predictions.csv", path / "validation_predictions.csv")
                return {"ready_for_reserved_test": False, "raw": {"macro_f1": 0.4}, "coverage": 0.1, "weighted_loss": 1.0}
            with patch("polarization_pipeline.targeted.development.verify_accumulation"), patch("polarization_pipeline.targeted.target_selftest.verify_target_models"), patch("polarization_pipeline.targeted.development.fit_seed", side_effect=fit) as fits, patch("polarization_pipeline.targeted.development.finish_model", side_effect=finish), redirect_stdout(io.StringIO()):
                tune_targetaware(settings, run, root, gold, pairs, plan, source)
                self.assertEqual(fits.call_count, 6)
                self.assertEqual([call.args[-1] for call in fits.call_args_list], [42, 43, 44, 42, 43, 44])
                selection = json.loads((root / "selection.json").read_text())
                self.assertIsNone(selection["selected"])
                self.assertFalse(selection["final_test_evaluated"])
                with self.assertRaisesRegex(ValueError, "ya se inició"):
                    tune_targetaware(settings, run, root, gold, pairs, plan, source)

    @unittest.skipUnless(importlib.util.find_spec("torch") and importlib.util.find_spec("transformers"), "requiere extra torch/transformers")
    def test_actual_torch_checkpoint_roundtrip_batching_and_gradients(self):
        from polarization_pipeline.targeted.target_selftest import verify_target_models
        with redirect_stdout(io.StringIO()):
            verify_target_models()


if __name__ == "__main__":
    unittest.main()
