import json
import os
import time
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_KEY = os.getenv("YOUTUBE_API_KEY")
CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID")

API_URL = "https://www.googleapis.com/youtube/v3"
WINDOW_SECONDS = 24 * 60 * 60
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "views.json"


def load_data() -> dict:
    if DATA_PATH.exists():
        return json.loads(DATA_PATH.read_text())
    return {"snapshots": []}


def save_data(data: dict) -> None:
    tmp = DATA_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, DATA_PATH)


def api_get(endpoint: str, **params) -> dict:
    resp = requests.get(
        f"{API_URL}/{endpoint}",
        params=params,
        headers={"x-goog-api-key": API_KEY},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"{endpoint} failed: {resp.status_code} {resp.text}")
    return resp.json()


def fetch_channel() -> tuple[int, str]:
    item = api_get("channels", part="contentDetails,statistics", id=CHANNEL_ID)["items"][0]
    return (
        int(item["statistics"]["viewCount"]),
        item["contentDetails"]["relatedPlaylists"]["uploads"],
    )


def fetch_video_ids(uploads_playlist_id: str) -> list[str]:
    ids, token = [], None
    while True:
        data = api_get(
            "playlistItems",
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=50,
            pageToken=token,
        )
        ids += [i["contentDetails"]["videoId"] for i in data["items"]]
        token = data.get("nextPageToken")
        if not token:
            return ids


def fetch_video_views(video_ids: list[str]) -> dict[str, int]:
    views = {}
    for i in range(0, len(video_ids), 50):
        data = api_get("videos", part="statistics", id=",".join(video_ids[i : i + 50]))
        for item in data["items"]:
            views[item["id"]] = int(item["statistics"].get("viewCount", 0))
    return {vid: views[vid] for vid in video_ids if vid in views}


def poll(data: dict) -> dict:
    now = int(time.time())
    channel_views, uploads_id = fetch_channel()
    snapshot = {
        "ts": now,
        "channel_views": channel_views,
        "videos": fetch_video_views(fetch_video_ids(uploads_id)),
    }
    data["snapshots"].append(snapshot)
    save_data(data)
    return snapshot


def report(data: dict, current: dict) -> None:
    print(f"Total channel views: {current['channel_views']:,}")
    earlier = [s for s in data["snapshots"] if s["ts"] < current["ts"]]
    if not earlier:
        print("No earlier data yet; cannot estimate the 24h change.")
        return
    target = current["ts"] - WINDOW_SECONDS
    old = min(earlier, key=lambda s: abs(s["ts"] - target))
    hours = (current["ts"] - old["ts"]) / 3600
    change = current["channel_views"] - old["channel_views"]
    print(f"Estimated change: {change:+,} views (based on data from {hours:.1f}h ago)")


def main() -> None:
    if not API_KEY or not CHANNEL_ID:
        raise SystemExit("Set YOUTUBE_API_KEY and YOUTUBE_CHANNEL_ID")

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = load_data()
    report(data, poll(data))


if __name__ == "__main__":
    main()
