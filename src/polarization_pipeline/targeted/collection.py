"""Read-only YouTube API acquisition with persistent per-day call accounting."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .common import atomic_json, in_window, read_csv, stages, stamp
from .corpus import build_corpus


class CollectionPaused(RuntimeError):
    def __init__(self, message, *, reason="unspecified"):
        super().__init__(message)
        self.reason = reason


class APIUnavailable(RuntimeError):
    pass


class APIRequestFailed(RuntimeError):
    def __init__(self, message, *, reason):
        super().__init__(message)
        self.reason = reason


class BudgetedAPI:
    def __init__(self, api, ledger: Path, budget: int, *, clock=None):
        if isinstance(budget, bool) or not isinstance(budget, int) or budget < 1:
            raise ValueError("El presupuesto diario debe ser un entero positivo")
        self.api, self.ledger, self.budget = api, ledger, budget
        self.pt_ledger = ledger.with_name(ledger.stem + "_pt" + ledger.suffix)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _validate_counts(counts):
        if not isinstance(counts, dict):
            raise ValueError("Contador de cuota inválido")
        for day, count in counts.items():
            if (not isinstance(day, str) or datetime.strptime(day, "%Y-%m-%d").strftime("%Y-%m-%d") != day
                    or isinstance(count, bool) or not isinstance(count, int) or count < 0):
                raise ValueError("Contador de cuota inválido")

    def _usage(self, now):
        local = now.astimezone(ZoneInfo("America/Los_Angeles"))
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        utc = json.loads(self.ledger.read_text()) if self.ledger.exists() else {}
        self._validate_counts(utc)
        if self.pt_ledger.exists():
            usage = json.loads(self.pt_ledger.read_text())
            if usage.get("schema_version") != 1 or usage.get("timezone") != "America/Los_Angeles":
                raise ValueError("Formato de cuota del Pacífico incompatible")
            self._validate_counts(usage["days"])
        else:
            # Old counters have only UTC dates. Charge all overlapping dates to
            # the first PT period, conservatively, without deleting old usage.
            first = start.astimezone(timezone.utc).date()
            last = (end.astimezone(timezone.utc) - timedelta(microseconds=1)).date()
            dates = [(first + timedelta(days=i)).isoformat() for i in range((last-first).days+1)]
            usage = dict(schema_version=1, timezone="America/Los_Angeles",
                days={local.date().isoformat(): sum(utc.get(day, 0) for day in dates)},
                migration=dict(at=now.isoformat(), overlapping_utc_days=dates, conservative=True))
        return utc, usage, local.date().isoformat(), end.astimezone(timezone.utc).isoformat()

    def budget_status(self):
        import fcntl
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger.with_suffix(".lock").open("a") as budget_lock:
            fcntl.flock(budget_lock, fcntl.LOCK_EX)
            _, usage, day, reset = self._usage(self.clock())
            consumed = usage["days"].get(day, 0)
            return dict(timezone="America/Los_Angeles", quota_day=day, effective_daily_budget=self.budget,
                locally_accounted_requests=consumed, local_remaining=max(0, self.budget-consumed),
                next_reset_utc=reset, official_google_balance_verified=False,
                migration_persisted=self.pt_ledger.exists())

    def call(self, resource: str, **params) -> dict:
        for attempt in range(4):
            # All official collectors share one ledger. Lock each reservation so
            # concurrent processes cannot overwrite increments or exceed budget.
            import fcntl
            self.ledger.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger.with_suffix(".lock").open("a") as budget_lock:
                fcntl.flock(budget_lock, fcntl.LOCK_EX)
                now = self.clock()
                utc, usage, day, _ = self._usage(now)
                if usage["days"].get(day, 0) >= self.budget:
                    raise CollectionPaused("Presupuesto diario del Pacífico alcanzado; avance guardado.", reason="local_budget")
                usage["days"][day] = usage["days"].get(day, 0) + 1
                # PT is authoritative: persist it first. A failed UTC mirror
                # write may overcount a reservation, never release quota.
                atomic_json(self.pt_ledger, usage)
                utc_day = now.astimezone(timezone.utc).date().isoformat()
                utc[utc_day] = utc.get(utc_day, 0) + 1
                atomic_json(self.ledger, utc)
            try:
                return getattr(self.api, resource)().list(**params).execute()
            except Exception as exc:
                # Never log request URLs (googleapiclient URLs can contain the API key).
                status = getattr(getattr(exc, "resp", None), "status", None)
                content = getattr(exc, "content", b"")
                if isinstance(content, str):
                    content = content.encode()
                if b"quotaExceeded" in content or b"dailyLimitExceeded" in content:
                    raise CollectionPaused("YouTube agotó la cuota; reanuda conservando los archivos.", reason="youtube_quota") from None
                import httplib2
                transport_error = isinstance(exc, (OSError, TimeoutError, httplib2.HttpLib2Error))
                if (status in (429, 500, 502, 503, 504) or (status is None and transport_error)) and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                if b"commentsDisabled" in content or status == 404:
                    raise APIUnavailable("recurso_no_disponible") from None
                raise APIRequestFailed(f"Fallo de YouTube ({status or 'transporte'}); no se registró la URL.",
                    reason="transport_error" if status is None else "api_error") from None
        raise RuntimeError("Reintentos agotados")


def api_client(settings: dict, api=None) -> BudgetedAPI:
    if api is None:
        from dotenv import load_dotenv
        from ..youtube import client
        load_dotenv(settings["_root"] / ".env")
        api = client()
        if hasattr(getattr(api, "_http", None), "timeout"):
            api._http.timeout = 30
    return BudgetedAPI(api, settings["workspace"] / "api_usage.json", settings["daily_api_budget"])


def refresh_metadata(settings: dict, run: Path, api: BudgetedAPI) -> None:
    frame = read_csv(run / "video_frame.csv")
    destination = run / "video_metadata.csv"
    old = read_csv(destination).to_dict("records") if destination.exists() else []
    done = {row["post_id"] for row in old}
    pending = sorted(set(frame.post_id) - done - {""})
    for start in range(0, len(pending), 50):
        ids = pending[start:start + 50]
        response = api.call("videos", part="snippet,statistics", id=",".join(ids), maxResults=50)
        items = {item["id"]: item for item in response.get("items", [])}
        for video_id in ids:
            item = items.get(video_id, {})
            snippet = item.get("snippet", {})
            old.append({
                "post_id": video_id, "channel_id": snippet.get("channelId", ""),
                "video_published_at": snippet.get("publishedAt", ""),
                "video_status": "verified" if item else "unavailable", "metadata_fetched_at": stamp(),
                "api_comment_count": item.get("statistics", {}).get("commentCount", ""),
            })
        pd.DataFrame(old).to_csv(destination, index=False)
    build_corpus(settings, run)


def select_panel(settings: dict, frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    handles = {handle for group in settings["source"]["youtube"]["channels"].values() for handle in group}
    periods = settings["source"]["youtube"]["periods"]
    frame = frame.loc[frame.channel_handle.isin(handles) & in_window(frame.video_published_at, periods)]
    frame["video_month"] = pd.to_datetime(frame.video_published_at, utc=True).dt.strftime("%Y-%m")
    selected = []
    for _, group in frame.sort_values("post_id").groupby(["channel_handle", "video_month"], sort=True):
        take = min(len(group), settings["panel_videos_per_channel_month"])
        sample = group.sample(n=take, random_state=settings["seed"]).copy()
        sample["video_inclusion_probability"] = take / len(group)
        sample["video_frame_size"] = len(group)
        selected.append(sample)
    if not selected:
        raise ValueError("No hay videos verificados de los canales configurados para el panel")
    return pd.concat(selected, ignore_index=True).sample(frac=1, random_state=settings["seed"]).reset_index(drop=True)


def comment_record(item: dict, parent_id: str = "") -> dict:
    snippet = item["snippet"]
    return {
        "comment_id": item["id"], "text": snippet.get("textOriginal", snippet.get("textDisplay", "")),
        "user_id": snippet.get("authorChannelId", {}).get("value", ""),
        "comment_published_at": snippet.get("publishedAt", ""),
        "updated_at": snippet.get("updatedAt", ""), "likes": snippet.get("likeCount", 0),
        "parent_id": parent_id or snippet.get("parentId", ""),
        "comment_type": "reply" if parent_id or snippet.get("parentId") else "top_level",
    }


def collect_video(api: BudgetedAPI, video: dict, destination: Path, periods: dict) -> dict:
    state = json.loads(destination.read_text()) if destination.exists() else {
        "schema_version": 3, "video": video, "threads_done": False, "thread_page_token": "",
        "comments": {}, "reply_tasks": {}, "started_at": stamp(), "status": "incomplete",
    }
    if state["status"] in ("complete", "unavailable"):
        return state
    start = min(pd.Timestamp(p[0]) for p in periods.values())
    try:
        while not state["threads_done"]:
            params = dict(part="snippet,replies", videoId=video["post_id"], maxResults=100, order="time", textFormat="plainText")
            if state["thread_page_token"]:
                params["pageToken"] = state["thread_page_token"]
            response = api.call("commentThreads", **params)
            reached_start = False
            for thread in response.get("items", []):
                root = comment_record(thread["snippet"]["topLevelComment"])
                date = pd.to_datetime(root["comment_published_at"], utc=True, errors="coerce")
                if pd.isna(date):
                    raise ValueError("YouTube devolvió un comentario sin fecha válida")
                if date < start:
                    reached_start = True
                if not bool(in_window(pd.Series([root["comment_published_at"]]), periods).iloc[0]):
                    continue
                root_id = root["comment_id"]
                root["reply_count_at_collection"] = thread["snippet"].get("totalReplyCount", 0)
                state["comments"][root_id] = root
                embedded = thread.get("replies", {}).get("comments", [])
                for item in embedded:
                    child = comment_record(item, root_id)
                    state["comments"][child["comment_id"]] = child
                # Embedded replies are complete only when their count matches totalReplyCount.
                state["reply_tasks"].setdefault(root_id, {
                    "done": len(embedded) >= root["reply_count_at_collection"], "page_token": "",
                })
            state["thread_page_token"] = response.get("nextPageToken", "")
            state["threads_done"] = not state["thread_page_token"] or reached_start
            atomic_json(destination, state)
        for root_id, task in state["reply_tasks"].items():
            while not task["done"]:
                params = dict(part="snippet", parentId=root_id, maxResults=100, textFormat="plainText")
                if task["page_token"]:
                    params["pageToken"] = task["page_token"]
                try:
                    response = api.call("comments", **params)
                except APIUnavailable:
                    task["done"] = True
                    task["unavailable"] = True
                    atomic_json(destination, state)
                    break
                for item in response.get("items", []):
                    child = comment_record(item, root_id)
                    state["comments"][child["comment_id"]] = child
                task["page_token"] = response.get("nextPageToken", "")
                task["done"] = not task["page_token"]
                atomic_json(destination, state)
        state["status"] = "complete"
        state["finished_at"] = stamp()
    except APIUnavailable:
        state["status"] = "unavailable"
    finally:
        atomic_json(destination, state)
    return state


def normalize_panel(settings: dict, run: Path) -> pd.DataFrame:
    rows = []
    periods = settings["source"]["youtube"]["periods"]
    for path in sorted((run / "raw_panel").glob("*.json")):
        state = json.loads(path.read_text())
        if state["status"] != "complete":
            continue  # Never use an interrupted video as though it were completely captured.
        video = state["video"]
        for comment in state["comments"].values():
            parent = state["comments"].get(comment["parent_id"], {})
            row = {**video, **comment, "parent_text": parent.get("text", ""),
                   "post_title": video.get("post_title", ""), "corpus": "audit_panel", "provenance": "youtube_api_v3"}
            if bool(in_window(pd.Series([comment["comment_published_at"]]), periods).iloc[0]):
                rows.append(row)
    columns = ["comment_id", "text", "user_id", "parent_id", "comment_type", "comment_published_at", "parent_text", "post_id", "post_title", "channel_id", "channel_handle", "channel", "party", "video_published_at", "corpus", "provenance"]
    frame = pd.DataFrame(rows) if rows else pd.DataFrame(columns=columns)
    frame["comment_stage"] = stages(frame.comment_published_at, periods)
    frame.to_csv(run / "corpus_panel.csv", index=False)
    return frame


def collect_context(settings: dict, run: Path, *, metadata_only: bool = False, api=None) -> None:
    client = api_client(settings, api)
    try:
        refresh_metadata(settings, run, client)
        if metadata_only:
            return
        panel_path = run / "panel.csv"
        if not panel_path.exists():
            panel = select_panel(settings, read_csv(run / "video_frame.csv"))
            titles = read_csv(run / "corpus_audited.csv", usecols=["post_id", "post_title"]).drop_duplicates("post_id")
            panel = panel.merge(titles, on="post_id", validate="one_to_one")
            panel.to_csv(panel_path, index=False)
        panel = read_csv(panel_path)
        destination = run / "raw_panel"
        destination.mkdir(exist_ok=True)
        for i, video in enumerate(panel.to_dict("records"), 1):
            collect_video(client, video, destination / f"{video['post_id']}.json", settings["source"]["youtube"]["periods"])
            print(f"Panel: {i}/{len(panel)} videos guardados", flush=True)
    finally:
        normalize_panel(settings, run)
