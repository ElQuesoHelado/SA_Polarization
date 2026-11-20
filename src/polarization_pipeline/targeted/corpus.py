from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .common import atomic_json, fingerprint, in_window, read_csv, require_columns, run_directory, sha256, stages, stamp


def raw_video_index(settings: dict) -> pd.DataFrame:
    """Read legacy v1/v2 pools; raw publication times remain unverified."""
    raw = Path(settings["source"]["paths"]["raw"])
    raw = raw if raw.is_absolute() else settings["_root"] / raw
    rows = []
    for path in sorted(raw.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        documents = payload if isinstance(payload, list) else [payload]
        for document in documents:
            for video in document.get("videos", []):
                video_id = video.get("video_id", video.get("post_id"))
                if video_id:
                    rows.append({
                        "post_id": video_id,
                        "channel_id": video.get("canal_id", ""),
                        "channel_handle": video.get("canal_handle", ""),
                        "raw_video_published_at": video.get("publicado", ""),
                    })
    return pd.DataFrame(rows, columns=["post_id", "channel_id", "channel_handle", "raw_video_published_at"]).drop_duplicates("post_id")


def build_corpus(settings: dict, run: Path) -> dict:
    manifest = json.loads((run / "manifest.json").read_text())
    source = Path(manifest["input_csv"])
    if sha256(source) != manifest["input_sha256"]:
        raise ValueError("La entrada cambió desde la auditoría; crea otra ejecución")
    frame = read_csv(source)
    require_columns(frame, ["text", "comment_id", "post_id", "user_id", "party", "published_at", "channel"])
    before = len(frame)
    # Do not merge empty IDs or silently keep disagreeing duplicate records.
    identified = frame.loc[frame.comment_id.ne("")]
    duplicates = identified[identified.comment_id.duplicated(False)]
    if not duplicates.empty and duplicates.groupby("comment_id")["text"].nunique().gt(1).any():
        raise ValueError("Identificadores duplicados con textos incompatibles")
    frame = frame.loc[~(frame.comment_id.ne("") & frame.comment_id.duplicated())].copy()
    index = raw_video_index(settings)
    frame = frame.merge(index, on="post_id", how="left", validate="many_to_one").fillna("")
    metadata = run / "video_metadata.csv"
    if metadata.exists():
        verified = read_csv(metadata).drop_duplicates("post_id")
        frame = frame.drop(columns=["channel_id"]).merge(verified, on="post_id", how="left", validate="many_to_one").fillna("")
    else:
        frame["video_published_at"] = ""
        frame["video_status"] = "unverified"
    frame["comment_published_at"] = frame["published_at"]
    frame["video_stage_legacy"] = frame.get("stage", "")
    periods = settings["source"]["youtube"]["periods"]
    frame["comment_stage"] = stages(frame.comment_published_at, periods)
    frame["comment_type"] = "top_level"
    frame["parent_id"] = ""
    frame["parent_text"] = ""
    frame["corpus"] = "main"
    frame["provenance"] = "legacy_top_level"
    comment_ok = in_window(frame.comment_published_at, periods)
    video_ok = in_window(frame.video_published_at, periods)
    frame["exclusion_reason"] = ""
    frame.loc[~comment_ok, "exclusion_reason"] = "comment_outside_window"
    frame.loc[comment_ok & ~video_ok, "exclusion_reason"] = "video_outside_window_or_unverified"
    frame.loc[frame.comment_id.eq("") | frame.post_id.eq(""), "exclusion_reason"] = "missing_record_id"
    frame.to_csv(run / "corpus_audited.csv", index=False)
    main = frame.loc[frame.exclusion_reason.eq("")]
    main.to_csv(run / "corpus_main.csv", index=False)
    panel = frame[["post_id", "channel", "channel_id", "channel_handle", "party", "video_published_at"]].drop_duplicates("post_id")
    panel.to_csv(run / "video_frame.csv", index=False)
    summary = {
        "rows_input": before, "rows_deduplicated": len(frame), "rows_main_verified": len(main),
        "comments_in_window": int(comment_ok.sum()), "comments_outside_window": int((~comment_ok).sum()),
        "excluded": frame.exclusion_reason.value_counts().to_dict(),
        "users": int(frame.loc[frame.user_id.ne(""), "user_id"].nunique()),
        "videos": int(frame.post_id.nunique()), "channels": int(frame.channel.nunique()),
        "source_counts": frame.party.value_counts().to_dict(),
        "months": pd.to_datetime(frame.comment_published_at, utc=True, errors="coerce").dt.strftime("%Y-%m").value_counts().sort_index().to_dict(),
        "metadata_complete": frame.video_published_at.ne("").all().item(),
        "metadata_checked_all": bool(metadata.exists() and frame.video_status.isin(["verified", "unavailable"]).all()),
        "video_status_counts": frame[["post_id", "video_status"]].drop_duplicates().video_status.value_counts().to_dict(),
    }
    atomic_json(run / "audit.json", summary)
    manifest["audit_updated_at"] = stamp()
    manifest["corpus_main_sha256"] = sha256(run / "corpus_main.csv")
    atomic_json(run / "manifest.json", manifest)
    return summary


def audit(settings: dict, run_id: str) -> Path:
    source = settings["input_csv"]
    if not source.is_file():
        raise FileNotFoundError(source)
    run = run_directory(settings, run_id, create=True)
    atomic_json(run / "manifest.json", {
        "schema_version": 1, "method_version": settings["method_version"], "created_at": stamp(),
        "input_csv": str(source), "input_sha256": sha256(source), "config_fingerprint": fingerprint(settings),
        "config": json.loads(json.dumps(settings, default=str)),
    })
    print(json.dumps(build_corpus(settings, run), ensure_ascii=False, indent=2))
    return run
