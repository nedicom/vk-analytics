import requests
import os
from datetime import datetime


VK_API_VERSION = "5.199"


def get_videos(group_id: str, token: str, count: int = 50) -> list[dict]:
    resp = requests.get("https://api.vk.com/method/video.get", params={
        "owner_id": f"-{group_id}",
        "count": count,
        "access_token": token,
        "v": VK_API_VERSION,
    })
    data = resp.json()
    if "error" in data:
        raise Exception(data["error"]["error_msg"])

    items = data.get("response", {}).get("items", [])
    result = []
    for v in items:
        likes = v.get("likes", {})
        reposts = v.get("reposts", {})
        result.append({
            "id": v["id"],
            "title": v.get("title", ""),
            "views": v.get("views", 0),
            "likes": likes.get("count", 0) if isinstance(likes, dict) else likes,
            "comments": v.get("comments", 0),
            "reposts": reposts.get("count", 0) if isinstance(reposts, dict) else 0,
            "duration": v.get("duration", 0),
            "date": datetime.fromtimestamp(v["date"]).strftime("%d.%m.%Y") if v.get("date") else "",
            "description": (v.get("description") or "")[:300],
        })
    return result


def get_group_stats(group_id: str, token: str) -> list[dict]:
    resp = requests.get("https://api.vk.com/method/stats.get", params={
        "group_id": group_id,
        "interval": "month",
        "access_token": token,
        "v": VK_API_VERSION,
    })
    data = resp.json()
    if "error" in data:
        return []
    return data.get("response", [])
