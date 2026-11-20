"""Resume authorized capture and prepare frozen samples, stopping before annotation."""
from __future__ import annotations

import json
import time
from collections import Counter

from ..collection import BudgetedAPI
from ..common import atomic_json, read_csv, stamp
from . import annotations, data
from .state import lock, output, verify


WAITING = {"waiting_active_capture", "waiting_quota"}


def collector_active(settings):
    try:
        with lock(settings["workspace"] / "publication_collection.lock"):
            return False
    except BlockingIOError:
        return True


def capture_counts(study):
    counts = Counter()
    for video in read_csv(study / "videos.csv").post_id:
        path = study / "raw_capture" / f"{video}.json"
        state = json.loads(path.read_text()) if path.exists() else {}
        status = state.get("status", "not_started")
        if status not in {"not_started", "incomplete", "complete", "unavailable"}:
            raise ValueError("Estado de captura incompatible")
        counts[status] += 1
    return dict(counts)


def latest_collection(settings, study):
    reports = list((output(settings, study) / "collection_runs").glob("*.json"))
    if not reports:
        return None
    return json.loads(max(reports, key=lambda p: p.stat().st_mtime_ns).read_text())


def step(settings, plan, parent, study, registry, budget):
    verify(study)
    if not (study / "freeze.json").exists():
        if collector_active(settings):
            return dict(status="waiting_active_capture")
        counts = capture_counts(study)
        pending = counts.get("not_started", 0) + counts.get("incomplete", 0)
        if pending:
            budget_state = BudgetedAPI(None, settings["workspace"] / "api_usage.json", budget).budget_status()
            previous = latest_collection(settings, study)
            if previous and previous.get("outcome") in {"transport_error", "api_error", "capture_error"}:
                return dict(status="needs_attention", reason=previous["outcome"], capture_status=counts)
            # Official quota can be exhausted while the local counter has room.
            official_pause = (previous and previous.get("outcome") == "youtube_quota"
                and previous.get("budget_after", previous.get("budget_before", {})).get("quota_day") == budget_state["quota_day"])
            if not budget_state["local_remaining"] or official_pause:
                return dict(status="waiting_quota", reason="youtube_quota" if official_pause else "local_budget",
                    capture_status=counts, budget=budget_state)
            try:
                result = data.collect(settings, plan, study, daily_api_budget=budget)
            except BlockingIOError:
                return dict(status="waiting_active_capture")
            outcome = result["collection"]["outcome"]
            if outcome in {"local_budget", "youtube_quota"}:
                return dict(status="waiting_quota", reason=outcome,
                    budget=result["collection"]["budget_after"], capture_status=capture_counts(study))
            if outcome != "completed":
                return dict(status="needs_attention", reason=outcome)
        try:
            data.freeze(settings, plan, parent, study, registry)
        except BlockingIOError:
            return dict(status="waiting_active_capture")
    verify(study, frozen=True)
    if not (study / "annotations/benchmark").exists():
        annotations.init_benchmark(study)
    else:
        annotations.checked(study, "benchmark")
    cohorts = sorted((study / "annotations").glob("cohort_[0-9][0-9][0-9][0-9]"))
    if not cohorts:
        annotations.next_batch(settings, plan, study, registry)
        cohorts = sorted((study / "annotations").glob("cohort_[0-9][0-9][0-9][0-9]"))
    for folder in cohorts:
        annotations.checked(study, folder.name)
    from .measurement import preflight as measurement
    from .evaluation_preflight import preflight as evaluation
    return dict(status="waiting_annotations", snapshot_frozen=True,
        benchmark_comments=len(read_csv(study / "benchmark.csv")),
        cohort_batches=len(cohorts), cohort_comments=sum(len(read_csv(p / "sample.csv")) for p in cohorts),
        cohort_users=sum(read_csv(p / "sample.csv").user_id.nunique() for p in cohorts),
        benchmark_review_command=".venv/bin/sa-polarization targeted publication review --sample benchmark",
        annotation_order="blind_benchmark_before_cohort_review",
        measurement=measurement(settings, plan, study, registry),
        evaluation=evaluation(settings, plan, study, registry),
        human_decisions_written=0, new_training=False, production_enabled=False)


def run(settings, plan, parent, study, registry, *, daily_api_budget=None, watch=False):
    budget = plan["daily_api_budget"] if daily_api_budget is None else daily_api_budget
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 1:
        raise ValueError("daily-api-budget debe ser un entero positivo")
    folder = output(settings, study) / "advancement"
    from .runtime import heartbeat
    with lock(study / "advancement.lock"), heartbeat(study):
        folder.mkdir(parents=True, exist_ok=True)
        prior = None
        while True:
            try:
                result = step(settings, plan, parent, study, registry, budget)
            except Exception as exc:
                # Store only the exception type: external exceptions may contain URLs/secrets.
                atomic_json(folder / "state.json", dict(status="needs_attention", error_type=type(exc).__name__,
                    updated_at=stamp(), effective_daily_budget=budget))
                raise RuntimeError("Continuación detenida; revisar artefactos locales y estado de captura") from None
            if result != prior:
                event = dict(**result, updated_at=stamp(), effective_daily_budget=budget)
                atomic_json(folder / (event["updated_at"].replace(":", "") + ".json"), event)
                atomic_json(folder / "state.json", event)
                print(json.dumps(event, ensure_ascii=False, default=str), flush=True)
                prior = result
            if not watch or result["status"] not in WAITING:
                return result
            time.sleep(60)
