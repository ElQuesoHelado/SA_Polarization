from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


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
            # A video with disabled comments should not abort the other channels.
            error_body = getattr(exc, "content", b"")
            if isinstance(error_body, bytes) and b"commentsDisabled" in error_body:
                print(f"  [AVISO] Comentarios no disponibles para {video_id}: {exc}")
                return result
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


def collect(config: dict[str, Any]) -> None:
    api = client()
    settings = config["youtube"]
    raw_dir: Path = config["paths"]["raw"]
    raw_dir.mkdir(parents=True, exist_ok=True)
    periods = settings["periods"]
    start = min(bounds[0] for bounds in periods.values())
    end = max(bounds[1] for bounds in periods.values())

    for pool, channels in settings["channels"].items():
        result = {
            "pool": pool,
            "fecha_extraccion": datetime.now(timezone.utc).isoformat(),
            "canales": channels,
            "videos": [],
        }
        for channel in channels:
            print(f"[{pool}] {channel}")
            try:
                found = channel_videos(api, channel, start, end, settings.get("max_videos_per_channel"))
            except ValueError as exc:
                print(f"  [AVISO] {exc}; se omite el canal")
                continue
            for video in found:
                video["etapa"] = stage_for(video["publicado"], periods)
                video_comments = comments(api, video["video_id"], settings.get("max_comments_per_video", 10000))
                video["cantidad_comentarios"] = len(video_comments)
                video["comentarios"] = video_comments
                result["videos"].append(video)
                print(f"  {video['titulo']}: {len(video_comments)} comentarios")
        path = raw_dir / f"{pool}.json"
        import json
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Guardado: {path}")
