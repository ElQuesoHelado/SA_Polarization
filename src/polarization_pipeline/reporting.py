from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


START_MARKER = "<!-- BEGIN GENERATED RESULTS COMPARISON -->"
END_MARKER = "<!-- END GENERATED RESULTS COMPARISON -->"
STUDY_HEADINGS = (
    "#### Resultados dirigidos (targeted-v1)",
    "#### Participación entre fuentes (targeted-v1)",
    "#### Estudio de publicación (targeted-publication-v1)",
)

# Table 4 and Tables 5–6 from Martínez-España et al. (2024).
# AP_Out is the sum of the off-diagonal Table 4 means; AP = AP_In - AP_Out.
PAPER_BENCHMARKS = {
    "derecha": {
        "label": "Right (PP)",
        "ap_in": 8.661985,
        "ap_out": -1.222552,
        "ap": 9.884537,
        "spread": 1.874452,
        "spread_high_pct": 15.89,
    },
    "izquierda": {
        "label": "Left (PSOE)",
        "ap_in": 6.812523,
        "ap_out": -1.159633,
        "ap": 7.972156,
        "spread": 1.748230,
        "spread_high_pct": 13.35,
    },
}


def validate_results_section(agents_path: Path) -> None:
    """Fail early if AGENTS.md cannot safely receive generated content."""
    try:
        text = agents_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"No se pudo leer {agents_path}: {exc}") from exc
    if text.count(START_MARKER) != 1 or text.count(END_MARKER) != 1:
        raise ValueError(
            f"{agents_path} debe contener exactamente una pareja de marcadores "
            "GENERATED RESULTS COMPARISON."
        )
    if text.index(START_MARKER) > text.index(END_MARKER):
        raise ValueError(f"Los marcadores de resultados en {agents_path} están invertidos.")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fmt(value: object, digits: int = 3) -> str:
    if pd.isna(value):
        return "—"
    return f"{float(value):.{digits}f}"


def _pct(numerator: int, denominator: int) -> str:
    return _fmt(100 * numerator / denominator if denominator else np.nan, 2) + "%"


def _render_comparison(output: Path, source: Path) -> str:
    sentiment = pd.read_csv(output / "favorabilidad_por_partido.csv", index_col=0)
    weighted = pd.read_csv(output / "favorabilidad_ponderada_por_partido.csv", index_col=0)
    users = pd.read_csv(output / "ap_individual.csv")

    classified = users.loc[users["ingroup"] != "Undetermined"].copy()
    total_users = len(users)
    undetermined = int((users["ingroup"] == "Undetermined").sum())
    ap_mean = classified["AP"].mean()
    ap_std = classified["AP"].std()
    spread_mean = classified["spread"].mean()
    spread_std = classified["spread"].std()
    spread_high_cut = spread_mean + spread_std

    summary_rows: list[str] = []
    for group in ("derecha", "izquierda", "neutral"):
        if group not in sentiment.index:
            continue
        s = sentiment.loc[group]
        w = weighted.loc[group] if group in weighted.index else pd.Series(dtype=float)
        summary_rows.append(
            f"| {group} | {int(s['total']):,} | {_fmt(s['%_negativo'], 2)}% | "
            f"{_fmt(s['%_neutro'], 2)}% | {_fmt(s['%_positivo'], 2)}% | "
            f"{_fmt(s['favorabilidad_neta'], 3)} | {_fmt(w.get('favorabilidad_ponderada_norm', np.nan), 3)} |"
        )

    group_rows: list[str] = []
    comparison_rows: list[str] = []
    for group in ("derecha", "izquierda"):
        subset = classified.loc[classified["ingroup"] == group]
        if subset.empty:
            continue
        spread_high = int((subset["nivel_spread"] == "Alto").sum())
        n_group = len(subset)
        metrics = {
            "AP_In": subset["AP_In"].mean(),
            "AP_Out": subset["AP_Out"].mean(),
            "AP_Out_politico": subset["AP_Out_politico"].mean(),
            "balance_neutral": subset["balance_neutral"].mean(),
            "AP_sin_neutral": subset["AP_sin_neutral"].mean(),
            "AP": subset["AP"].mean(),
            "spread": subset["spread"].mean(),
        }
        group_rows.append(
            f"| {group} | {n_group:,} | {_fmt(metrics['AP_In'])} | {_fmt(metrics['AP_Out_politico'])} | "
            f"{_fmt(metrics['balance_neutral'])} | {_fmt(metrics['AP_Out'])} | "
            f"{_fmt(metrics['AP_sin_neutral'])} | "
            f"{_fmt(metrics['AP'])} | {_fmt(metrics['spread'])} | {_pct(spread_high, n_group)} |"
        )
        paper = PAPER_BENCHMARKS[group]
        comparison_rows.append(
            f"| {paper['label']} ↔ {group} | {_fmt(paper['ap_in'])} / {_fmt(metrics['AP_In'])} | "
            f"{_fmt(paper['ap_out'])} / {_fmt(metrics['AP_Out'])} | "
            f"{_fmt(paper['ap'])} / {_fmt(metrics['AP'])} | "
            f"{_fmt(paper['spread'])} / {_fmt(metrics['spread'])} | "
            f"{paper['spread_high_pct']:.2f}% / {_pct(spread_high, n_group)} |"
        )

    updated = datetime.now(ZoneInfo("America/Lima")).isoformat(timespec="minutes")
    return "\n".join(
        [
            f"**Actualizado:** {updated} (America/Lima).",
            f"**Entrada analizada:** `{source.name}`, {len(pd.read_csv(source, usecols=[0])):,} filas; "
            f"SHA-256 `{_sha256(source)}`.",
            "",
            "#### Sentimiento y favorabilidad por grupo",
            "",
            "| party | comentarios | % negativo | % neutro | % positivo | favorabilidad neta | favorabilidad ponderada normalizada |",
            "|---|---:|---:|---:|---:|---:|---:|",
            *summary_rows,
            "",
            "#### Polarización por endogrupo asignado",
            "",
            f"Usuarios con identificador: {total_users:,}; `Undetermined`: {undetermined:,} "
            f"({_pct(undetermined, total_users)}). AP global entre grupos determinados: {_fmt(ap_mean)} "
            f"(DE {_fmt(ap_std)}); spread global entre usuarios determinados: {_fmt(spread_mean)} "
            f"(DE {_fmt(spread_std)}; nivel alto > {_fmt(spread_high_cut)}). Spread usa ahora todos los comentarios "
            "del usuario en el denominador, incluidos los clasificados como sentimiento neutral.",
            "",
            "| ingroup | usuarios determinados | AP_In medio | balance bloque opuesto | balance fuentes neutrales | AP_Out compuesto | AP sin neutral | AP medio | spread medio | spread alto |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            *group_rows,
            "",
            "#### Comparación descriptiva con el paper",
            "",
            "Valores por par `paper / pipeline`. Derecha/Right e izquierda/Left son correspondencias aproximadas, "
            "no grupos equivalentes. La comparación es descriptiva: plataformas, interacciones, grupos y constructos "
            "difieren, así que no constituye una réplica ni una prueba de diferencias.",
            "",
            "| grupo aproximado | AP_In | AP_Out | AP | spread | spread alto |",
            "|---|---:|---:|---:|---:|---:|",
            *comparison_rows,
        ]
    )


