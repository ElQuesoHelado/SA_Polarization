import csv
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from polarization_pipeline.targeted.annotations import text_key
from polarization_pipeline.targeted.cohort import (eligible_frame, exclusion_reason, rank_users,
    selected_comments, reading_queue, cost_scenarios, load_exclusions)
from polarization_pipeline.targeted.metrics import partition_videos


class ToyMatcher:
    def find(self, text, date=""):
        return [{"target_id": group, "target_name": group, "target_group": group,
                 "mention_start": text.index(group), "mention_end": text.index(group) + len(group)}
                for group in ("izquierda", "derecha") if group in text]


class UserCohortTests(unittest.TestCase):
    settings = dict(seed=42, minimum_positive_videos=2, evaluation_min_interactions=3, evaluation_min_videos=2)

    def fixture(self):
        videos = pd.DataFrame({"post_id": [f"video{i}" for i in range(100)]})
        videos["fold"] = partition_videos(videos, 42)
        a = videos.loc[videos.fold.eq("A"), "post_id"].tolist()[:2]
        b = videos.loc[videos.fold.eq("B"), "post_id"].tolist()[:2]
        rows = []
        for user in ("one", "two", "three"):
            for i, (video, text) in enumerate(((a[0], "izquierda"), (a[1], "izquierda"),
                (b[0], "izquierda derecha"), (b[1], "derecha"), (b[1], "sin coincidencias " + "x" * 5000))):
                rows.append(dict(user_id=user, comment_id=f"{user}{i}", post_id=video, channel_id="channel",
                    corpus="main", text=text, comment_published_at="2026-01-01", comment_type="top_level"))
        return rows, {key: set() for key in ("user_id", "post_id", "comment_id", "text_key")}

    def test_eligibility_is_structural_and_retains_noncandidate_comments(self):
        rows, excluded = self.fixture()
        frame, summary = eligible_frame(iter(rows), ToyMatcher(), self.settings, excluded)
        self.assertEqual(summary["unrestricted_potential_users"], 3)
        self.assertEqual(len(frame), 3)
        self.assertEqual(set(frame.total_comments), {5})
        self.assertEqual(set(frame.political_mention_comments), {4})
        self.assertNotIn("ingroup", frame)
        self.assertNotIn("AP", frame)

    def test_each_exclusion_applies_and_insufficient_remaining_activity_drops_user(self):
        rows, excluded = self.fixture()
        for key, value in (("user_id", "one"), ("post_id", rows[0]["post_id"]),
                           ("comment_id", rows[0]["comment_id"]), ("text_key", text_key(rows[0]["text"]))):
            updated = {k: set(v) for k, v in excluded.items()}; updated[key].add(value)
            self.assertEqual(exclusion_reason(rows[0], updated), key)
        excluded["post_id"].add(rows[0]["post_id"])
        frame, summary = eligible_frame(rows, ToyMatcher(), self.settings, excluded)
        self.assertEqual(len(frame), 0)
        self.assertEqual(summary["unrestricted_potential_users"], 3)

    def test_selection_nested_reproducible_not_order_or_sentiment_dependent(self):
        rows, excluded = self.fixture()
        frame, _ = eligible_frame(rows, ToyMatcher(), self.settings, excluded)
        a = rank_users(frame, 57); b = rank_users(frame.sample(frac=1, random_state=2), 57)
        self.assertEqual(a.user_id.tolist(), b.user_id.tolist())
        selected = a.iloc[:2]
        result = selected_comments(rows, selected, ToyMatcher(), excluded, seed=42, cohort_id="toy", population=3)
        self.assertEqual(len(result), 10)
        self.assertTrue(result.text.str.len().max() > 5000)
        self.assertFalse(result.groupby("post_id").fold.nunique().gt(1).any())
        self.assertEqual(set(result.user_inclusion_probability), {2 / 3})
        queue = reading_queue(result)
        self.assertEqual(set(queue), {"sample_id", "text", "target_hints_json"})
        self.assertFalse(queue.target_hints_json.str.contains('"target_group"').any())
        self.assertFalse(any(k in queue for k in ("party", "fold", "review_complete", "label", "sentimiento")))

    def test_export_rejects_missing_rows_instead_of_capping_history(self):
        rows, excluded = self.fixture()
        frame, _ = eligible_frame(rows, ToyMatcher(), self.settings, excluded)
        with self.assertRaisesRegex(ValueError, "todos los comentarios"):
            selected_comments(rows[:-1], frame, ToyMatcher(), excluded, seed=42, cohort_id="toy", population=3)

    def test_cost_uses_all_comments_and_does_not_substitute_unavailable_size(self):
        rows, excluded = self.fixture()
        frame, _ = eligible_frame(rows, ToyMatcher(), self.settings, excluded)
        costs = cost_scenarios(rank_users(frame, 57), 2)
        self.assertEqual(int(costs.loc[costs.users.eq(2), "comments"].iloc[0]), 10)
        self.assertFalse(costs.loc[costs.users.eq(100), "available"].iloc[0])

    def test_exclusions_read_metadata_without_decoding_final_annotations(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp); run = workspace / "active"; (run / "annotations").mkdir(parents=True)
            row = dict(user_id="heldout", post_id="testvideo", comment_id="testcomment", text="Texto reservado",
                       split="test", annotation_json="THIS IS NOT JSON")
            with (run / "annotations/sampling_manifest.csv").open("w") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(row));writer.writeheader();writer.writerow(row)
            excluded, hashes = load_exclusions({"workspace": workspace}, run)
            self.assertIn("testvideo", excluded["post_id"])
            self.assertIn(text_key(row["text"]), excluded["text_key"])
            self.assertEqual(len(hashes), 1)
            self.assertFalse((run / "model/test_opened.json").exists())

    def test_duplicate_comments_rejected(self):
        rows, excluded = self.fixture()
        with self.assertRaisesRegex(ValueError, "duplicada"):
            eligible_frame(rows + rows[:1], ToyMatcher(), self.settings, excluded)


if __name__ == "__main__":
    unittest.main()
