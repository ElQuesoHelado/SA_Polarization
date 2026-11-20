"""Incremental local preparation; no services, annotations or final sampling."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
from collections import Counter
from pathlib import Path

import pandas as pd

from ..common import atomic_json, in_window, read_csv, sha256, stamp
from ..diagnostics import EVENT_COLUMNS, opportunities
from ..registry import Matcher, load_registry
from .state import lock, output, seal, verify, verify_seal

CANDIDATES = "_cached_candidates"
EXCLUSIONS = ["comment_id", "post_id", "comment_published_at", "reason"]


class SourceChanged(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def context(settings, registry):
    package = Path(__file__).resolve().parent
    return digest(dict(schema_version=1, registry=sha256(registry), periods=settings["source"]["youtube"]["periods"],
        code={str(p.name): sha256(p) for p in (Path(__file__), package / "data.py", package.parent / "registry.py", package.parent / "common.py")}))


def inventory(study):
    sources = [("historical", study / "historical.csv", sha256(study / "historical.csv"))]
    states = []
    for video in read_csv(study / "videos.csv").itertuples():
        path = study / "raw_capture" / f"{video.post_id}.json"
        if not path.exists():
            states.append((video.post_id, "not_started"))
            continue
        raw = path.read_bytes()
        state = json.loads(raw)
        status = state["status"]
        if status not in ("complete", "incomplete", "unavailable") or state["video"]["post_id"] != video.post_id:
            raise ValueError("Identidad o estado de captura incompatible")
        states.append((video.post_id, status))
        if status == "complete":
            sources.append(("capture", path, hashlib.sha256(raw).hexdigest()))
    return sources, states


def capture_rows(state, periods):
    rows, excluded = [], []
    comments = list(state["comments"].values())
    dates = pd.Series([r["comment_published_at"] for r in comments], dtype=str)
    # The cold freeze parses each timestamp separately. Mixed parsing preserves
    # that behavior when API rows contain different ISO timestamp formats.
    valid = in_window(pd.to_datetime(dates, format="mixed", errors="coerce", utc=True), periods)
    for comment, keep in zip(comments, valid):
        if not keep:
            excluded.append(dict(comment_id=comment["comment_id"], post_id=state["video"]["post_id"],
                comment_published_at=comment["comment_published_at"], reason="comment_outside_window_or_invalid_date"))
            continue
        parent = state["comments"].get(comment.get("parent_id", ""), {})
        rows.append({**state["video"], **comment, "component": "api_capture", "corpus": "publication_union",
            "parent_text": parent.get("text", ""), "captured_at": state["finished_at"], "provenance": "youtube_api_v3"})
    return rows, excluded


def fragment(settings, study, registry, source, namespace, *, write=True):
    kind, path, expected = source
    destination = study / "local_preparation_cache" / namespace / digest([kind, expected])
    if destination.exists():
        manifest = verify_seal(destination)
        if manifest.get("source_sha256") != expected or manifest.get("context") != namespace or manifest.get("kind") != kind:
            raise ValueError("Caché incompatible con su fuente")
        frame = read_csv(destination / "rows.csv")
        for name, dtype in manifest["numeric_dtypes"].items():
            frame[name] = pd.to_numeric(frame[name].mask(frame[name].eq(""))).astype(dtype)
        for name in manifest["boolean_columns"]:
            if not frame[name].isin(["True", "False"]).all():
                raise ValueError("Booleanos de caché inválidos")
            frame[name] = frame[name].eq("True")
        return frame, read_csv(destination / "exclusions.csv"), True
    if sha256(path) != expected:
        raise SourceChanged("Fuente modificada durante preparación; reintentar")
    excluded = []
    if kind == "historical":
        frame = read_csv(path)
    else:
        state = json.loads(path.read_text())
        if state["status"] != "complete":
            raise SourceChanged("La captura ya no está completa")
        rows, excluded = capture_rows(state, settings["source"]["youtube"]["periods"])
        frame = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["comment_id", "post_id", "user_id", "text", "comment_published_at"])
    if CANDIDATES in frame:
        raise ValueError("Columna reservada de caché en la fuente")
    numeric = {name: str(dtype) for name, dtype in frame.dtypes.items() if dtype.kind in "iuf"}
    booleans = [name for name, dtype in frame.dtypes.items() if dtype.kind == "b"]
    matcher = Matcher(load_registry(registry, frozen=True))
    frame[CANDIDATES] = [json.dumps(matcher.find(r.text, r.comment_published_at), ensure_ascii=False) for r in frame.itertuples()]
    if sha256(path) != expected:
        raise SourceChanged("Fuente modificada durante preparación; reintentar")
    exclusions = pd.DataFrame(excluded, columns=EXCLUSIONS)
    if write:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".building-", dir=destination.parent))
        try:
            frame.to_csv(temporary / "rows.csv", index=False)
            exclusions.to_csv(temporary / "exclusions.csv", index=False)
            seal(temporary, ["rows.csv", "exclusions.csv"], context=namespace, kind=kind, source_sha256=expected,
                numeric_dtypes=numeric, boolean_columns=booleans)
            temporary.rename(destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)  # only our unpublished temporary directory
    return frame, exclusions, False


def assemble(settings, study, registry, sources=None, *, write=True):
    from .data import merge_comments
    namespace = context(settings, registry)
    sources = inventory(study)[0] if sources is None else sources
    historical, new, exclusions = [], [], []
    hits = 0
    for index, source in enumerate(sources):
        frame, omitted, hit = fragment(settings, study, registry, source, namespace, write=write)
        hits += hit
        # Preserve the original source scalar types and missing numeric values.
        records = frame.to_dict("records")
        (historical if source[0] == "historical" else new).extend(records)
        exclusions.extend(omitted.to_dict("records"))
        if write and (index == 0 or index % 500 == 0):
            print(f"Preparación local: {index+1}/{len(sources)} fuentes; {hits} reutilizadas", flush=True)
    union, versions = merge_comments(historical, new)
    candidates = union.pop(CANDIDATES).tolist()
    if CANDIDATES in versions:
        versions = versions.drop(columns=CANDIDATES)
    union["corpus"] = "publication_union"
    return union, versions, pd.DataFrame(exclusions, columns=EXCLUSIONS), candidates, dict(
        sources=len(sources), cache_hits=hits, cache_misses=len(sources)-hits, historical_comments=len(historical), capture_rows=len(new))


def prepare_pass(settings, plan, study, registry):
    verify(study)
    if (study / "freeze.json").exists():
        return dict(status="snapshot_frozen")
    sources, states = inventory(study)
    namespace = context(settings, registry)
    signature = digest(dict(context=namespace, sources=[(kind, str(path), value) for kind, path, value in sources], states=states))
    pointer = study / "local_preparation_cache/latest.json"
    if pointer.exists():
        prior = json.loads(pointer.read_text())
        if prior["signature"] == signature:
            verify_seal(Path(prior["report"]))
            return dict(status="unchanged", report=prior["report"])
    union, versions, exclusions, candidates, cache = assemble(settings, study, registry, sources)
    # Never publish a report describing a mixture of source versions.
    if any(sha256(path) != expected for _, path, expected in sources):
        raise SourceChanged("Fuentes cambiaron durante preparación; posponer informe")
    verify(study)
    events, support = [], Counter()
    for row, value in zip(union.itertuples(), candidates):
        items = json.loads(value)
        groups = {i["target_group"] for i in items} & {"izquierda", "derecha"}
        support["known_block_comments"] += bool(groups)
        support["unknown_only_comments"] += bool(items) and not groups
        support["no_candidate_comments"] += not items
        for group in groups:
            if row.user_id:
                events.append((row.user_id, row.comment_id, row.post_id, row.channel_id, row.party, row.comment_published_at[:7], group))
    users = Counter(union.loc[union.user_id.ne(""), "user_id"])
    opportunity = opportunities(pd.DataFrame(events, columns=EVENT_COLUMNS), users, settings, seed=plan["seed"])
    destination = output(settings, study) / "local_preparation" / stamp().replace(":", "")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".building-", dir=destination.parent))
    distributions = []
    union["month"] = union.comment_published_at.str[:7]
    for dimension in ("party", "month", "channel_id", "comment_type"):
        for value, count in union[dimension].value_counts().items():
            distributions.append(dict(dimension=dimension, value=value, comments=int(count)))
    pd.DataFrame(distributions).to_csv(temporary / "coverage.csv", index=False)
    opportunity.to_csv(temporary / "structural_opportunity.csv", index=False)
    summary = dict(status="prepared", partial=True, production_enabled=False, test_opened=False,
        scope="historical_plus_completed_captures", context=namespace, signature=signature,
        capture_status=dict(Counter(status for _, status in states)), comments=len(union),
        new_comments=len(union)-cache["historical_comments"], repeated_versions=len(versions),
        replies=int(union.parent_id.ne("").sum()), empty_texts=int(union.text.str.strip().eq("").sum()),
        comments_without_user=int(union.user_id.eq("").sum()), excluded_capture_rows=len(exclusions),
        identified_users=len(users), potentially_comparable_users=int(opportunity.potentially_paired.sum()),
        support=dict(support), cache=cache, report=str(destination))
    atomic_json(temporary / "summary.json", summary)
    (temporary / "report.md").write_text("# Preparación local parcial\n\n"+
        f"Comentarios únicos: {len(union)}; nuevos: {summary['new_comments']}; respuestas: {summary['replies']}.\n\n"+
        f"Usuarios con oportunidad estructural: {summary['potentially_comparable_users']}; no son comparables afectivos confirmados.\n\n"+
        "No es un snapshot final, una muestra de anotación ni un resultado de polarización. No contiene nuevas predicciones o decisiones humanas.\n")
    seal(temporary, [p.name for p in temporary.iterdir()], signature=signature, partial=True)
    temporary.rename(destination)
    atomic_json(pointer, dict(signature=signature, report=str(destination)))
    return summary


def run(settings, plan, study, registry, *, watch=False):
    with lock(study / "local_preparation.lock"):
        while True:
            try:
                result = prepare_pass(settings, plan, study, registry)
                if result["status"] != "unchanged":
                    print(json.dumps(result, ensure_ascii=False), flush=True)
            except SourceChanged:
                if not watch:
                    raise
                print("Fuente cambiando; se reintentará en la siguiente pasada", flush=True)
                result = dict(status="source_changing")
            if not watch or result["status"] == "snapshot_frozen":
                return result
            time.sleep(60)
