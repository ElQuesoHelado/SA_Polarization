from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .common import POLITICAL, atomic_json, read_csv, sha256, stamp

VALID = ("positive", "negative", "neutral")


def collapse_events(predictions: pd.DataFrame) -> pd.DataFrame:
    frame = predictions.loc[predictions.target_group.isin(POLITICAL)].copy()
    require = ["user_id", "post_id", "channel_id", "comment_published_at", "party", "corpus"]
    if frame.empty:
        return pd.DataFrame(columns=["comment_id", "target_group", "valence", *require])
    rows = []
    for _, group in frame.groupby(["corpus", "comment_id", "target_group"], sort=False):
        if group.groupby("target_id").valence.nunique().gt(1).any():
            raise ValueError("Predicciones incompatibles para el mismo comentario y objetivo")
        group = group.drop_duplicates("target_id")
        accepted = group.accepted.astype(str).str.lower().isin(["true", "1"])
        labels = set(group.loc[accepted, "valence"])
        if not accepted.all():
            valence = "abstained"
        elif "mixed" in labels or {"positive", "negative"} <= labels:
            valence = "mixed"
        elif "positive" in labels:
            valence = "positive"
        elif "negative" in labels:
            valence = "negative"
        elif "neutral" in labels:
            valence = "neutral"
        else:
            valence = "not_evaluable"
        first = group.iloc[0]
        rows.append({key: first[key] for key in ("comment_id", "target_group", *require)} | {"valence": valence})
    return pd.DataFrame(rows)


def partition_videos(events: pd.DataFrame, seed: int = 42) -> pd.Series:
    """Outcome-independent split, keyed only by video; stable across sampling/replies."""
    def split(video):
        value = int(hashlib.sha256(f"affinity:{seed}:{video}".encode()).hexdigest()[:12], 16)
        return "A" if value % 2 == 0 else "B"
    return events.post_id.map(split)


