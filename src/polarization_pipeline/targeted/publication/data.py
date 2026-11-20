from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from ..annotations import text_key
from ..collection import CollectionPaused, api_client, collect_video
from ..common import POLITICAL, atomic_json, in_window, read_csv, sha256, stamp
from ..diagnostics import EVENT_COLUMNS, opportunities
from ..metrics import partition_videos
from ..registry import Matcher, load_registry
from .state import PROTOCOL, lock, metadata_exclusions, output, seal, sid, verify


def prepare(settings, plan, parent, study, registry, config_path):
    if study.exists():
        raise FileExistsError("Estudio existente; use collect/status para reanudar")
    if (parent / "model/test_opened.json").exists():
        raise ValueError("La prueba final debe permanecer reservada")
    actors = load_registry(registry, frozen=True)
    audit = actors.get("publication_audit", {})
    if audit.get("status") != "complete":
        raise ValueError("Falta auditoría documental v3 completa")
    exclusions = metadata_exclusions(settings, parent)
    inputs = {str(Path(config_path).resolve()): sha256(Path(config_path)),
              str(settings["_config_path"].resolve()): sha256(settings["_config_path"]),
              str(settings["source_config"].resolve()): sha256(settings["source_config"]),
              str(registry.resolve()): sha256(registry), **exclusions["hashes"]}
    for path in (parent / "annotations/manifest.json", parent / "annotations/gold.csv", settings["registry"]):
        inputs[str(path.resolve())] = sha256(path)
    frames = []
    for name, component in (("corpus_main.csv", "historical_main"), ("corpus_panel.csv", "audit_panel")):
        path = parent / name
        if path.exists():
            inputs[str(path.resolve())] = sha256(path)
            frame = read_csv(path)
            frame["component"] = component
            frames.append(frame)
    if not frames:
        raise ValueError("Sin corpus de origen")
    base = pd.concat(frames, ignore_index=True).fillna("")
    periods = settings["source"]["youtube"]["periods"]
    allowed = {v for values in settings["source"]["youtube"]["channels"].values() for v in values}
    base = base.loc[in_window(base.video_published_at, periods)
                    & in_window(base.comment_published_at, periods)
                    & ~base.post_id.isin(exclusions["test_videos"])
                    & ~base.comment_id.isin(exclusions["test_ids"])].copy()
    base = merge_comments(base.to_dict("records"), [])[0]
    if base.empty:
        raise ValueError("Marco sin videos elegibles")
    # Reject contradictory source metadata, including user/editorial identities.
    for key in ("channel_id", "party", "channel_handle", "video_published_at"):
        if base.groupby("post_id")[key].nunique().gt(1).any():
            raise ValueError(f"Metadata contradictoria por video: {key}")
    videos = base.loc[base.channel_handle.isin(allowed)].drop_duplicates("post_id")[[k for k in (
        "post_id", "channel_id", "channel_handle", "channel", "party", "video_published_at", "post_title") if k in base]]
    videos = videos.sort_values("post_id")
    study.mkdir(parents=True)
    base.to_csv(study / "historical.csv", index=False)
    videos.to_csv(study / "videos.csv", index=False)
    (study / "raw_capture").mkdir()
    inputs.update({str((study / name).resolve()): sha256(study / name) for name in ("historical.csv", "videos.csv")})
    atomic_json(study / "study.json", dict(protocol=PROTOCOL, created_at=stamp(), plan=plan,
        inputs=inputs, parent=str(parent.resolve()), registry=str(registry.resolve()),
        test_marker=str((parent / "model/test_opened.json").resolve()),
        historical_comments=len(base), known_videos=len(videos), final_test_labels_decoded=False,
        sampling_scope="Histórico/panel conservados; captura nueva solo en canales/periodos configurados y videos observados; no censo de YouTube"))
    return status(settings, study)


