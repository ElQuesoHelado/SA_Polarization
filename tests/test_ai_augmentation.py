import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from polarization_pipeline.targeted.ai_augmentation import (balanced_sample, build_augmented, import_annotations,
    validate_plan, check_separation, paired_video_bootstrap)
from polarization_pipeline.targeted.common import atomic_json, sha256
from polarization_pipeline.targeted.development import loss_weights


class AIAugmentationTests(unittest.TestCase):
    def fixture(self, root):
        matches = [{"target_id": "actor", "target_name": "Actor", "target_group": "izquierda", "entity_type": "person",
                    "mention_start": 0, "mention_end": 5, "candidate_origin": "explicit_alias"}]
        pd.DataFrame([{"sample_id": "new", "text": "Actor excelente", "comment_id": "c", "post_id": "v", "split": "train",
                      "candidates_json": json.dumps(matches)}]).to_csv(root / "sample.csv", index=False)
        atomic_json(root / "sample_manifest.json", {"sample_sha256": sha256(root / "sample.csv")})
        atomic_json(root / "ai_annotations.json", {})
        pd.DataFrame([{"sample_id": "human", "label": "positive", "split": "train", "label_origin": "human_confirmed"},
                      {"sample_id": "val", "label": "neutral", "split": "validation", "label_origin": "human_confirmed"}]).to_csv(root / "human_pairs.csv", index=False)
        return {"start": 0, "sample_sha256": sha256(root / "sample.csv"), "origin": "synthetic test AI", "note": "synthetic evidence", "labels": ["P"]}

    def test_ia_weight_is_quarter_equivalent_human_and_normalized(self):
        rows = pd.DataFrame({"label": ["positive", "positive", "negative", "positive", "negative"],
                             "label_origin": ["human_confirmed"] * 3 + ["ai_auxiliary"] * 2})
        weights = loss_weights(rows, "ai_augmented")
        self.assertAlmostEqual(weights.mean(), 1)
        self.assertAlmostEqual(weights[3] / weights[0], .25)
        self.assertAlmostEqual(weights[4] / weights[2], .25)
        # Human class frequencies, independent of the new AI frequency.
        self.assertAlmostEqual(weights[2] / weights[0], np.sqrt(2))

    def test_origin_and_unsupported_class_rejected(self):
        with self.assertRaises(ValueError):
            loss_weights(pd.DataFrame({"label": ["positive"], "label_origin": ["pretend_human"]}), "ai_augmented")
        with self.assertRaises(ValueError):
            loss_weights(pd.DataFrame({"label": ["positive", "neutral"], "label_origin": ["human_confirmed", "ai_auxiliary"]}), "ai_augmented")

    def test_sampling_exact_reproducible_and_respects_availability(self):
        frame = pd.DataFrame({"channel_id": ["large"] * 80 + ["small"] * 20, "month": ["2026-01"] * 100})
        sample = balanced_sample(frame, 40, 57)
        self.assertEqual(len(sample), 40)
        self.assertEqual(len(sample.loc[sample.channel_id.eq("small")]), 14)
        pd.testing.assert_frame_equal(sample, balanced_sample(frame, 40, 57))
        with self.assertRaises(ValueError):
            balanced_sample(frame, 101, 57)

    def test_import_is_ai_only_and_resumable_but_not_overwritable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); batch = self.fixture(root)
            self.assertEqual(import_annotations(root, batch)["annotated"], 1)
            import_annotations(root, batch)
            stored = json.loads((root / "ai_annotations.json").read_text())["new"]
            self.assertIs(stored["human_confirmed"], False)
            self.assertNotIn("review_complete", stored)
            batch["labels"] = ["N"]
            with self.assertRaisesRegex(ValueError, "sobrescribir"):
                import_annotations(root, batch)

    def test_uncertainty_excludes_pair_instead_of_neutral_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); batch = self.fixture(root); batch["labels"] = ["U"]
            import_annotations(root, batch)
            pairs, counts = build_augmented(root)
            self.assertEqual(counts["excluded_uncertain_pairs"], 1)
            self.assertEqual(counts["ai_pairs"], 0)
            self.assertEqual(set(pairs.label_origin), {"human_confirmed"})
            self.assertEqual(len(pairs.loc[pairs.split.eq("validation")]), 1)

    def test_incomplete_batch_changed_sample_and_invalid_codes_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); batch = self.fixture(root)
            with self.assertRaisesRegex(ValueError, "Faltan"):
                build_augmented(root)
            for codes in ("", "NN", "Q"):
                with self.assertRaises(ValueError):
                    import_annotations(root, {**batch, "labels": [codes]})
            with (root / "sample.csv").open("a") as handle:
                handle.write("\n")
            with self.assertRaisesRegex(ValueError, "alterada"):
                import_annotations(root, batch)

    def test_plan_enforces_single_model_three_fits_and_original_weights(self):
        import tomllib
        plan = tomllib.loads(Path("config/targeted_ai_augmentation.toml").read_text())
        validate_plan(plan)
        for changed in ({"maximum_fits": 4}, {"ai_weight": 1}, {"sample_comments": 500}):
            with self.assertRaises(ValueError):
                validate_plan({**plan, **changed})

    def test_overlap_and_nontraining_sample_rejected(self):
        human = pd.DataFrame([dict(sample_id="h", comment_id="hc", post_id="hv", user_id="hu", text="Texto humano")])
        sample = pd.DataFrame([dict(sample_id="a", comment_id="ac", post_id="av", user_id="au", text="Otro", split="train")])
        check_separation(sample, human)
        for column in ("sample_id", "comment_id", "post_id", "user_id", "text"):
            with self.assertRaises(ValueError):
                check_separation(sample.assign(**{column: human.iloc[0][column]}), human)
        with self.assertRaises(ValueError):
            check_separation(sample.assign(split="test"), human)

    def test_paired_bootstrap_identity_zero_and_known_coverage_change(self):
        gold, predictions = [], []
        for i, label in enumerate(("positive", "negative", "neutral")):
            gold.append(dict(sample_id=str(i), post_id=str(i), split="validation", sampling_probability=1,
                             annotation_json=json.dumps([dict(target_id="actor", valence=label)])))
            predictions.append(dict(sample_id=str(i), post_id=str(i), target_id="actor", label=label,
                                    valence=label, weight=1, accepted="true", context_windowed="false"))
        gold, predictions = pd.DataFrame(gold), pd.DataFrame(predictions)
        targets = {"actor": {"target_group": "izquierda"}}
        identical = paired_video_bootstrap(gold, predictions, predictions, targets, draws=100)
        self.assertEqual(identical["differences"]["macro_f1_weighted"]["ci95"], [0, 0])
        changed = paired_video_bootstrap(gold, predictions.assign(accepted="false"), predictions, targets, draws=100)
        self.assertEqual(changed["differences"]["left_coverage"]["ci95"], [1, 1])
        self.assertEqual(changed["differences"]["right_coverage"]["valid_draws"], 0)

    def test_import_preserves_sealed_ai_reports_without_local_rerender(self):
        from polarization_pipeline.targeted.remote import import_experiment
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); incoming = base / "incoming"; run = base / "run"
            output = incoming / "experiments/ai_round"; output.mkdir(parents=True)
            target = run / "experiments/ai_round"; target.mkdir(parents=True)
            for root in (output, target):
                atomic_json(root / "plan.json", {"protocol": "targeted-ai-augmentation-v1"})
                atomic_json(root / "source.json", {"frozen": True})
            atomic_json(output / "selection.json", {"selected": None})
            (output / "report").mkdir()
            (output / "report/comparison.png").write_bytes(b"sealed rendering")
            files = {p.relative_to(output).as_posix(): sha256(p) for p in output.rglob("*") if p.is_file()}
            atomic_json(output / "export_tune.json", {"experiment_id": "ai_round", "task": "tune", "files": files,
                "source": {"frozen": True}, "final_test_evaluated": False})
            archive = base / "archive"; archive.write_bytes(b"synthetic archive")
            with patch("polarization_pipeline.targeted.development.verify_source"), patch("polarization_pipeline.targeted.ai_augmentation.render") as render:
                import_experiment({}, run, incoming, archive)
                render.assert_not_called()
            self.assertEqual(sha256(output / "report/comparison.png"), sha256(target / "report/comparison.png"))


if __name__ == "__main__":
    unittest.main()