def user_scores(events: pd.DataFrame, settings: dict, *, seed: int = 42, reverse: bool = False,
                channel_weights: dict | None = None, evaluation_month: str | None = None,
                balance_unit: str | None = None) -> pd.DataFrame:
    events = events.loc[events.user_id.ne("") & events.corpus.eq("main")].copy()
    users = pd.Index(events.user_id.unique(), name="user_id")
    if len(users) == 0:
        return pd.DataFrame(columns=["user_id", "ingroup", "paired", "AP_In", "AP_Out", "AP_target", "spread", "in_rate", "out_rate", "gap"])
    events["fold"] = partition_videos(events, seed)
    events["weight"] = events.channel_id.map(channel_weights).fillna(0) if channel_weights is not None else 1.0
    events = events.loc[events.weight.gt(0) & events.valence.isin(VALID)]
    assignment_fold, evaluation_fold = ("B", "A") if reverse else ("A", "B")
    assignment = events.loc[events.fold.eq(assignment_fold) & events.valence.eq("positive")]
    counts = assignment.groupby(["user_id", "target_group"]).weight.sum().unstack(fill_value=0).reindex(index=users, columns=POLITICAL, fill_value=0)
    videos = assignment.groupby(["user_id", "target_group"]).post_id.nunique().unstack(fill_value=0).reindex(index=users, columns=POLITICAL, fill_value=0)
    maximum = counts.max(axis=1)
    dominant = counts.idxmax(axis=1)
    share = maximum / counts.sum(axis=1).replace(0, np.nan)
    selected_videos = np.where(dominant.eq("izquierda"), videos.izquierda, videos.derecha)
    determined = counts.eq(maximum, axis=0).sum(axis=1).eq(1) & maximum.ge(2) & share.ge(settings["affinity_positive_share"]) & (selected_videos >= settings["minimum_positive_videos"])
    ingroup = dominant.where(determined, "Undetermined")
    evaluation = events.loc[events.fold.eq(evaluation_fold)]
    if evaluation_month is not None:
        dates = pd.to_datetime(evaluation.comment_published_at, utc=True)
        evaluation = evaluation.loc[dates.dt.strftime("%Y-%m").eq(evaluation_month)]
    if balance_unit is not None:
        if balance_unit not in ("channel_id", "post_id"):
            raise ValueError("Unidad de equilibrio no soportada")
        evaluation = evaluation.copy()
        unit_sizes = evaluation.groupby(balance_unit).size()
        evaluation["weight"] /= evaluation[balance_unit].map(unit_sizes)
    evaluation = evaluation.assign(sign=evaluation.valence.map({"positive": 1, "negative": -1, "neutral": 0}))
    evaluation["balance"] = evaluation.sign * evaluation.weight
    balances = evaluation.groupby(["user_id", "target_group"]).balance.sum().unstack(fill_value=0).reindex(index=users, columns=POLITICAL, fill_value=0)
    totals = evaluation.groupby(["user_id", "target_group"]).weight.sum().unstack(fill_value=0).reindex(index=users, columns=POLITICAL, fill_value=0)
    total_events = evaluation.groupby("user_id").comment_id.size().reindex(users, fill_value=0)
    video_counts = evaluation.groupby("user_id").post_id.nunique().reindex(users, fill_value=0)
    select_left = ingroup.eq("izquierda")
    n_in = pd.Series(np.where(select_left, totals.izquierda, totals.derecha), index=users)
    n_out = pd.Series(np.where(select_left, totals.derecha, totals.izquierda), index=users)
    ap_in = pd.Series(np.where(select_left, balances.izquierda, balances.derecha), index=users)
    ap_out = pd.Series(np.where(select_left, balances.derecha, balances.izquierda), index=users)
    paired = determined & n_in.gt(0) & n_out.gt(0) & total_events.ge(settings["evaluation_min_interactions"]) & video_counts.ge(settings["evaluation_min_videos"])
    result = pd.DataFrame({"ingroup": ingroup, "paired": paired, "N_in": n_in, "N_out": n_out,
        "evaluation_interactions": total_events, "evaluation_videos": video_counts,
        "AP_In": ap_in.where(determined & totals.sum(axis=1).gt(0)),
        "AP_Out": ap_out.where(determined & totals.sum(axis=1).gt(0)),
        "out_observed": n_out.gt(0) & determined,
        "AP_target": (ap_in - ap_out).where(determined & totals.sum(axis=1).gt(0)),
        "spread": np.sqrt((balances ** 2).sum(axis=1) / totals.sum(axis=1).replace(0, np.nan)).where(determined),
        "in_rate": (ap_in / n_in.replace(0, np.nan)).where(paired),
        "out_rate": (ap_out / n_out.replace(0, np.nan)).where(paired),
    })
    result["gap"] = result.in_rate - result.out_rate
    return result.reset_index()


def summaries(scores: pd.DataFrame, user_weights: dict | None = None) -> dict:
    paired = scores.loc[scores.paired].copy()
    weights = paired.user_id.map(user_weights).fillna(0) if user_weights is not None else pd.Series(1.0, index=paired.index)
    def average(values, selected=None):
        mask = values.notna() & weights.gt(0)
        if selected is not None:
            mask &= selected
        return float(np.average(values.loc[mask], weights=weights.loc[mask])) if mask.any() else np.nan
    result = {name: average(paired[name]) for name in ("in_rate", "out_rate", "gap")}
    for group in POLITICAL:
        result[f"gap_{group}"] = average(paired.gap, paired.ingroup.eq(group))
    result["gap_difference_right_minus_left"] = result["gap_derecha"] - result["gap_izquierda"]
    return result


