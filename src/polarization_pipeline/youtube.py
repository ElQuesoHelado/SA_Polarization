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
        "formato_version": 2,
        "pool": pool,
        "fecha_extraccion": datetime.now(timezone.utc).isoformat(),
        "canales": channels,
        "canales_procesados": [],
        "videos": [],
    }


def _resume_pool(path: Path, pool: str, channels: list[str]) -> dict[str, Any] | None:
    """Load cached videos, preserving completed and interrupted work."""
    import json
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("videos"), list):
        return None
    processed = [channel for channel in payload.get("canales_procesados", []) if channel in channels]
    done = set(processed)
    videos = []
    for cached in payload["videos"]:
        if not isinstance(cached, dict) or not cached.get("video_id"):
            continue
        video = dict(cached)
        # Older files did not store per-video status. A video from a channel that
        # finished successfully is complete; one from an interrupted channel retries.
        video.setdefault("comentarios_completos", video.get("canal_handle") in done)
        video.setdefault("comentarios", [])
        videos.append(video)
    return {
        "formato_version": 2,
        "pool": pool,
        "fecha_extraccion": payload.get("fecha_extraccion") or datetime.now(timezone.utc).isoformat(),
        "canales": channels,
        "canales_procesados": processed,
        "videos": videos,
    }


def _unique_comment_ids(videos: list[dict[str, Any]]) -> set[str]:
    return {
        comment["comment_id"]
        for video in videos
        for comment in video.get("comentarios", [])
        if isinstance(comment, dict) and comment.get("comment_id")
    }


def _cached_comment_ids(path: Path) -> set[str]:
    """Read comment IDs from either a pool JSON or the canonical neutral list."""
    import json

    if not path.is_file():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    videos = payload.get("videos", []) if isinstance(payload, dict) else payload
    if not isinstance(videos, list):
        return set()
    return _unique_comment_ids([v for v in videos if isinstance(v, dict)])


def _cached_pool_count(path: Path) -> int:
    return len(_cached_comment_ids(path))


def _pool_targets(settings: dict[str, Any], raw_dir: Path, neutral_name: str) -> dict[str, int]:
    """Allocate the total target using the current cached comment proportions."""
    target = int(settings.get("target_total_comments", 1_000_000))
    counts = {}
    for pool in settings["channels"]:
        count = _cached_pool_count(raw_dir / f"{pool}.json")
        if pool == "neutral_local":
            count += _cached_pool_count(raw_dir / neutral_name)
        counts[pool] = count
    total = sum(counts.values())
    if total == 0:
        # No local cache: split equally, with any rounding remainder assigned last.
        names = list(counts)
        base, remainder = divmod(target, max(1, len(names)))
        return {name: base + (i < remainder) for i, name in enumerate(names)}
    configured_shares = settings.get("target_group_shares")
    if configured_shares:
        shares = {pool: float(configured_shares.get(pool, 0)) for pool in counts}
        share_total = sum(shares.values())
        if share_total <= 0:
            raise ValueError("youtube.target_group_shares debe sumar un valor mayor que cero")
        targets = {pool: round(target * share / share_total) for pool, share in shares.items()}
    else:
        targets = {pool: round(target * count / total) for pool, count in counts.items()}
    if targets:
        targets[next(reversed(targets))] += target - sum(targets.values())
    return targets


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
    targets = _pool_targets(settings, raw_dir, neutral_name)
    for pool, channels in settings["channels"].items():
        path = raw_dir / f"{pool}.json"

        result = _resume_pool(path, pool, channels)
        if result is not None:
            print(f"[{pool}] Avance previo: {len(result['canales_procesados'])} canales, {len(result['videos'])} videos")
        else:
            result = _new_pool(pool, channels)
        _write_pool(path, result)

        quota_exhausted = False
        pool_target = targets[pool]
        existing_ids = _unique_comment_ids(result["videos"])
        if pool == "neutral_local":
            existing_ids.update(_cached_comment_ids(raw_dir / neutral_name))
        print(f"[{pool}] Meta asignada: {pool_target:,}; comentarios únicos guardados: {len(existing_ids):,}")
        for channel in channels:
            if len(existing_ids) >= pool_target:
                print(f"[{pool}] Meta del grupo alcanzada")
                break
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
                break
            except ValueError as exc:
                print(f"  [AVISO] {exc}; se omite el canal")
                if channel not in result["canales_procesados"]:
                    result["canales_procesados"].append(channel)
                _write_pool(path, result)
                continue

            cached_by_id = {v["video_id"]: v for v in result["videos"] if v.get("canal_handle") == channel}
            channel_complete = True
            for video in found:
                video["etapa"] = stage_for(video["publicado"], periods)
                video["canal_handle"] = channel
                cached = cached_by_id.get(video["video_id"])
                if cached and cached.get("comentarios_completos", False):
                    continue
                try:
                    video_comments = comments(api, video["video_id"], max_comments)
                except QuotaExceeded as exc:
                    video_comments = exc.partial
                    video["cantidad_comentarios"] = len(video_comments)
                    video["comentarios"] = video_comments
                    video["comentarios_completos"] = False
                    if cached:
                        result["videos"].remove(cached)
                    result["videos"].append(video)
                    existing_ids.update(_unique_comment_ids([video]))
                    channel_complete = False
                    quota_exhausted = True
                    print(f"  [AVISO] {exc}; se guardan {len(video_comments)} comentarios parciales de {video['video_id']}")
                    break
                video["cantidad_comentarios"] = len(video_comments)
                video["comentarios"] = video_comments
                video["comentarios_completos"] = True
                if cached:
                    result["videos"].remove(cached)
                result["videos"].append(video)
                existing_ids.update(_unique_comment_ids([video]))
                print(f"  {video['titulo']}: {len(video_comments)} comentarios")
                if len(existing_ids) >= pool_target:
                    break

            if channel_complete and channel not in result["canales_procesados"]:
                result["canales_procesados"].append(channel)
            # Persist after every channel so a quota error never loses finished work.
            _write_pool(path, result)

        if quota_exhausted:
            print(f"[{pool}] Cuota agotada; avance guardado en {path}. Reejecuta collect cuando se renueve la cuota.")
            break
        print(f"Guardado: {path}")
