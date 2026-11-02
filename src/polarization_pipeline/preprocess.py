from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pandas as pd


def _documents(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    if isinstance(payload, dict):
        yield payload
    elif isinstance(payload, list):
        yield from (item for item in payload if isinstance(item, dict))
    else:
        raise ValueError(f"Formato JSON no soportado en {path}")


def _comment_rows(doc: dict[str, Any], source: Path, party: str) -> list[dict[str, Any]]:
    rows = []
    videos = doc.get("videos", [])
    if isinstance(videos, list):
        for video in videos:
            if not isinstance(video, dict):
                continue
            for comment in video.get("comentarios", []):
                if not isinstance(comment, dict):
                    continue
                rows.append({
                    "text": comment.get("texto", comment.get("text", "")),
                    "user_id": comment.get("autor_canal_id", comment.get("user_id")),
                    "username": comment.get("autor", comment.get("username")),
                    "likes": comment.get("likes", 0),
                    "comment_id": comment.get("comment_id"),
                    "post_id": video.get("video_id", video.get("post_id")),
                    "post_title": video.get("titulo", video.get("post_title")),
                    "channel": video.get("canal", video.get("channel")),
                    "published_at": comment.get("fecha_publicacion", comment.get("published_at")),
                    "updated_at": comment.get("fecha_actualizacion", comment.get("updated_at")),
                    "reply_count": comment.get("cantidad_respuestas", comment.get("reply_count", 0)),
                    "stage": video.get("etapa", video.get("stage")),
                    "party": party,
                    "source_file": source.name,
                    "search_query": doc.get("query"),
                })
    return rows


def _resolve_party(doc: dict[str, Any], source: Path, mapping: dict[str, str]) -> str:
    # The pool (or the file stem when the pool is absent) is mapped through file_party so
    # auxiliary pools such as `neutral_local` collapse into the canonical party labels.
    pool = doc.get("pool")
    key = pool if isinstance(pool, str) and pool.strip() else source.stem
    return mapping.get(key, key)


def _drop_duplicated_comments(frame: pd.DataFrame) -> pd.DataFrame:
    # The canonical Kaggle neutral.json and a local neutral pool can share videos.
    identified = frame.loc[frame["comment_id"].notna()]
    duplicated = identified.duplicated(subset=["comment_id"], keep="first")
    if not duplicated.any():
        return frame
    keep = frame.index.difference(identified.index[duplicated])
    print(f"Se omitieron {int(duplicated.sum())} comentarios duplicados por comment_id.")
    return frame.loc[keep]


def preprocess(config: dict[str, Any]) -> Path:
    raw_dir: Path = config["paths"]["raw"]
    processed_dir: Path = config["paths"]["processed"]
    processed_dir.mkdir(parents=True, exist_ok=True)
    if not raw_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta de datos raw: {raw_dir}; ejecuta collect o data-pull.")

    mapping = config.get("preprocess", {}).get("file_party", {})
    files = sorted(raw_dir.glob("*.json"))
    rows = []
    for path in files:
        for document in _documents(path):
            rows.extend(_comment_rows(document, path, _resolve_party(document, path, mapping)))
    if not rows:
        raise ValueError(f"No se encontraron comentarios en {raw_dir}")

    result = pd.DataFrame(rows)
    result["text"] = result["text"].fillna("").astype(str)
    result["likes"] = pd.to_numeric(result["likes"], errors="coerce").fillna(0).astype("int64")
    result = _drop_duplicated_comments(result)
    output = processed_dir / config.get("preprocess", {}).get("comments_file", "comentarios_consolidado.csv")
    result.to_csv(output, index=False)
    print(f"{len(result)} comentarios procesados en {output}")
    print(result["party"].value_counts(dropna=False).to_string())
    return output


def require_neutral_rows(path: Path) -> int:
    parties = pd.read_csv(path, usecols=["party"])["party"]
    neutral_count = int(parties.eq("neutral").sum())
    if neutral_count == 0:
        raise ValueError(f"El consolidado {path} no contiene comentarios del grupo neutral.")
    return neutral_count
