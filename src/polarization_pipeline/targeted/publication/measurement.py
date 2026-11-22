"""Human-reference measurement readiness, independent of predictive models."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..common import read_csv
from .state import verify, verify_seal


def validate_histories(sample, ranked, corpus):
    if (ranked.user_id.duplicated().any() or ranked.user_id.eq("").any()
            or ranked["rank"].astype(int).tolist() != list(range(1, len(ranked)+1))):
        raise ValueError("Orden congelado de usuarios inválido")
    used = set(sample.user_id)
    if used != set(ranked.iloc[:len(used)].user_id):
        raise ValueError("La cohorte no conserva el prefijo congelado")
    if sample.comment_id.duplicated().any() or corpus.comment_id.duplicated().any():
        raise ValueError("Comentarios duplicados en historiales")
    expected = corpus.loc[corpus.user_id.isin(used)].sort_values("comment_id").reset_index(drop=True)
    if set(sample.comment_id) != set(expected.comment_id):
        raise ValueError("Faltan o sobran comentarios del historial congelado")
    actual = sample.sort_values("comment_id").reset_index(drop=True)
    if not actual[corpus.columns].equals(expected):
        raise ValueError("El historial difiere del corpus congelado")


def screened_users(sample, events, scored, ranked, settings, target):
    frame = ranked.loc[ranked.user_id.isin(sample.user_id), ["user_id", "rank"]].merge(scored, how="left", on="user_id", validate="one_to_one")
    frame["ingroup"] = frame.ingroup.fillna("Undetermined")
    frame["paired"] = frame.paired.eq(True)
    counts = sample.groupby("user_id").comment_id.size()
    valid = events.loc[events.valence.isin(["positive", "negative", "neutral"])].groupby("user_id").size()
    frame["observed_comments"] = frame.user_id.map(counts).fillna(0).astype(int)
    frame["known_evaluable_events"] = frame.user_id.map(valid).fillna(0).astype(int)
    def reasons(row):
        if row.paired:
            return []
        if 'affinity_excluded' in sample and sample.loc[sample.user_id.eq(row.user_id),'affinity_excluded'].all():
            return ["affinity_exclusion_certified"]
        if not row.known_evaluable_events:
            return ["no_known_evaluable_events"]
        if row.ingroup == "Undetermined":
            return ["affinity_undetermined"]
        result = []
        for name, reason, minimum in (("N_in", "no_evaluation_ingroup", 1), ("N_out", "no_evaluation_outgroup", 1),
                ("evaluation_interactions", "insufficient_evaluation_events", settings["evaluation_min_interactions"]),
                ("evaluation_videos", "insufficient_evaluation_videos", settings["evaluation_min_videos"])):
            if getattr(row, name, 0) < minimum:
                result.append(reason)
        return result
    frame["exclusion_reasons"] = [json.dumps(reasons(r)) for r in frame.itertuples()]
    chosen = set(frame.loc[frame.paired].sort_values("rank").iloc[:target].user_id)
    frame["selection_status"] = np.where(frame.user_id.isin(chosen), "primary", np.where(frame.paired, "comparable_beyond_target", "not_comparable"))
    return frame


def precision_assessment(intervals, planned_half_width):
    gap = intervals.loc[intervals.contrast.eq("gap")]
    result = dict(precision_status="not_estimable", precision_target_met=None, observed_half_width=None,
        planned_half_width=planned_half_width, gap_evidence="not_estimable", gap_ci_low=None, gap_ci_high=None)
    if gap.empty:
        return result
    row = gap.iloc[0]
    if row.status != "estimated" or not np.isfinite([row.ci_low, row.ci_high]).all() or row.ci_low > row.ci_high:
        return result
    low, high = float(row.ci_low), float(row.ci_high)
    half = (high-low)/2
    result.update(precision_status="target_met" if half <= planned_half_width else "target_not_met",
        precision_target_met=bool(half <= planned_half_width), observed_half_width=half,
        gap_ci_low=low, gap_ci_high=high,
        gap_evidence="positive_relative_favoritism" if low > 0 else "negative_relative_favoritism" if high < 0 else "inconclusive")
    return result


def coverage_tables(corpus, sample, events, included, registry):
    from ..registry import load_registry
    coverage, composition, annotations = [], [], []
    targets = {t["target_id"]: t.get("target_group", "unknown") for t in load_registry(registry, frozen=True)["targets"]}
    for scope, comments in (("snapshot", corpus), ("screened", sample), ("primary", sample.loc[sample.user_id.isin(included)])):
        for source, part in [("all", comments), *list(comments.groupby("party", sort=True))]:
            coverage.append(dict(scope=scope, source=source, comments=len(part), users=part.loc[part.user_id.ne(""), "user_id"].nunique(),
                videos=part.post_id.nunique(), channels=part.channel_id.nunique()))
        if scope == "snapshot":
            continue
        selected = events if scope == "screened" else events.loc[events.user_id.isin(included)]
        for (group, valence), part in selected.groupby(["target_group", "valence"], sort=True):
            composition.append(dict(scope=scope, target_group=group, valence=valence, events=len(part),
                users=part.user_id.nunique(), comments=part.comment_id.nunique(), videos=part.post_id.nunique(), channels=part.channel_id.nunique()))
        units = []
        empty = 0
        skipped = 0
        for row in comments.itertuples():
            if pd.isna(row.annotation_json):
                skipped += 1
                continue
            items = json.loads(row.annotation_json)
            empty += not items
            for item in items:
                units.append(dict(target_group=targets.get(item["target_id"], "unknown"), valence=item["valence"], comment_id=row.comment_id, user_id=row.user_id))
        if units:
            for (group, valence), part in pd.DataFrame(units).groupby(["target_group", "valence"], sort=True):
                annotations.append(dict(scope=scope, target_group=group, valence=valence, targets=len(part), comments=part.comment_id.nunique(), users=part.user_id.nunique()))
        if skipped:
            annotations.append(dict(scope=scope, target_group="unread", valence="skipped_affinity", targets=0, comments=skipped, users=None))
        annotations.append(dict(scope=scope, target_group="none", valence="no_explicit_targets", targets=0, comments=empty, users=None))
    return (pd.DataFrame(coverage), pd.DataFrame(composition, columns=["scope", "target_group", "valence", "events", "users", "comments", "videos", "channels"]),
        pd.DataFrame(annotations))


def preflight(settings, plan, study, registry):
    from .annotations import decisions
    from .analysis import events_from_annotations, scores
    from .evaluation_preflight import sample_readiness
    verify(study)
    result = dict(study=study.name, read_only=True, measurement_basis="human_annotations",
        model_readiness_required=False, benchmark_required_for_primary_measurement=False,
        production_enabled=False, reserved_test_opened=False, ready_for_analysis=False,
        status="waiting_snapshot", requirements=dict(snapshot_frozen=(study / "freeze.json").exists()))
    if not result["requirements"]["snapshot_frozen"]:
        result["next_command"] = "targeted publication collect"
        result["after_capture_command"] = "targeted publication freeze"
        return result
    verify(study, frozen=True)
    verify_seal(study, "capture_manifest.json")
    ranked = read_csv(study / "eligible_users.csv")
    corpus = read_csv(study / "corpus.csv")
    folders = sorted((study / "annotations").glob("cohort_[0-9][0-9][0-9][0-9]"))
    if [f.name for f in folders] != [f"cohort_{i:04d}" for i in range(1, len(folders)+1)]:
        raise ValueError("Secuencia de lotes incompleta")
    result.update(eligible_frame_users=len(ranked), target_comparable_users=plan["comparable_users"],
        screened_users=0, reviewed_comments=0, pending_comments=0)
    result["requirements"].update(cohort_initialized=bool(folders), human_review_complete=False, histories_complete=False)
    if ranked.empty:
        result.update(status="insufficient_eligible_frame", frame_exhausted=True, target_reached=False,
            comparable_users=0, next_command=None,
            limitation="Sin usuarios estructuralmente elegibles; informar insuficiencia, no cambiar criterios automáticamente")
        return result
    if not folders:
        result.update(status="waiting_cohort", next_command="targeted publication next")
        return result
    samples, finals = [], []
    for folder in folders:
        sample, form, info = sample_readiness(study, folder.name, registry)
        samples.append(sample)
        complete = form.review_complete.str.lower().eq("true")
        result["reviewed_comments"] += int(complete.sum())
        if info['human_review_complete']:
            result['pending_comments'] += 0
        else:
            result['pending_comments'] += int((~complete).sum())
        result['skipped_comments'] = result.get('skipped_comments',0) + info.get('skipped_comments',0)
        # Validate every completed batch, even if a different batch is pending.
        if info["human_review_complete"]:
            finals.append(decisions(study, folder.name, registry, "final"))
    sample = pd.concat(samples, ignore_index=True)
    validate_histories(sample, ranked, corpus)
    result["screened_users"] = sample.user_id.nunique()
    from .fixed_scope import policy
    fixed=policy(study)
    result.update(stopping_rule="fixed_screened_users" if fixed else "comparable_users_or_exhaustion",
        screened_users_ceiling=fixed["screened_users"] if fixed else None)
    if fixed and result["screened_users"]>fixed["screened_users"]:
        raise ValueError("Usuarios fuera del alcance fijo")
    result["requirements"]["histories_complete"] = True
    if result["pending_comments"]:
        result.update(status="waiting_human_review", next_command="targeted publication review --sample <lote pendiente>")
        return result
    result["requirements"]["human_review_complete"] = True
    frame = pd.concat(finals, ignore_index=True)
    events = events_from_annotations(frame, registry)
    screened = screened_users(frame, events, scores(events, settings), ranked, settings, plan["comparable_users"])
    comparable = int(screened.paired.sum())
    exhausted = result["screened_users"] == len(ranked)
    from .fixed_scope import policy
    fixed=policy(study)
    reached=(result['screened_users']==fixed['screened_users']) if fixed else comparable>=plan['comparable_users']
    if fixed and result['screened_users']>fixed['screened_users']:
        raise ValueError('Usuarios fuera del alcance fijo')
    result.update(comparable_users=comparable if fixed else min(comparable, plan['comparable_users']),
        comparable_screened_total=comparable,stopping_rule='fixed_screened_users' if fixed else 'comparable_users_or_exhaustion',
        screened_users_ceiling=fixed['screened_users'] if fixed else None,
        frame_exhausted=exhausted, target_reached=reached)
    result["ready_for_analysis"] = result["target_reached"] or exhausted
    result.update(status="ready_for_analysis" if result["ready_for_analysis"] else "waiting_comparable_users",
        next_command="targeted publication analyze --stage final" if result["ready_for_analysis"] else "targeted publication next --stage final",
        precision_status="not_assessed_before_analysis", no_stopping_by_gap_or_significance=True)
    return result