def holm(pvalues: list[float]) -> list[float]:
    values = np.asarray(pvalues)
    adjusted = np.full(len(values), np.nan)
    valid = np.flatnonzero(np.isfinite(values))
    order = valid[np.argsort(values[valid])]
    previous = 0.0
    for rank, index in enumerate(order):
        previous = max(previous, min(1.0, values[index] * (len(order) - rank)))
        adjusted[index] = previous
    return adjusted.tolist()


def clustered_inference(events: pd.DataFrame, settings: dict, *, evaluation_month: str | None = None) -> pd.DataFrame:
    """Crossed-factor bootstrap: channel draws alter observations; user draws weight people, not their counts."""
    primary = user_scores(events, settings, seed=settings["seed"], evaluation_month=evaluation_month)
    point = summaries(primary)
    rng = np.random.default_rng(settings["seed"])
    users = primary.user_id.to_numpy()
    # Channels nested in source strata; users cross channels. Video clustering is contained by channel.
    strata = events[["channel_id", "party"]].drop_duplicates().groupby("party")
    channel_groups = [group.channel_id.to_numpy() for _, group in strata]
    draws = {key: [] for key in point}
    for iteration in range(settings["bootstrap_iterations"]):
        channel_weights = {}
        for channels in channel_groups:
            counts = rng.multinomial(len(channels), np.full(len(channels), 1 / len(channels)))
            channel_weights.update(zip(channels, counts))
        user_counts = rng.multinomial(len(users), np.full(len(users), 1 / len(users))) if len(users) else []
        score = user_scores(events, settings, seed=settings["seed"], channel_weights=channel_weights, evaluation_month=evaluation_month)
        values = summaries(score, dict(zip(users, user_counts)))
        for key in draws:
            draws[key].append(values[key])
        if (iteration + 1) % 100 == 0:
            print(f"Bootstrap {evaluation_month or 'global'}: {iteration + 1}/{settings['bootstrap_iterations']}", flush=True)
    rows = []
    for key, value in point.items():
        sample = np.asarray(draws[key])
        sample = sample[np.isfinite(sample)]
        sufficient = np.isfinite(value) and len(sample) >= max(10, settings["bootstrap_iterations"] * 0.8)
        low, high = np.quantile(sample, [0.025, 0.975]) if sufficient else (np.nan, np.nan)
        p = (1 + np.sum(np.abs(sample - value) >= abs(value))) / (len(sample) + 1) if sufficient else np.nan
        rows.append({"contrast": key, "estimate": value, "ci_low": low, "ci_high": high, "p_bootstrap": p,
                     "valid_replicates": len(sample), "status": "estimated" if sufficient else "insufficient_coverage"})
    result = pd.DataFrame(rows)
    result["p_holm"] = holm(result.p_bootstrap.tolist())
    return result


