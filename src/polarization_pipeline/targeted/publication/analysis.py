from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..common import atomic_json, read_csv, stamp
from ..metrics import collapse_events, clustered_inference, holm, user_scores
from ..registry import load_registry
from .state import output, seal, verify
from .measurement import validate_histories, screened_users, coverage_tables, precision_assessment


def events_from_annotations(frame, registry):
    targets = {t["target_id"]: t for t in load_registry(registry, frozen=True)["targets"]}
    rows = []
    for row in frame.to_dict("records"):
        for item in json.loads(row["annotation_json"]):
            target = targets.get(item["target_id"], {})
            rows.append({**row, **item, "target_group": target.get("target_group", "unknown"),
                         "corpus": "publication_union", "accepted": True})
    columns = ["comment_id", "target_id", "target_group", "valence", "accepted", "user_id", "post_id", "channel_id", "comment_published_at", "party", "corpus"]
    return collapse_events(pd.DataFrame(rows, columns=columns))


def scoring_input(events):
    """Explicit adapter: old metrics filter main; origin remains in persisted study artifacts."""
    if not events.corpus.isin(["publication_union"]).all():
        raise ValueError("Componente de corpus inesperado")
    return events.assign(corpus="main")


def scores(events, settings, **kwargs):
    return user_scores(scoring_input(events), settings, seed=settings["seed"], **kwargs)


