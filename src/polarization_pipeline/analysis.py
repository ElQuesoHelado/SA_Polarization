from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[2] / "data" / ".matplotlib-cache"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SENTIMENTS = ["negative", "neutral", "positive"]
COLORS = {"negative": "#d62728", "neutral": "#7f7f7f", "positive": "#2ca02c"}


def _require(frame: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in frame]
    if missing:
        raise ValueError(f"El archivo de inferencia no contiene columnas requeridas: {', '.join(missing)}")


def _save(fig, destination: Path) -> None:
    fig.tight_layout()
    fig.savefig(destination, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _sentiment_summary(frame: pd.DataFrame, output: Path) -> None:
    counts = frame.groupby(["party", "sentimiento"]).size().unstack(fill_value=0).reindex(columns=SENTIMENTS, fill_value=0)
    totals = counts.sum(axis=1).replace(0, np.nan)
    net = pd.DataFrame({
        "negative": counts["negative"], "neutral": counts["neutral"],
        "positive": counts["positive"], "total": counts.sum(axis=1),
        "favorabilidad_neta": (counts["positive"] - counts["negative"]) / totals,
        "%_positivo": counts["positive"] / totals * 100,
        "%_negativo": counts["negative"] / totals * 100,
        "%_neutro": counts["neutral"] / totals * 100,
    })
    net.to_csv(output / "favorabilidad_por_partido.csv")
    work = frame.copy()
    work["signo"] = work["sentimiento"].map({"positive": 1, "negative": -1, "neutral": 0})
    work["aporte"] = work["signo"] * work["confianza"]
    weighted = work.groupby("party").agg(
        favorabilidad_ponderada=("aporte", "sum"), n_comentarios=("aporte", "count"),
        confianza_media=("confianza", "mean"),
    )
    weighted["favorabilidad_ponderada_norm"] = weighted["favorabilidad_ponderada"] / weighted["n_comentarios"].replace(0, np.nan)
    weighted.sort_values("favorabilidad_ponderada_norm", ascending=False).to_csv(output / "favorabilidad_ponderada_por_partido.csv")

    pct = counts.div(totals, axis=0).fillna(0) * 100
    fig, ax = plt.subplots(figsize=(8, 5))
    pct.plot(kind="barh", stacked=True, ax=ax, color=[COLORS[x] for x in SENTIMENTS])
    ax.set_xlabel("% de comentarios")
    ax.set_ylabel("Partido / tag")
    ax.legend(title="Sentimiento", bbox_to_anchor=(1.02, 1), loc="upper left")
    _save(fig, output / "plot_distribucion_sentimiento.png")

    ordered = net["favorabilidad_neta"].sort_values()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(ordered.index, ordered.values, color=["#d62728" if value < 0 else "#2ca02c" for value in ordered.values])
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Favorabilidad neta (-1 a +1)")
    for i, value in enumerate(ordered.values):
        ax.text(value, i, f" {value:.3f}", va="center", ha="left" if value >= 0 else "right")
    _save(fig, output / "plot_favorabilidad_neta.png")

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.hist(frame["confianza"].dropna(), bins=30, color="#4c72b0", edgecolor="white")
    if frame["confianza"].notna().any():
        ax.axvline(frame["confianza"].mean(), color="red", linestyle="--", label=f"media = {frame['confianza'].mean():.2f}")
        ax.legend()
    ax.set_ylabel("N° de comentarios")
    _save(fig, output / "plot_confianza_general.png")

    fig, ax = plt.subplots(figsize=(7, 5))
    for sentiment in SENTIMENTS:
        ax.hist(frame.loc[frame["sentimiento"] == sentiment, "confianza"].dropna(), bins=30, alpha=0.5, label=sentiment, color=COLORS[sentiment])
    ax.set_ylabel("N° de comentarios")
    ax.legend(title="Sentimiento")
    _save(fig, output / "plot_confianza_por_sentimiento.png")

    uncertain = frame.assign(dudoso=frame["confianza"] < 0.5).groupby("party")["dudoso"].mean().mul(100).sort_values()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(uncertain.index, uncertain.values, color="#dd8452")
    ax.set_xlabel("% comentarios con confianza < 0.5")
    for i, value in enumerate(uncertain.values):
        ax.text(value, i, f" {value:.1f}%", va="center")
    _save(fig, output / "plot_comentarios_dudosos.png")

    fig, ax = plt.subplots(figsize=(9, 6))
    for i, (party, group) in enumerate(frame.groupby("party")):
        counts_by_user = group.groupby("user_id", dropna=False).size().clip(upper=5)
        distribution = counts_by_user.value_counts().reindex([1, 2, 3, 4, 5], fill_value=0)
        ax.plot(distribution.index, distribution.values, marker="o", label=party, color=f"C{i % 10}")
    ax.set_xticks([1, 2, 3, 4, 5], ["1", "2", "3", "4", "5+"])
    ax.set_xlabel("N° de comentarios por usuario")
    ax.set_ylabel("N° de usuarios")
    ax.legend(title="Categoría")
    _save(fig, output / "plot_frecuencia_comentarios.png")

    medians = frame.groupby(["party", "sentimiento"])["likes"].median()
    fig, ax = plt.subplots(figsize=(8, 6))
    for i, party in enumerate(frame["party"].dropna().unique()):
        values = medians.get(party, pd.Series(dtype=float)).reindex(SENTIMENTS)
        ax.plot(SENTIMENTS, values.values, marker="o", linewidth=2, label=party, color=f"C{i % 10}")
    ax.set_xlabel("Tipo de sentimiento")
    ax.set_ylabel("Likes median")
    ax.legend(title="Categoría")
    _save(fig, output / "plot_engagement_vs_indiferencia.png")


def _empty_polarization(output: Path) -> None:
    columns = ["user_id", "ingroup", "AP_In", "AP_Out", "AP", "spread", "n_interacciones", "nivel_AP", "nivel_spread"]
    pd.DataFrame(columns=columns).to_csv(output / "ap_individual.csv", index=False)
    pd.DataFrame(columns=["mean", "std", "count"]).to_csv(output / "polarizacion_por_grupo.csv")
    for xlabel, filename in (("Affective polarization in-group (AP_In)", "plot_ap_in.png"), ("Affective polarization out-group (AP_Out)", "plot_ap_out.png"), ("Affective polarization (AP)", "plot_ap_final.png"), ("Spread", "plot_spread.png")):
        fig, ax = plt.subplots(figsize=(9, 6))
        ax.set_xlabel(xlabel)
        _save(fig, output / filename)


def _polarization(frame: pd.DataFrame, output: Path) -> None:
    work = frame.loc[frame["sentimiento"].isin(["positive", "negative"])].copy()
    if work.empty or work["user_id"].dropna().empty:
        _empty_polarization(output)
        return
    users = work["user_id"].dropna().unique()
    tags = frame["party"].dropna().unique().tolist()
    parties = [tag for tag in tags if tag != "neutral"]
    matrix = work.groupby(["user_id", "party", "sentimiento"]).size().unstack(fill_value=0)
    for sentiment in ("positive", "negative"):
        if sentiment not in matrix:
            matrix[sentiment] = 0
    positive = matrix["positive"].unstack(fill_value=0).reindex(index=users, columns=tags, fill_value=0)
    negative = matrix["negative"].unstack(fill_value=0).reindex(index=users, columns=tags, fill_value=0)
    ingroups = []
    for _, row in positive.reindex(columns=parties, fill_value=0).iterrows():
        maximum = row.max() if len(row) else 0
        leaders = row.index[row == maximum].tolist() if maximum else []
        ingroups.append(leaders[0] if len(leaders) == 1 else "Undetermined")
    ingroup = pd.Series(ingroups, index=positive.index)
    records = []
    for user in positive.index:
        selected = ingroup.loc[user]
        total = positive.loc[user].sum() + negative.loc[user].sum()
        if selected == "Undetermined":
            ap_in = ap_out = ap = spread = np.nan
        else:
            ap_in = positive.loc[user, selected] - negative.loc[user, selected]
            outgroups = [tag for tag in tags if tag != selected]
            ap_out = sum(positive.loc[user, tag] - negative.loc[user, tag] for tag in outgroups)
            ap = ap_in - ap_out
            spread = np.sqrt(sum((positive.loc[user, tag] - negative.loc[user, tag]) ** 2 for tag in tags) / total) if total else np.nan
        records.append({"user_id": user, "ingroup": selected, "AP_In": ap_in, "AP_Out": ap_out, "AP": ap, "spread": spread, "n_interacciones": total})
    result = pd.DataFrame(records)
    ap_mean, ap_std = result["AP"].mean(), result["AP"].std()
    spread_mean, spread_std = result["spread"].mean(), result["spread"].std()
    result["nivel_AP"] = np.select(
        [result["AP"].isna(), result["AP"] < ap_mean - ap_std, result["AP"] > ap_mean + ap_std],
        ["Undetermined", "Bajo", "Alto"], default="Medio",
    )
    result["nivel_spread"] = np.select(
        [result["spread"].isna(), result["spread"] == 0, result["spread"] > spread_mean + spread_std],
        ["Undetermined", "Bajo", "Alto"], default="Medio",
    )
    result.to_csv(output / "ap_individual.csv", index=False)
    result.loc[result["ingroup"] != "Undetermined"].groupby("ingroup")["AP"].agg(["mean", "std", "count"]).to_csv(output / "polarizacion_por_grupo.csv")
    for metric, xlabel, filename in (("AP_In", "Affective polarization in-group (AP_In)", "plot_ap_in.png"), ("AP_Out", "Affective polarization out-group (AP_Out)", "plot_ap_out.png"), ("AP", "Affective polarization (AP)", "plot_ap_final.png"), ("spread", "Spread", "plot_spread.png")):
        valid = result.loc[result["ingroup"] != "Undetermined"]
        groups = sorted(valid["ingroup"].dropna().unique())
        fig, ax = plt.subplots(figsize=(9, 6))
        for i, group in enumerate(groups):
            values = valid.loc[valid["ingroup"] == group, metric].dropna()
            rng = np.random.default_rng(0)
            jitter = rng.uniform(i - 0.15, i + 0.15, size=len(values))
            ax.scatter(values, jitter, alpha=0.4, s=15, color=f"C{i % 10}")
        ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
        ax.set_yticks(range(len(groups)), groups)
        ax.set_xlabel(xlabel)
        _save(fig, output / filename)


def analyze(config: dict[str, Any]) -> None:
    output: Path = config["paths"]["outputs"]
    output.mkdir(parents=True, exist_ok=True)
    source = output / "datos_clasificados.csv"
    if not source.is_file():
        raise FileNotFoundError(f"No existe {source}; ejecuta infer o coloca ahí la salida de Kaggle.")
    frame = pd.read_csv(source)
    _require(frame, ["text", "user_id", "party", "sentimiento", "confianza", "likes"])
    frame.to_csv(output / "datos_clasificados.csv", index=False)
    frame["confianza"] = pd.to_numeric(frame["confianza"], errors="coerce")
    frame["likes"] = pd.to_numeric(frame["likes"], errors="coerce").fillna(0)
    _sentiment_summary(frame, output)
    _polarization(frame, output)
    print(f"Análisis guardado en {output}")
