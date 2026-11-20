import csv
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from polarization_pipeline.targeted.common import atomic_json, read_csv, sha256
from polarization_pipeline.targeted.cohort_annotations import initialize, checked, import_proposals, import_reference, review


class CohortAnnotationTests(unittest.TestCase):
    def fixture(self, base):
        run = base / "run"; root = run / "cohorts/test"; output = base / "output/run/cohorts/test"
        root.mkdir(parents=True);output.mkdir(parents=True);(run / "annotations").mkdir()
        (run / "annotations/gold.csv").write_text("opaque original; do not decode")
        registry = base / "registry.json"
        atomic_json(registry, {"schema_version": 1, "targets": [{"target_id": "actor", "name": "Actor",
            "target_group": "unknown", "aliases": ["Actor"], "sources": []}]})
        def csv_file(path, rows):
            with path.open("w") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        csv_file(root / "selected_users.csv", [{"user_id": "first"}, {"user_id": "pending"}])
        csv_file(root / "comments.csv", [{"sample_id": "p", "user_id": "first", "comment_id": "c", "post_id": "v", "fold": "A", "text": "Actor bien", "candidates_json": "[]"},
            {"sample_id": "reserved", "user_id": "pending", "comment_id": "d", "post_id": "v", "fold": "B", "text": "Actor mal", "candidates_json": "[]"}])
        atomic_json(output / "summary.json", {"registry_sha256": sha256(registry), "human_gold_sha256": sha256(run / "annotations/gold.csv")})
        artifacts = {str(p.resolve()): sha256(p) for folder in (root, output) for p in folder.iterdir()}
        atomic_json(output / "manifest.json", {"status": "complete", "artifacts": artifacts})
        settings = dict(outputs=base / "output", registry=registry, seed=42, minimum_positive_videos=2,
            affinity_positive_share=2/3, evaluation_min_interactions=3, evaluation_min_videos=2, quality={"macro_f1": .75})
        folder = initialize(settings, run, "test", pilot_users=1)
        batch = {"sample_sha256": sha256(folder / "pilot_sample.csv"), "origin": "synthetic AI fixture", "proposals": [
            {"sample_id": "p", "annotations": [{"target_id": "actor", "valence": "positive", "mention_start": 0, "mention_end": 5}], "note": "synthetic praise"}]}
        return settings, run, folder, batch

    def test_pilot_is_complete_users_and_form_is_unconfirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, run, folder, batch = self.fixture(Path(tmp))
            self.assertEqual(read_csv(folder / "pilot_sample.csv").sample_id.tolist(), ["p"])
            self.assertEqual(read_csv(folder / "pending_ids.csv").sample_id.tolist(), ["reserved"])
            self.assertTrue(read_csv(folder / "human_review.csv").review_complete.eq("").all())
            plan=json.loads((folder / "plan.json").read_text())
            self.assertEqual(plan["shared_videos_pilot_pending"], 1)
            self.assertFalse(plan["training_allowed"])
            with self.assertRaises(FileExistsError):initialize(settings, run, "test", pilot_users=1)

    def test_proposals_never_confirm_humans_or_open_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, run, folder, batch = self.fixture(Path(tmp))
            import_proposals(settings, run, "test", batch)
            status=import_reference(settings, run, "test", check_only=True)
            self.assertEqual(status["ai_proposals"],1);self.assertEqual(status["human_confirmed"],0)
            self.assertFalse(status["ready"])
            with self.assertRaisesRegex(ValueError,"confirmaciones humanas"):import_reference(settings,run,"test")
            self.assertFalse((folder / "pilot_gold.csv").exists());self.assertFalse((run / "model/test_opened.json").exists())

    def test_heldout_duplicate_and_bad_spans_rejected_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings,run,folder,batch=self.fixture(Path(tmp));before=sha256(folder / "ai_proposals.json")
            for field,value in (("sample_id","reserved"),("annotations",[{"target_id":"actor","valence":"positive","mention_start":0,"mention_end":100}])):
                changed=json.loads(json.dumps(batch));changed["proposals"][0][field]=value
                with self.assertRaises(ValueError):import_proposals(settings,run,"test",changed)
                self.assertEqual(sha256(folder / "ai_proposals.json"),before)
            import_proposals(settings,run,"test",batch)
            with self.assertRaises(ValueError):import_proposals(settings,run,"test",batch)

    def test_unregistered_omission_allowed_and_sample_changes_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings,run,folder,batch=self.fixture(Path(tmp))
            batch["proposals"][0]["annotations"][0]["target_id"]="unregistered:Actor"
            import_proposals(settings,run,"test",batch)
            with (folder / "pilot_sample.csv").open("a") as handle:handle.write("\n")
            with self.assertRaises(ValueError):checked(settings,run,"test")

    def test_synthetic_human_review_requires_confirmation_and_closes_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, run, folder, batch = self.fixture(Path(tmp))
            import_proposals(settings, run, "test", batch)
            # Only synthetic fixture input is mocked. Real user forms are never filled by agents.
            with patch("builtins.input", side_effect=["fixture-reviewer", "a", "n"]), patch("builtins.print"):
                review(settings, run, "test")
            self.assertEqual(import_reference(settings, run, "test", check_only=True)["human_confirmed"], 0)
            with patch("builtins.input", side_effect=["fixture-reviewer", "invalid", "a", "s"]), patch("builtins.print"):
                review(settings, run, "test")
            self.assertTrue(import_reference(settings, run, "test")["ready"])
            self.assertTrue((folder / "pilot_gold.csv").exists())
            with self.assertRaises(FileExistsError):
                import_reference(settings, run, "test")
            self.assertFalse((run / "model/test_opened.json").exists())
            with (folder / "pilot_gold.csv").open("a") as handle:
                handle.write("altered")
            with self.assertRaisesRegex(ValueError, "cerrada alterada"):
                import_reference(settings, run, "test", check_only=True)

    def test_partial_human_decisions_and_changed_proposals_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, run, folder, batch = self.fixture(Path(tmp))
            import_proposals(settings, run, "test", batch)
            form = read_csv(folder / "human_review.csv")
            form.loc[0, "reviewer_id"] = "fixture-partial"
            form.to_csv(folder / "human_review.csv", index=False)
            with self.assertRaisesRegex(ValueError, "parcial"):
                import_reference(settings, run, "test", check_only=True)
            with (folder / "ai_proposals.json").open("a") as handle:
                handle.write("\n")
            with self.assertRaisesRegex(ValueError, "alterados"):
                checked(settings, run, "test")