def merge_comments(historical, new):
    rows, versions = {}, []
    for row in [*historical, *new]:
        key = row.get("comment_id", "")
        if not key or not row.get("post_id"):
            raise ValueError("Comentario/video sin identidad")
        if key in rows:
            prior = rows[key]
            for field in ("post_id", "user_id"):
                if prior.get(field) and row.get(field) and prior[field] != row[field]:
                    raise ValueError(f"Conflicto de identidad de comentario: {field}")
            versions.append({**row, "retained_component": prior.get("component", ""),
                             "text_changed": prior["text"] != row["text"]})
        else:
            rows[key] = row
    return pd.DataFrame(rows.values()).fillna(""), pd.DataFrame(versions).fillna("")


def status(settings, study):
    manifest = verify(study)
    counts = Counter()
    captured_rows, captured_replies = 0, 0
    for path in (study / "raw_capture").glob("*.json"):
        state = json.loads(path.read_text())
        counts[state["status"]] += 1
        if state["status"] == "complete":
            comments = list(state.get("comments", {}).values())
            if comments:
                mask = in_window(pd.Series([row["comment_published_at"] for row in comments]), settings["source"]["youtube"]["periods"])
                captured_rows += int(mask.sum())
                captured_replies += sum(bool(row.get("parent_id")) for row, valid in zip(comments, mask) if valid)
    result = dict(study=study.name, videos=manifest["known_videos"], capture_status=dict(counts),
                  not_started=manifest["known_videos"]-sum(counts.values()),
                  historical_union_comments=manifest["historical_comments"],
                  captured_rows_in_window=captured_rows, captured_replies_in_window=captured_replies,
                  captured_counts_are_not_new_unique_rows=True,
                  frozen=(study / "freeze.json").exists(), test_opened=False)
    atomic_json(output(settings, study) / "status.json", result)
    return result


def collect(settings, plan, study, *, api=None, max_videos=None, daily_api_budget=None):
    effective_budget = plan["daily_api_budget"] if daily_api_budget is None else daily_api_budget
    if isinstance(effective_budget, bool) or not isinstance(effective_budget, int) or effective_budget < 1:
        raise ValueError("daily-api-budget debe ser un entero positivo")
    verify(study)
    if (study / "freeze.json").exists():
        raise ValueError("No capturar sobre un snapshot congelado")
    # BudgetedAPI's existing JSON ledger is protected for the full capture process.
    # This also prevents simultaneous publication collectors losing increments.
    with lock(settings["workspace"] / "publication_collection.lock"):
        client = api_client({**settings, "daily_api_budget": effective_budget}, api)
        started = stamp()
        report_path = output(settings, study) / "collection_runs" / (started.replace(":", "") + ".json")
        if report_path.exists():
            raise FileExistsError("Informe de captura existente; no sobrescribir")
        execution = dict(study=study.name, started_at=started, outcome="running", effective_daily_budget=effective_budget,
            configured_daily_budget=plan["daily_api_budget"], budget_before=client.budget_status(),
            official_google_balance_verified=False)
        atomic_json(report_path, execution)
        count = 0
        reason = "completed"
        try:
            for video in read_csv(study / "videos.csv").to_dict("records"):
                path = study / "raw_capture" / f"{video['post_id']}.json"
                if path.exists() and json.loads(path.read_text())["status"] in ("complete", "unavailable"):
                    continue
                if max_videos is not None and count >= max_videos:
                    reason = "max_videos"
                    break
                try:
                    collect_video(client, video, path, settings["source"]["youtube"]["periods"])
                    count += 1
                    if count % 25 == 0:
                        print(f"Captura: {count} videos terminados en esta sesión", flush=True)
                except CollectionPaused as exc:
                    reason = exc.reason
                    print(f"Captura pausada ({reason}); progreso conservado.", flush=True)
                    break
            verify(study)
        except Exception as exc:
            reason = getattr(exc, "reason", "capture_error")
            raise
        finally:
            execution.update(outcome=reason, finished_at=stamp(), videos_finished_this_run=count,
                budget_after=client.budget_status())
            atomic_json(report_path, execution)
            result = status(settings, study)
            result["collection"] = execution
            atomic_json(output(settings, study) / "status.json", result)
        return result