def activity_analysis(frame: pd.DataFrame, settings: dict, output: Path) -> None:
    frame = frame.loc[frame.user_id.ne("")].copy()
    activity = frame.groupby(["user_id", "party"]).size().unstack(fill_value=0).reindex(columns=[*POLITICAL, "neutral"], fill_value=0)
    activity["political_comments"] = activity.izquierda + activity.derecha
    activity["both_blocks"] = activity.izquierda.gt(0) & activity.derecha.gt(0)
    activity["right_share"] = activity.derecha / activity.political_comments.replace(0, np.nan)
    activity["concentration"] = (2 * activity.right_share - 1).abs()
    activity.to_csv(output / "participation_users.csv")
    sensitivity = []
    for minimum in (1, 3, 5, 10, 20):
        subset = activity.loc[activity.political_comments.ge(minimum)]
        sensitivity.append({"minimum_political_comments": minimum, "users": len(subset),
            "both_blocks_share": float(subset.both_blocks.mean()) if len(subset) else np.nan,
            "concentration_mean": float(subset.concentration.mean()) if len(subset) else np.nan})
    pd.DataFrame(sensitivity).to_csv(output / "participation_activity_thresholds.csv", index=False)
    political = frame.loc[frame.party.isin(POLITICAL)].copy()
    political["month"] = pd.to_datetime(political.comment_published_at, utc=True).dt.strftime("%Y-%m")
    users, user_index = np.unique(political.user_id, return_inverse=True)
    counts = np.bincount(user_index, minlength=len(users))
    eligible = counts >= 5
    right = political.party.eq("derecha").to_numpy(dtype=int)
    month_indices = [indices for indices in political.reset_index(drop=True).groupby("month").indices.values()]
    def measure(labels):
        positive = np.bincount(user_index, weights=labels, minlength=len(users))
        if not eligible.any():
            return {"both_blocks": np.nan, "concentration": np.nan}
        return {"both_blocks": float(np.mean((positive[eligible] > 0) & (positive[eligible] < counts[eligible]))),
                "concentration": float(np.mean(np.abs(2 * positive[eligible] / counts[eligible] - 1)))}
    point = measure(right)
    rng = np.random.default_rng(settings["seed"])
    null = {key: [] for key in point}
    for _ in range(settings["permutations"]):
        shuffled = right.copy()
        # Equivalent to shuffling channel labels: retains channel/month volumes and each user's activity.
        for indices in month_indices:
            shuffled[indices] = rng.permutation(right[indices])
        values = measure(shuffled)
        for key in null:
            null[key].append(values[key])
    rows = []
    for key, observed in point.items():
        values = np.asarray(null[key])
        valid = np.isfinite(values)
        extreme = values <= observed if key == "both_blocks" else values >= observed
        rows.append({"metric": key, "observed": observed, "null_mean": float(values[valid].mean()) if valid.any() else np.nan,
                     "p_permutation": (1 + extreme[valid].sum()) / (1 + valid.sum()) if np.isfinite(observed) else np.nan,
                     "eligible_users": int(eligible.sum()), "minimum_comments": 5})
    result = pd.DataFrame(rows)
    result["p_holm"] = holm(result.p_permutation.tolist())
    result.to_csv(output / "participation_null.csv", index=False)
    # A second null retains every user-video/channel interaction. Only channel pool labels
    # are permuted, with the same number of channels in each political pool.
    channels, channel_index = np.unique(political.channel_id, return_inverse=True)
    matrix = np.zeros((len(users), len(channels)), dtype=np.int32)
    if len(users):
        np.add.at(matrix, (user_index, channel_index), 1)
    source_mapping = political[["channel_id", "party"]].drop_duplicates()
    if source_mapping.channel_id.duplicated().any():
        raise ValueError("Un canal tiene múltiples etiquetas editoriales; resolver la clasificación antes de analizar")
    right_channels = source_mapping.set_index("channel_id").party.reindex(channels).eq("derecha").to_numpy(copy=True)
    label_null = {key: [] for key in point}
    for _ in range(settings["permutations"]):
        labels = rng.permutation(right_channels)
        positive = matrix[:, labels].sum(axis=1)
        values = {"both_blocks": float(np.mean((positive[eligible] > 0) & (positive[eligible] < counts[eligible]))) if eligible.any() else np.nan,
                  "concentration": float(np.mean(np.abs(2 * positive[eligible] / counts[eligible] - 1))) if eligible.any() else np.nan}
        for key in label_null:
            label_null[key].append(values[key])
    fixed_rows = []
    for key, observed in point.items():
        values = np.asarray(label_null[key])
        valid = np.isfinite(values)
        extreme = values <= observed if key == "both_blocks" else values >= observed
        fixed_rows.append({"metric": key, "observed": observed, "null_mean": float(values[valid].mean()) if valid.any() else np.nan,
                           "p_permutation": (1 + extreme[valid].sum()) / (1 + valid.sum()) if np.isfinite(observed) else np.nan,
                           "eligible_users": int(eligible.sum()), "minimum_comments": 5,
                           "null": "fixed_network_channel_label_permutation"})
    fixed_result = pd.DataFrame(fixed_rows)
    # Four predeclared complementary tests (two statistics, two nulls).
    adjusted = holm(result.p_permutation.tolist() + fixed_result.p_permutation.tolist())
    result["p_holm"] = adjusted[:len(result)]
    fixed_result["p_holm"] = adjusted[len(result):]
    result.to_csv(output / "participation_null.csv", index=False)
    fixed_result.to_csv(output / "participation_channel_label_null.csv", index=False)
    # Small channel projection; no quadratic graph over all users.
    unique = political[["user_id", "channel_id"]].drop_duplicates()
    overlaps = []
    audiences = {key: set(group.user_id) for key, group in unique.groupby("channel_id")}
    channels = sorted(audiences)
    for i, a in enumerate(channels):
        for b in channels[i + 1:]:
            intersection = len(audiences[a] & audiences[b])
            union = len(audiences[a] | audiences[b])
            overlaps.append({"channel_a": a, "channel_b": b, "shared_users": intersection, "jaccard": intersection / union if union else np.nan})
    pd.DataFrame(overlaps, columns=["channel_a", "channel_b", "shared_users", "jaccard"]).to_csv(output / "channel_overlap.csv", index=False)


