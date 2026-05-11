from __future__ import annotations
import requests
import os
from datetime import datetime, timedelta


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


def get_ads_token(client_id: str, client_secret: str) -> str:
    resp = requests.post("https://target.my.com/api/v2/oauth2/token.json", data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    })
    data = resp.json()
    return data.get("access_token", "")


def get_ads_stats(client_id: str, client_secret: str) -> dict:
    token = get_ads_token(client_id, client_secret)
    if not token:
        return {}

    headers = {"Authorization": f"Bearer {token}"}

    campaigns_resp = requests.get("https://target.my.com/api/v2/campaigns.json",
                                   headers=headers, params={"_count": 250})
    campaigns_data = campaigns_resp.json()
    campaigns = campaigns_data.get("items", [])
    if not campaigns:
        return {"campaigns": [], "total_impressions": 0, "total_clicks": 0, "total_spent": 0}

    campaign_ids = ",".join(str(c["id"]) for c in campaigns)
    date_to = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    stats_resp = requests.get(
        "https://target.my.com/api/v2/statistics/campaigns/day.json",
        headers=headers,
        params={"id": campaign_ids, "date_from": date_from, "date_to": date_to},
    )
    stats_data = stats_resp.json()
    total_impressions = 0
    total_clicks = 0
    total_spent = 0.0
    for item in stats_data.get("items", []):
        for row in item.get("rows", []):
            base = row.get("base", {})
            total_impressions += base.get("shows", 0)
            total_clicks += base.get("clicks", 0)
            total_spent += float(base.get("spent", 0) or 0)

    return {
        "campaigns": [{"name": c.get("name", ""), "status": c.get("status", "")} for c in campaigns[:5]],
        "total_impressions": total_impressions,
        "total_clicks": total_clicks,
        "total_spent": round(total_spent, 2),
        "ctr": round(total_clicks / total_impressions * 100, 2) if total_impressions else 0,
    }


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