def freeze(settings, plan, parent, study, registry, *, use_cache=True):
    with lock(settings["workspace"] / "publication_collection.lock"):
        return _freeze(settings, plan, parent, study, registry, use_cache=use_cache)


def _freeze(settings, plan, parent, study, registry, *, use_cache=True):
    verify(study)
    if (study / "freeze.json").exists():
        raise FileExistsError("El snapshot ya está congelado")
    states = []
    videos = read_csv(study / "videos.csv")
    for video in videos.post_id:
        path = study / "raw_capture" / f"{video}.json"
        if not path.exists():
            raise ValueError("Captura pendiente; no congelar un corpus parcial")
        state = json.loads(path.read_text())
        if state["status"] not in ("complete", "unavailable"):
            raise ValueError("Captura incompleta; reanudar collect")
        states.append(state)
    cached_candidates = None
    if use_cache and (study / "local_preparation_cache").exists():
        from .local_preparation import assemble, inventory, SourceChanged
        sources, _ = inventory(study)
        union, versions, excluded, cached_candidates, _ = assemble(settings, study, registry, sources, write=False)
        if any(sha256(path) != expected for _, path, expected in sources):
            raise SourceChanged("Fuentes cambiaron antes de congelar")
        exclusions = excluded.to_dict("records")
    else:
        periods = settings["source"]["youtube"]["periods"]
        new, exclusions = [], []
        for state in states:
            if state["status"] != "complete":
                continue
            for comment in state["comments"].values():
                if not bool(in_window(pd.Series([comment["comment_published_at"]]), periods).iloc[0]):
                    exclusions.append(dict(comment_id=comment["comment_id"], post_id=state["video"]["post_id"],
                        comment_published_at=comment["comment_published_at"], reason="comment_outside_window_or_invalid_date"))
                    continue
                parent_row = state["comments"].get(comment.get("parent_id", ""), {})
                new.append({**state["video"], **comment, "component": "api_capture", "corpus": "publication_union",
                            "parent_text": parent_row.get("text", ""), "captured_at": state["finished_at"],
                            "provenance": "youtube_api_v3"})
        union, versions = merge_comments(read_csv(study / "historical.csv").to_dict("records"), new)
        union["corpus"] = "publication_union"
    union.to_csv(study / "corpus.csv", index=False)
    versions.to_csv(study / "recapture_versions.csv", index=False)
    pd.DataFrame(exclusions, columns=["comment_id", "post_id", "comment_published_at", "reason"]).to_csv(study / "capture_exclusions.csv", index=False)
    sample_frames(settings, plan, parent, study, registry, union, precomputed_candidates=cached_candidates)
    seal(study, [str(path.relative_to(study)) for path in sorted((study / "raw_capture").glob("*.json"))],
         filename="capture_manifest.json", status="closed_capture")
    seal(study, ["corpus.csv", "recapture_versions.csv", "capture_exclusions.csv", "capture_manifest.json", "eligible_users.csv", "benchmark.csv"],
         filename="freeze.json", comments=len(union), new_comments=len(union)-len(read_csv(study / "historical.csv")),
         complete_videos=sum(s["status"] == "complete" for s in states),
         unavailable_videos=sum(s["status"] == "unavailable" for s in states), status="frozen")
    return status(settings, study)