def update_results_section(agents_path: Path, output: Path, source: Path) -> None:
    validate_results_section(agents_path)
    original = agents_path.read_text(encoding="utf-8")
    start = original.index(START_MARKER) + len(START_MARKER)
    end = original.index(END_MARKER)
    generated = _render_comparison(output, source)
    # Preserve independently dated studies when refreshing the legacy baseline.
    _, studies = split_study_sections(original[start:end])
    for heading in STUDY_HEADINGS:
        if heading in studies:
            generated += "\n\n" + studies[heading]
    replacement = original[:start] + "\n" + generated + "\n" + original[end:]

    temporary_path: Path | None = None
    try:
        fd, temporary_name = tempfile.mkstemp(prefix=f".{agents_path.name}.", suffix=".tmp", dir=agents_path.parent)
        temporary_path = Path(temporary_name)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(replacement)
        os.chmod(temporary_path, stat.S_IMODE(agents_path.stat().st_mode))
        os.replace(temporary_path, agents_path)
    except OSError as exc:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
        raise RuntimeError(f"No se pudo actualizar la comparación en {agents_path}: {exc}") from exc


def split_study_sections(section: str) -> tuple[str, dict[str, str]]:
    positions = []
    for heading in STUDY_HEADINGS:
        if section.count(heading) > 1:
            raise ValueError(f"Sección de estudio duplicada: {heading}")
        position = section.find(heading)
        if position >= 0:
            positions.append((position, heading))
    positions.sort()
    baseline = section[:positions[0][0]].strip() if positions else section.strip()
    studies = {}
    for index, (position, heading) in enumerate(positions):
        end = positions[index + 1][0] if index + 1 < len(positions) else len(section)
        studies[heading] = section[position:end].strip()
    return baseline, studies


def update_study_section(agents_path: Path, heading: str, content: str) -> None:
    """Atomically update one validated study slot without erasing the others."""
    if heading not in STUDY_HEADINGS or not content.strip().startswith(heading):
        raise ValueError("Cabecera de estudio inválida")
    validate_results_section(agents_path)
    original = agents_path.read_text(encoding="utf-8")
    start = original.index(START_MARKER) + len(START_MARKER)
    end = original.index(END_MARKER)
    baseline, studies = split_study_sections(original[start:end])
    studies[heading] = content.strip()
    generated = baseline + "\n\n" + "\n\n".join(studies[key] for key in STUDY_HEADINGS if key in studies)
    replacement = original[:start] + "\n" + generated + "\n" + original[end:]
    temporary = None
    try:
        fd, name = tempfile.mkstemp(prefix=f".{agents_path.name}.", suffix=".tmp", dir=agents_path.parent)
        temporary = Path(name)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(replacement)
        os.chmod(temporary, stat.S_IMODE(agents_path.stat().st_mode))
        os.replace(temporary, agents_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
