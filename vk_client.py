from __future__ import annotations
import requests
import os
from datetime import datetime


VK_API_VERSION = "5.199"


def get_videos(group_id: str, token: str, count: int = 50) -> list[dict]:
    resp = requests.get("https://api.vk.com/method/wall.get", params={
        "owner_id": f"-{group_id}",
        "count": count,
        "filter": "owner",
        "access_token": token,
        "v": VK_API_VERSION,
    })
    data = resp.json()
    if "error" in data:
        raise Exception(data["error"]["error_msg"])

    result = []
    for post in data.get("response", {}).get("items", []):
        for att in post.get("attachments", []):
            if att.get("type") != "video":
                continue
            v = att["video"]
            if v.get("type") != "short_video":
                continue
            result.append({
                "id": v["id"],
                "title": v.get("description") or v.get("title", ""),
                "views": v.get("views", 0),
                "likes": post.get("likes", {}).get("count", 0),
                "comments": post.get("comments", {}).get("count", 0),
                "reposts": post.get("reposts", {}).get("count", 0),
                "duration": v.get("duration", 0),
                "date": datetime.fromtimestamp(post["date"]).strftime("%d.%m.%Y") if post.get("date") else "",
                "description": "",
            })
    return result


def get_group_info(group_id: str, token: str) -> dict:
    resp = requests.get("https://api.vk.com/method/groups.getById", params={
        "group_id": group_id,
        "fields": "members_count,activity,description",
        "access_token": token,
        "v": VK_API_VERSION,
    })
    data = resp.json()
    if "error" in data:
        return {}
    groups = data.get("response", {}).get("groups", [])
    return groups[0] if groups else {}


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
