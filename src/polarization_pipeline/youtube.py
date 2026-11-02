from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class QuotaExceeded(RuntimeError):
    """The YouTube API quota ran out; `partial` holds the comments gathered so far."""

    def __init__(self, message: str, partial: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.partial = partial or []


def _is_quota_error(exc: HttpError) -> bool:
    error_body = getattr(exc, "content", b"")
    if isinstance(error_body, bytes):
        return b"quotaExceeded" in error_body or b"dailyLimitExceeded" in error_body
    return False


def client():
    from .config import require_env

    return build("youtube", "v3", developerKey=require_env("YOUTUBE_API_KEY"))


def resolve_channel_id(api, channel: str) -> str:
    channel = channel.strip()
    if channel.startswith("UC"):
        return channel
    if channel.startswith("@"):
        items = api.channels().list(part="id", forHandle=channel).execute().get("items", [])
        if items:
            return items[0]["id"]
    items = api.channels().list(part="id", forUsername=channel.lstrip("@")).execute().get("items", [])
    if items:
        return items[0]["id"]
    raise ValueError(f"No se pudo resolver el canal: {channel}")


def channel_videos(api, channel: str, start: str, end: str, limit: int | None) -> list[dict[str, Any]]:
    channel_id = resolve_channel_id(api, channel)
    details = api.channels().list(part="contentDetails", id=channel_id).execute().get("items", [])
    if not details:
        raise ValueError(f"Canal no encontrado: {channel_id}")
    uploads_id = details[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    videos, token = [], None
    while True:
        page = api.playlistItems().list(
            part="snippet", playlistId=uploads_id, maxResults=50, pageToken=token
        ).execute()
        for item in page.get("items", []):
            snippet = item["snippet"]
            published = snippet["publishedAt"]
            if published < start:
                return videos
            if start <= published <= end:
                videos.append({
                    "video_id": snippet["resourceId"]["videoId"],
                    "titulo": snippet["title"],
                    "canal": snippet["channelTitle"],
                    "canal_id": channel_id,
                    "publicado": published,
                })
                if limit and len(videos) >= limit:
                    return videos
        token = page.get("nextPageToken")
        if not token:
            break
    return videos


def comments(api, video_id: str, limit: int) -> list[dict[str, Any]]:
    result, token = [], None
    while len(result) < limit:
        try:
            page = api.commentThreads().list(
                part="snippet", videoId=video_id,
                maxResults=min(100, limit - len(result)), pageToken=token,
                textFormat="plainText",
            ).execute()
        except HttpError as exc:
            error_body = getattr(exc, "content", b"")
            if isinstance(error_body, bytes) and b"commentsDisabled" in error_body:
                # A video with disabled comments should not abort the other channels.
                print(f"  [AVISO] Comentarios no disponibles para {video_id}: {exc}")
                return result
            if _is_quota_error(exc):
                raise QuotaExceeded(f"Cuota de la API agotada al leer {video_id}: {exc}", partial=result) from exc
            raise
        for item in page.get("items", []):
            top = item["snippet"]["topLevelComment"]
            snippet = top["snippet"]
            result.append({
                "comment_id": top["id"],
                "autor": snippet.get("authorDisplayName"),
                "autor_canal_id": snippet.get("authorChannelId", {}).get("value"),
                "texto": snippet.get("textOriginal", snippet.get("textDisplay", "")),
                "likes": snippet.get("likeCount", 0),
                "fecha_publicacion": snippet.get("publishedAt"),
                "fecha_actualizacion": snippet.get("updatedAt"),
                "cantidad_respuestas": item["snippet"].get("totalReplyCount", 0),
            })
        token = page.get("nextPageToken")
        if not token:
            break
    return result


def stage_for(published: str, periods: dict[str, list[str]]) -> str | None:
    for stage, (start, end) in periods.items():
        if start <= published <= end:
            return stage
    return None


def _write_pool(path: Path, result: dict[str, Any]) -> None:
    import json
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _new_pool(pool: str, channels: list[str]) -> dict[str, Any]:
    return {
        "pool": pool,
        "fecha_extraccion": datetime.now(timezone.utc).isoformat(),
        "canales": channels,
        "canales_procesados": [],
        "videos": [],
    }


def _resume_pool(path: Path, pool: str, channels: list[str]) -> dict[str, Any] | None:
    """Reuse a pool file written by this same incremental format.

    Only channels listed in `canales_procesados` are kept: a channel interrupted by a
    quota error is collected again from scratch on the next run, so its videos cannot
    duplicate. Legacy files without that key are ignored and rewritten as before.
    """
    import json
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("canales_procesados"), list):
        return None
    processed = [channel for channel in payload["canales_procesados"] if channel in channels]
    done = set(processed)
    videos = [
        video for video in payload.get("videos", [])
        if isinstance(video, dict) and video.get("canal_handle") in done
    ]
    if not processed:
        return None
    return {
        "pool": pool,
        "fecha_extraccion": payload.get("fecha_extraccion") or datetime.now(timezone.utc).isoformat(),
        "canales": channels,
        "canales_procesados": processed,
        "videos": videos,
    }


def collect(config: dict[str, Any]) -> None:
    settings = config["youtube"]
    raw_dir: Path = config["paths"]["raw"]
    raw_dir.mkdir(parents=True, exist_ok=True)
    periods = settings["periods"]
    start = min(bounds[0] for bounds in periods.values())
    end = max(bounds[1] for bounds in periods.values())
    neutral_name = config.get("kaggle", {}).get("neutral_file", "neutral.json")
    max_comments = settings.get("max_comments_per_video", 2000)

    # Fail fast before building the API client: a pool must never shadow the canonical file.
    for pool in settings["channels"]:
        if f"{pool}.json" == neutral_name:
            raise ValueError(
                f"El pool '{pool}' escribiría sobre {neutral_name} (archivo canónico de Kaggle); usa otro nombre de pool."
            )

    api = client()
    for pool, channels in settings["channels"].items():
        path = raw_dir / f"{pool}.json"

        result = _resume_pool(path, pool, channels)
        if result is not None:
            print(f"[{pool}] Avance previo: {len(result['canales_procesados'])} canales, {len(result['videos'])} videos")
        else:
            result = _new_pool(pool, channels)
        _write_pool(path, result)

        quota_exhausted = False
        for channel in channels:
            if channel in result["canales_procesados"]:
                print(f"[{pool}] {channel} (ya recolectado)")
                continue
            if quota_exhausted:
                break
            print(f"[{pool}] {channel}")
            try:
                found = channel_videos(api, channel, start, end, settings.get("max_videos_per_channel"))
            except HttpError as exc:
                if not _is_quota_error(exc):
                    raise
                print(f"  [AVISO] Cuota de la API agotada al listar videos de {channel}: {exc}")
                quota_exhausted = True
                continue
            except ValueError as exc:
                print(f"  [AVISO] {exc}; se omite el canal")
                result["canales_procesados"].append(channel)
                _write_pool(path, result)
                continue

            for video in found:
                video["etapa"] = stage_for(video["publicado"], periods)
                video["canal_handle"] = channel
                try:
                    video_comments = comments(api, video["video_id"], max_comments)
                except QuotaExceeded as exc:
                    video_comments = exc.partial
                    video["cantidad_comentarios"] = len(video_comments)
                    video["comentarios"] = video_comments
                    result["videos"].append(video)
                    quota_exhausted = True
                    print(f"  [AVISO] {exc}; se guardan {len(video_comments)} comentarios parciales de {video['video_id']}")
                    break
                video["cantidad_comentarios"] = len(video_comments)
                video["comentarios"] = video_comments
                result["videos"].append(video)
                print(f"  {video['titulo']}: {len(video_comments)} comentarios")

            if not quota_exhausted:
                result["canales_procesados"].append(channel)
            # Persist after every channel so a quota error never loses finished work.
            _write_pool(path, result)

        if quota_exhausted:
            print(f"[{pool}] Cuota agotada; avance guardado en {path}. Reejecuta collect cuando se renueve la cuota.")
            break
        print(f"Guardado: {path}")
