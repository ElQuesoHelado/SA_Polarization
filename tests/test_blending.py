import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from polarization_pipeline.targeted.common import LABELS
from polarization_pipeline.targeted.blending import (PROB, aligned, apply_calibration, cross_calibrate,
                                                     validate_plan, video_folds, prepare, execute)


class BlendingTests(unittest.TestCase):
    def frame(self):
        frame = pd.DataFrame([{"sample_id": str(i), "target_id": "actor", "split": "validation", "text": "Actor",
            "post_id": "video_" + str(i // 3), "comment_id": "comment_" + str(i), "target_group": "unknown",
            "label": LABELS[i % 3], "weight": 1., "context_windowed": "False"} for i in range(90)])
        for j, col in enumerate(PROB):
            frame[col] = [.8 if i % 3 == j else .05 for i in range(90)]
        return frame

    def test_exact_alignment_and_probability_validation(self):
        frame = self.frame()
        left, right = aligned(frame, frame.sample(frac=1, random_state=3))
        pd.testing.assert_frame_equal(left, right)
        changes = [frame.iloc[:-1], pd.concat([frame, frame.iloc[:1]])]
        for col, value in (("split", "test"), ("label", "negative"), ("weight", 2.), ("text", "stale"),
                           ("p_positive", float("nan")), ("p_positive", -.1), ("context_windowed", "unknown")):
            altered = frame.copy(); altered.loc[0, col] = value; changes.append(altered)
        for changed in changes:
            with self.assertRaises(ValueError):
                aligned(frame, changed)

    def test_fold_is_by_video_deterministic_independent_of_row_order(self):
        frame = self.frame(); frame["fold"] = video_folds(frame)
        self.assertEqual(frame.groupby("post_id").fold.nunique().max(), 1)
        shuffled = frame.sample(frac=1, random_state=7)
        np.testing.assert_array_equal(shuffled.fold, video_folds(shuffled))
        self.assertEqual(set(frame.fold), set(range(5)))
        with self.assertRaises(ValueError):
            video_folds(frame.iloc[:3])

    def test_held_video_labels_do_not_calibrate_themselves(self):
        frame = self.frame(); p = frame[PROB].to_numpy(); valid = np.ones(len(frame), bool)
        original, decisions = cross_calibrate(frame, p, valid, precision=.85)
        held = original.calibration_fold.eq(0).to_numpy()
        changed = frame.copy(); changed.loc[held, "label"] = "not_evaluable"
        updated, second = cross_calibrate(changed, p, valid, precision=.85)
        self.assertEqual(decisions[0]["calibration"], second[0]["calibration"])
        np.testing.assert_array_equal(original.loc[held, "accepted"], updated.loc[held, "accepted"])
        np.testing.assert_allclose(original.loc[held, PROB].astype(float), updated.loc[held, PROB].astype(float))
        for fold in decisions:
            self.assertFalse(set(fold["fit_videos"]) & set(fold["held_videos"]))
        self.assertNotIn("seed_42_p_positive", original)

    def test_incomplete_context_never_accepted_and_group_not_a_feature(self):
        frame = self.frame(); p = frame[PROB].to_numpy(); valid = np.ones(len(frame), bool); valid[0] = False
        calibration = {"temperature": 1., "thresholds": dict.fromkeys(LABELS, .5)}
        result = apply_calibration(frame, p, calibration, valid)
        self.assertFalse(result.loc[0, "accepted"])
        self.assertTrue(result.loc[0, "context_windowed"])
        altered = frame.copy(); altered["target_group"] = "izquierda"; altered["party"] = "derecha"
        other = apply_calibration(altered, p, calibration, valid)
        pd.testing.assert_frame_equal(result[PROB + ["valence", "accepted"]], other[PROB + ["valence", "accepted"]])

    def test_budget_and_no_overwrite_or_final_test(self):
        import tomllib
        plan = tomllib.loads(Path("config/targeted_ensemble.toml").read_text())
        validate_plan(plan)
        for key, value in (("augmented_weights", [.1, .2]), ("maximum_new_candidates", 20), ("seed", 58)):
            with self.assertRaises(ValueError):
                validate_plan(plan | {key: value})
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp); (run / "model").mkdir(); (run / "model/test_opened.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "reservada"):
                prepare({}, run, "new", Path("config/targeted_ensemble.toml"))
            root = run / "existing"; root.mkdir(); (root / "execution_report.json").write_text("{}")
            with self.assertRaises(FileExistsError):
                execute({}, run, root)

    def test_cross_calibration_receives_only_complement_rows(self):
        frame = self.frame(); calls = []
        def spy(logits, truth, weights, precision, valid):
            calls.append(len(truth))
            self.assertEqual(logits.shape[0], len(truth))
            return {"temperature": 1., "thresholds": dict.fromkeys(LABELS, .5)}
        with patch("polarization_pipeline.targeted.blending.calibrate", side_effect=spy):
            result, _ = cross_calibrate(frame, frame[PROB].to_numpy(), np.ones(len(frame), bool), precision=.85)
        self.assertEqual(calls, [72] * 5)
        self.assertEqual(len(result), len(frame))


if __name__ == "__main__":
    unittest.main()