def analyze_targeted(settings: dict, run: Path, *, smoke: bool = False) -> Path:
    from ..reporting import validate_results_section
    if not smoke:
        validate_results_section(settings["_root"] / "AGENTS.md")
    prediction_manifest = json.loads((run / "prediction_manifest.json").read_text())
    evaluation = json.loads((run / "model" / "evaluation.json").read_text())
    if not smoke and evaluation.get("status") != "passed":
        raise ValueError("El modelo no superó la prueba humana; no se generan resultados de producción")
    if sha256(run / "predictions.csv") != prediction_manifest["predictions_sha256"] or sha256(run / "corpus_main.csv") != prediction_manifest["corpus_main_sha256"]:
        raise ValueError("Predicciones o corpus cambiaron desde la inferencia")
    if not smoke and sha256(run / "model" / "evaluation.json") != prediction_manifest["evaluation_sha256"]:
        raise ValueError("La evaluación del modelo cambió después de inferir")
    output = settings["outputs"] / (run.name + ("_smoke" if smoke else ""))
    output.mkdir(parents=True, exist_ok=False)
    predictions = read_csv(run / "predictions.csv")
    events = collapse_events(predictions)
    events.to_csv(output / "target_events.csv", index=False)
    scores = user_scores(events, settings, seed=settings["seed"])
    scores.to_csv(output / "ap_individual_targeted.csv", index=False)
    scores.groupby("ingroup").agg(users=("user_id", "size"), paired_users=("paired", "sum"), AP_In=("AP_In", "mean"), AP_Out=("AP_Out", "mean"), AP_target=("AP_target", "mean"), spread=("spread", "mean"), gap=("gap", "mean")).to_csv(output / "group_summary.csv")
    inference = clustered_inference(events, settings)
    inference.to_csv(output / "contrasts.csv", index=False)
    sensitivity = []
    for seed, reverse in [(settings["seed"], True), *((seed, False) for seed in range(43, 53))]:
        value = user_scores(events, settings, seed=seed, reverse=reverse)
        sensitivity.append({"seed": seed, "reverse": reverse, "paired_users": int(value.paired.sum()), **summaries(value)})
    for minimum in (1, 3):
        variant = {**settings, "minimum_positive_videos": minimum}
        sensitivity.append({"variant": f"positive_videos_{minimum}", **summaries(user_scores(events, variant, seed=settings["seed"]))})
    for unit in ("channel_id", "post_id"):
        sensitivity.append({"variant": f"evaluation_balanced_{unit}", **summaries(user_scores(events, settings, seed=settings["seed"], balance_unit=unit))})
    for channel in events.channel_id.unique():
        sensitivity.append({"variant": "leave_channel_out", "channel_id": channel, **summaries(user_scores(events.loc[events.channel_id.ne(channel)], settings, seed=settings["seed"]))})
    for threshold in (0.70, 0.80, 0.90):
        variant = predictions.copy()
        variant["accepted"] = variant.confidence.astype(float).ge(threshold)
        if "context_windowed" in variant:
            variant["accepted"] &= ~variant.context_windowed.str.lower().isin(["true", "1"])
        sensitivity.append({"variant": f"confidence_{threshold}", **summaries(user_scores(collapse_events(variant), settings, seed=settings["seed"]))})
    for seed in settings.get("model_seeds", []):
        columns = [f"seed_{seed}_p_{label}" for label in ("positive", "negative", "neutral", "mixed", "not_evaluable")]
        if not set(columns) <= set(predictions.columns):
            continue
        variant = predictions.copy()
        probs = variant[columns].astype(float).to_numpy()
        labels = ["positive", "negative", "neutral", "mixed", "not_evaluable"]
        variant["valence"] = [labels[i] for i in probs.argmax(axis=1)]
        calibration = json.loads((run / "model" / "calibration.json").read_text())
        variant["accepted"] = [confidence >= calibration["thresholds"][label] for label, confidence in zip(variant.valence, probs.max(axis=1))]
        variant["accepted"] &= ~variant.context_windowed.str.lower().isin(["true", "1"])
        sensitivity.append({"variant": f"model_seed_{seed}", **summaries(user_scores(collapse_events(variant), settings, seed=settings["seed"]))})
    for actor in predictions.target_id.value_counts().head(5).index:
        variant = predictions.loc[predictions.target_id.ne(actor)]
        sensitivity.append({"variant": "leave_dominant_actor_out", "actor": actor, **summaries(user_scores(collapse_events(variant), settings, seed=settings["seed"]))})
    panel_events = events.loc[events.corpus.eq("audit_panel")].copy()
    if not panel_events.empty:
        panel_events["corpus"] = "main"
        sensitivity.append({"variant": "panel_top_and_replies", **summaries(user_scores(panel_events, settings, seed=settings["seed"]))})
    pd.DataFrame(sensitivity).to_csv(output / "sensitivity.csv", index=False)
    monthly, monthly_inference = [], []
    months = sorted(pd.to_datetime(events.comment_published_at, utc=True).dt.strftime("%Y-%m").unique())
    for month in months:
        item = user_scores(events, settings, seed=settings["seed"], evaluation_month=month)
        monthly.append({"month": month, "paired_users": int(item.paired.sum()), **summaries(item)})
        if item.paired.any():
            inferred = clustered_inference(events, settings, evaluation_month=month)
            inferred["month"] = month
            monthly_inference.append(inferred)
    pd.DataFrame(monthly).to_csv(output / "monthly.csv", index=False)
    if monthly_inference:
        monthly_contrasts = pd.concat(monthly_inference, ignore_index=True)
        monthly_contrasts["p_holm"] = holm(monthly_contrasts.p_bootstrap.tolist())
        monthly_contrasts.to_csv(output / "monthly_contrasts.csv", index=False)
    else:
        pd.DataFrame(columns=["month", "contrast", "estimate", "ci_low", "ci_high", "p_holm"]).to_csv(output / "monthly_contrasts.csv", index=False)
    activity_analysis(read_csv(run / "corpus_main.csv"), settings, output)
    _figures(scores, inference, output)
    artifacts = {path.name: sha256(path) for path in output.iterdir() if path.is_file()}
    atomic_json(output / "manifest.json", {"status": "complete", "created_at": stamp(), "method_version": settings["method_version"],
                "prediction_manifest": prediction_manifest, "artifacts": artifacts, "smoke": smoke,
                "annotation_protocol": evaluation.get("annotation_protocol", "two_independent_humans"),
                "annotation_limitation": evaluation.get("annotation_limitation"),
                "scope": "Polarización afectiva expresada en participantes observados; sin inferencia poblacional ni causal."})
    if not smoke:
        _update_context(settings, output, scores, inference, annotation_limitation=evaluation.get("annotation_limitation"))
    return output