def proportional_sample(frame, n, seed):
    """Hamilton allocation, >=1 per observed stratum, with known comment probabilities."""
    if len(frame) < n:
        raise ValueError(f"Cuota sin soporte: necesita {n}, disponible {len(frame)}")
    groups = list(frame.groupby(["party", "month", "comment_type"], sort=True, dropna=False))
    if n < len(groups):
        raise ValueError("Cuota menor que número de estratos; no asignar probabilidad cero")
    populations = np.array([len(g) for _, g in groups])
    ideal = populations / populations.sum() * n
    counts = np.minimum(populations, np.maximum(1, np.floor(ideal).astype(int)))
    while counts.sum() > n:
        i = int(np.argmax(np.where(counts > 1, counts-ideal, -np.inf)))
        counts[i] -= 1
    while counts.sum() < n:
        i = int(np.argmax(np.where(counts < populations, ideal-counts, -np.inf)))
        counts[i] += 1
    result = []
    for (_, group), count in zip(groups, counts):
        chosen = group.sort_values("comment_id").sample(n=int(count), random_state=seed).copy()
        chosen["sampling_probability"] = count / len(group)
        chosen["stratum_population"] = len(group)
        chosen["stratum_sample"] = int(count)
        result.append(chosen)
    return pd.concat(result, ignore_index=True)


def sample_frames(settings, plan, parent, study, registry, corpus, *, precomputed_candidates=None):
    matcher = Matcher(load_registry(registry, frozen=True))
    corpus = corpus.copy()
    if precomputed_candidates is None:
        corpus["candidates_json"] = [json.dumps(matcher.find(r.text, r.comment_published_at), ensure_ascii=False)
                                      for r in corpus.itertuples()]
    else:
        if len(precomputed_candidates) != len(corpus):
            raise ValueError("Candidatos de caché desalineados")
        corpus["candidates_json"] = precomputed_candidates
    events = []
    def bucket(row):
        candidates = json.loads(row["candidates_json"])
        known = sorted({m["target_group"] for m in candidates} & set(POLITICAL))
        if len(known) == 2:
            return known[int(hashlib.sha256(row["comment_id"].encode()).hexdigest(), 16) % 2]
        return known[0] if known else "unknown" if candidates else "none"
    for row in corpus.to_dict("records"):
        for group in {m["target_group"] for m in json.loads(row["candidates_json"])} & set(POLITICAL):
            events.append({**{k: row.get(k, "") for k in EVENT_COLUMNS}, "target_group": group})
    users = Counter(corpus.loc[corpus.user_id.ne(""), "user_id"])
    opportunity = opportunities(pd.DataFrame(events, columns=EVENT_COLUMNS), users, settings, seed=plan["seed"])
    eligible = opportunity.loc[opportunity.potentially_paired].copy()
    eligible["rank_hash"] = eligible.user_id.map(lambda u: hashlib.sha256(f"ap-publication:{plan['selection_seed']}:{u}".encode()).hexdigest())
    eligible = eligible.sort_values(["rank_hash", "user_id"]).reset_index(drop=True)
    eligible["rank"] = np.arange(1, len(eligible)+1)
    eligible.to_csv(study / "eligible_users.csv", index=False)
    exclusions = metadata_exclusions(settings, parent)
    benchmark = corpus.loc[~corpus.post_id.isin(exclusions["seen_videos"])
        & ~corpus.text.map(text_key).isin(exclusions["seen_texts"])].copy()
    benchmark["text_key"] = benchmark.text.map(text_key)
    benchmark = benchmark.drop_duplicates("text_key").copy()
    benchmark["bucket"] = [bucket(row) for row in benchmark.to_dict("records")]
    benchmark["month"] = pd.to_datetime(benchmark.comment_published_at, utc=True).dt.strftime("%Y-%m")
    selections = [proportional_sample(benchmark.loc[benchmark.bucket.eq(group)], n, plan["selection_seed"])
                  for group, n in zip((*POLITICAL, "unknown", "none"), plan["benchmark_counts"])]
    benchmark = pd.concat(selections, ignore_index=True)
    benchmark["sample_id"] = benchmark.comment_id.map(lambda c: sid(study, c))
    benchmark.to_csv(study / "benchmark.csv", index=False)
    corpus["sample_id"] = corpus.comment_id.map(lambda c: sid(study, c))
    corpus["fold"] = partition_videos(corpus, plan["seed"])
    corpus.to_csv(study / "corpus.csv", index=False)