def analyze(settings, plan, study, registry, *, stage="provisional"):
    from .annotations import cohort_samples, close_reference
    from ...reporting import validate_results_section, update_study_section
    verify(study, frozen=True)
    if stage == "final":
        validate_results_section(settings["_root"] / "AGENTS.md")
    sample = cohort_samples(study, registry, stage)
    ranked = read_csv(study / "eligible_users.csv")
    ranked["rank"] = ranked["rank"].astype(int)
    corpus = read_csv(study / "corpus.csv")
    validate_histories(sample, ranked, corpus)
    used = set(sample.user_id)
    events = events_from_annotations(sample, registry)
    all_scores = scores(events, settings)
    screened = screened_users(sample, events, all_scores, ranked, settings, plan["comparable_users"])
    paired = screened.loc[screened.paired].sort_values("rank")
    selected = paired.iloc[:plan["comparable_users"]]
    # Keep every screened user in audit; the primary sample is the first K qualifiers.
    included = set(selected.user_id)
    primary = events.loc[events.user_id.isin(included)].copy()
    if stage == "final" and len(included) < plan["comparable_users"] and len(used) < len(ranked):
        raise ValueError("Faltan comparables: continuar revisión/next antes del cierre")
    destination = output(settings, study) / f"analysis_{stage}"
    destination.mkdir(exist_ok=False)
    screened.to_csv(destination / "screened_user_scores.csv", index=False)
    selected.to_csv(destination / "primary_user_scores.csv", index=False)
    events.to_csv(destination / "events.csv", index=False)
    options = {**settings, "bootstrap_iterations": plan["bootstrap_iterations"]}
    if included:
        intervals = clustered_inference(scoring_input(primary), options)
        secondary = intervals.contrast.ne("gap")
        intervals.loc[secondary, "p_holm"] = holm(intervals.loc[secondary, "p_bootstrap"].tolist())
        intervals.loc[~secondary, "p_holm"] = np.nan
    else:
        intervals = pd.DataFrame(columns=["contrast", "estimate", "ci_low", "ci_high", "status"])
    intervals.to_csv(destination / "contrasts.csv", index=False)
    precision = precision_assessment(intervals, plan["planned_half_width"])
    coverage, composition, support = coverage_tables(corpus, sample, events, included, registry)
    coverage.to_csv(destination / "coverage.csv", index=False)
    composition.to_csv(destination / "event_composition.csv", index=False)
    support.to_csv(destination / "annotation_support.csv", index=False)
    sensitivity = []
    targets = {t["target_id"]: t for t in load_registry(registry)["targets"]}
    target_counts = {}
    for value in sample.annotation_json:
        for item in json.loads(value):
            if targets.get(item["target_id"], {}).get("target_group") in ("izquierda", "derecha"):
                target_counts[item["target_id"]] = target_counts.get(item["target_id"], 0)+1
    variants = [("reverse_A_B", scores(events, settings, reverse=True)),
                ("balanced_video", scores(events, settings, balance_unit="post_id"))]
    for target in sorted(target_counts, key=lambda t: (-target_counts[t], t))[:3]:
        altered = sample.copy()
        altered["annotation_json"] = altered.annotation_json.map(lambda v: json.dumps([i for i in json.loads(v) if i["target_id"] != target]))
        variants.append(("exclude_"+target, scores(events_from_annotations(altered, registry), settings)))
    original = sample.loc[sample.component.eq("historical_main")]
    variants.append(("historical_main_only", scores(events_from_annotations(original, registry), settings)))
    for name, frame in variants:
        frame = frame.loc[frame.user_id.isin(included)]
        sensitivity.append(dict(variant=name, comparable=int(frame.paired.sum()), gap=number(frame.loc[frame.paired, "gap"].mean())))
    pd.DataFrame(sensitivity).to_csv(destination / "sensitivities.csv", index=False)
    gap = selected.gap.mean() if len(selected) else np.nan
    report = dict(stage=stage, study=study.name, screened_users=len(used), comparable_users=len(included),
        comparable_screened_total=int(all_scores.paired.sum()),
        target_comparable_users=plan["comparable_users"], frame_exhausted=len(used) == len(ranked),
        eligible_frame_users=len(ranked), snapshot_comments=len(corpus), screened_comments=len(sample),
        primary_comments=int(sample.user_id.isin(included).sum()), screened_events=len(events), primary_events=len(primary),
        screened_frame_user_fraction=len(used)/len(ranked) if len(ranked) else None,
        primary_screened_user_fraction=len(included)/len(used) if used else None,
        measurement_basis="human_annotations" if stage == "final" else "ai_proposals",
        model_readiness_required=False, production_enabled=False, automatic_expansion_enabled=False,
        benchmark_required_for_primary_measurement=False, precision=precision,
        gap=number(gap), annotation_origin="ai_proposed" if stage == "provisional" else "single_human_reviewed",
        independently_validated=False, test_opened=False, inference_scope="Usuarios comparables en el marco explícito observado; no votantes",
        planned_design_effect=plan["planned_design_effect"], planned_half_width=plan["planned_half_width"])
    atomic_json(destination / "summary.json", report)
    text = [f"# Polarización dirigida — {stage}", "", f"Usuarios examinados: {len(used)}; comparables incluidos: {len(included)}.",
            f"Gap medio: {number(gap)}. Consulte contrasts.csv para incertidumbre y cobertura.", "",
            f"Precisión estadística: {precision['precision_status']}; semiancho IC95% observado: {precision['observed_half_width']}; meta prevista: {plan['planned_half_width']}.",
            f"Interpretación del intervalo del gap: {precision['gap_evidence']}. No determina por sí sola la interpretación de las sensibilidades.",
            f"Comentarios del snapshot/examinados/primarios: {len(corpus)}/{len(sample)}/{int(sample.user_id.isin(included).sum())}.",
            f"Usuarios del marco elegible/examinados/primarios: {len(ranked)}/{len(used)}/{len(included)}. Estas fracciones no son probabilidades de inclusión.",
            "coverage.csv desglosa fuentes; event_composition.csv cuenta eventos colapsados por bloque; annotation_support.csv separa objetivos desconocidos, mezclas y ausencias.",
            "screened_user_scores.csv registra motivos de exclusión; pueden concurrir varios motivos y no deben sumarse como usuarios distintos.",
            "La preparación del análisis, su precisión estadística y el desempeño del clasificador son condiciones distintas. No se exige un modelo para esta medición.",
            "Una precisión insuficiente o un intervalo que incluye cero no activa nuevas muestras, ajustes de umbral ni cambios de criterio.", "",
            "Provisional IA: no es referencia humana." if stage == "provisional" else "Referencia de un humano; asistencia declarada en la cohorte.",
            "La afinidad es operacional. Gap positivo indica favoritismo relativo; no implica por sí solo valoración externa negativa.",
            "La captura tardía, la selección de canales, los actores desconocidos y la selección de usuarios limitan la transferencia."]
    (destination / "report.md").write_text("\n".join(text)+"\n")
    if len(selected):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        ax.hist(selected.gap, bins=30); ax.set(xlabel="Gap individual", ylabel="Usuarios", title=f"Polarización expresada ({stage})")
        fig.savefig(destination / "gap.png", dpi=200, bbox_inches="tight"); plt.close(fig)
    if stage == "final":
        for folder in sorted((study / "annotations").glob("cohort_*")):
            close_reference(study, folder.name, registry)
    seal(destination, [p.name for p in destination.iterdir() if p.is_file()], status="complete", stage=stage)
    verify(study, frozen=True)
    if stage == "final":
        heading = "#### Estudio de publicación (targeted-publication-v1)"
        update_study_section(settings["_root"] / "AGENTS.md", heading, heading+"\n\n"+
            f"Estudio `{study.name}`; {len(used)} usuarios examinados, {len(included)} comparables; gap={number(gap)}.\n\n"+
            f"IC95% gap=[{precision['gap_ci_low']}, {precision['gap_ci_high']}]; precisión={precision['precision_status']}; evidencia={precision['gap_evidence']}.\n\n"+
            f"Medición desde anotaciones humanas, independiente de umbrales del modelo; {len(sample)} comentarios examinados y {len(primary)} eventos primarios.\n\n"+
            f"Referencia de un humano, cohorte asistida; intervalos y sensibilidades en `{destination}`.\n"+
            "Alcance condicional a los usuarios/actores/videos observados. Los resultados históricos se conservan.")
    return destination


def number(value):
    return float(value) if np.isfinite(value) else None