def _figures(scores: pd.DataFrame, contrasts: pd.DataFrame, output: Path) -> None:
    import os
    os.environ.setdefault("MPLCONFIGDIR", str(output / ".matplotlib-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 5))
    for group in POLITICAL:
        values = scores.loc[scores.ingroup.eq(group) & scores.paired, "gap"].dropna()
        ax.hist(values, bins=30, alpha=0.5, label=f"{group} (n={len(values)})")
    ax.set(xlabel="Contraste de valoración dirigida (grupo propio − opuesto)", ylabel="Usuarios")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "gap_distribution.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    for ax, metric in zip(axes.flat, ("AP_In", "AP_Out", "AP_target", "spread")):
        for group in POLITICAL:
            values = scores.loc[scores.ingroup.eq(group), metric].dropna()
            if len(values):
                ax.hist(values, bins=30, density=True, alpha=0.5, label=group)
        ax.set(xlabel=metric, ylabel="Densidad de usuarios")
        if ax.get_legend_handles_labels()[0]:
            ax.legend()
    fig.suptitle("Indicadores dirigidos: conteos y spread; AP externo puede tener cobertura parcial")
    fig.tight_layout()
    fig.savefig(output / "ap_components.png", dpi=180)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 6))
    valid = contrasts.dropna(subset=["estimate", "ci_low", "ci_high"])
    for position, row in enumerate(valid.to_dict("records")):
        ax.plot([row["ci_low"], row["ci_high"]], [position, position], color="tab:blue")
        ax.scatter([row["estimate"]], [position], color="tab:blue")
    ax.set_yticks(range(len(valid)), labels=valid.contrast.tolist())
    ax.axvline(0, linestyle="--", color="gray")
    ax.set(xlabel="Estimación e IC 95% agrupado", title="Contrastes preespecificados de valoración dirigida")
    fig.tight_layout()
    fig.savefig(output / "contrast_intervals.png", dpi=180)
    plt.close(fig)


def _update_context(settings: dict, output: Path, scores: pd.DataFrame, contrasts: pd.DataFrame, *, annotation_limitation: str | None = None) -> None:
    from ..reporting import update_study_section
    agents = settings["_root"] / "AGENTS.md"
    report = ["", "#### Resultados dirigidos (targeted-v1)", "", f"Actualizado: {stamp()}. Artefactos: `{output.relative_to(settings['_root'])}`.",
              f"Usuarios: {len(scores):,}; contraste con cobertura de ambos bloques: {int(scores.paired.sum()):,}.",
              "Los resultados anteriores se conservan como línea base histórica de sentimiento general.",
              "Las unidades, selección de afinidad y denominadores dirigidos difieren del paper español; la comparación es conceptual.", "",
              "| contraste | estimación | IC 95% | p ajustada Holm |", "|---|---:|---|---:|"]
    fmt = lambda value: "—" if pd.isna(value) else f"{value:.3f}"
    for row in contrasts.to_dict("records"):
        report.append(f"| {row['contrast']} | {fmt(row['estimate'])} | [{fmt(row['ci_low'])}, {fmt(row['ci_high'])}] | {fmt(row['p_holm'])} |")
    report += ["", "| afinidad | usuarios | cobertura pareada | AP_In | AP_Out | AP_target | spread | gap |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for group in POLITICAL:
        subset = scores.loc[scores.ingroup.eq(group)]
        report.append(f"| {group} | {len(subset):,} | {int(subset.paired.sum()):,} | " + " | ".join(fmt(subset[key].mean()) for key in ("AP_In", "AP_Out", "AP_target", "spread", "gap")) + " |")
    report += ["", "AP externo acumulativo con ausencia de observaciones no significa neutralidad. El gap se calcula solo con ambos bloques observados."]
    if annotation_limitation:
        report += ["", f"Referencia de evaluación: {annotation_limitation}"]
    update_study_section(agents, "#### Resultados dirigidos (targeted-v1)", "\n".join(report))


def analyze_activity(settings: dict, run: Path) -> Path:
    """Model-independent complementary study; does not bypass target-valence validation."""
    from ..reporting import update_study_section, validate_results_section
    agents = settings["_root"] / "AGENTS.md"
    validate_results_section(agents)
    source = run / "corpus_main.csv"
    manifest = json.loads((run / "manifest.json").read_text())
    if sha256(source) != manifest["corpus_main_sha256"]:
        raise ValueError("El corpus verificado cambió después de la auditoría")
    if not (run / "video_metadata.csv").exists():
        raise ValueError("Primero verificar fechas de videos mediante YouTube")
    output = settings["outputs"] / (run.name + "_activity")
    output.mkdir(parents=True, exist_ok=False)
    frame = read_csv(source)
    if frame.empty:
        raise ValueError("Sin comentarios verificados en la ventana")
    activity_analysis(frame, settings, output)
    import os
    os.environ.setdefault("MPLCONFIGDIR", str(output / ".matplotlib-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    activity = pd.read_csv(output / "participation_users.csv")
    eligible = activity.loc[activity.political_comments.ge(5)]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(eligible.right_share, bins=np.linspace(0, 1, 21))
    ax.set(xlabel="Proporción de comentarios bajo fuentes de derecha", ylabel="Usuarios", title="Participación entre fuentes políticas (≥5 comentarios)")
    fig.tight_layout()
    fig.savefig(output / "participation_distribution.png", dpi=180)
    plt.close(fig)
    artifacts = {path.name: sha256(path) for path in output.iterdir() if path.is_file()}
    atomic_json(output / "manifest.json", {"status": "complete", "created_at": stamp(), "method": "targeted-v1-activity",
        "corpus_main_sha256": sha256(source), "rows": len(frame), "permutations": settings["permutations"], "artifacts": artifacts,
        "scope": "Segregación de participación en fuentes observadas. No mide afecto, ideología, visualización ni población peruana.",
        "null_assumptions": "Reasignación de fuentes por comentario/mes; adicionalmente intercambiabilidad de etiquetas entre canales en la red fija."})
    report = ["#### Participación entre fuentes (targeted-v1)", "", f"Actualizado: {stamp()}; corpus verificado: {len(frame):,} comentarios; SHA-256 `{sha256(source)}`.",
              f"Artefactos: `{output.relative_to(settings['_root'])}`. No requiere ni sustituye la validación del modelo afectivo.", "",
              "| modelo nulo | estadístico | observado | media nula | p Holm |", "|---|---|---:|---:|---:|"]
    for filename, label in (("participation_null.csv", "comentario/mes"), ("participation_channel_label_null.csv", "red fija/canales")):
        for row in pd.read_csv(output / filename).to_dict("records"):
            report.append(f"| {label} | {row['metric']} | {row['observed']:.4f} | {row['null_mean']:.4f} | {row['p_holm']:.4f} |")
    report += ["", f"Usuarios con al menos 5 comentarios bajo fuentes políticas: {len(eligible):,}.",
               "El primer nulo conserva actividad individual y volumen de fuente/mes, pero rompe agrupación por video; el segundo conserva toda la red de participación y permuta etiquetas de canales.",
               "Estas pruebas evalúan segregación de participación condicional al corpus; no identificación partidaria ni polarización afectiva. La clasificación de fuentes y la selección del corpus limitan la generalización.",
               "La comparación con Martínez-España et al. es de alcance metodológico: no existe equivalencia numérica entre participación y AP/spread."]
    update_study_section(agents, "#### Participación entre fuentes (targeted-v1)", "\n".join(report))
    return output
