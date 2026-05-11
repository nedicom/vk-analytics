from __future__ import annotations
import json
import os
import requests
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
                "post_id": post["id"],
                "owner_id": v.get("owner_id", f"-{group_id}"),
                "title": v.get("description") or v.get("title", ""),
                "views": v.get("views", 0),
                "likes": post.get("likes", {}).get("count", 0),
                "comments": post.get("comments", {}).get("count", 0),
                "reposts": post.get("reposts", {}).get("count", 0),
                "duration": v.get("duration", 0),
                "date": datetime.fromtimestamp(post["date"]).strftime("%d.%m.%Y") if post.get("date") else "",
                "post_date_ts": post.get("date", 0),
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


_ADS_TOKEN_FILE = os.path.join(os.path.dirname(__file__), "ads_token_cache.json")


def _load_token_file() -> dict:
    try:
        with open(_ADS_TOKEN_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_token_file(data: dict):
    try:
        with open(_ADS_TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def _delete_ads_tokens(client_id: str, client_secret: str, user_id: str = ""):
    data = {"client_id": client_id, "client_secret": client_secret}
    if user_id:
        data["user_id"] = user_id
    requests.post("https://target.my.com/api/v2/oauth2/token/delete.json", data=data)


def _fetch_new_ads_token(client_id: str, client_secret: str) -> dict:
    resp = requests.post("https://target.my.com/api/v2/oauth2/token.json", data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    })
    return resp.json()


def get_ads_token(client_id: str, client_secret: str) -> str:
    import time
    now = time.time()

    cache = _load_token_file()
    cached = cache.get(client_id)

    # Если токен действителен — вернуть
    if cached and cached.get("expires_at", 0) > now + 60:
        return cached["token"]

    # Если есть refresh_token — обновить через него
    if cached and cached.get("refresh_token"):
        resp = requests.post("https://target.my.com/api/v2/oauth2/token.json", data={
            "grant_type": "refresh_token",
            "refresh_token": cached["refresh_token"],
            "client_id": client_id,
            "client_secret": client_secret,
        })
        data = resp.json()
        if data.get("access_token"):
            entry = {
                "token": data["access_token"],
                "refresh_token": data.get("refresh_token", cached["refresh_token"]),
                "expires_at": now + int(data.get("expires_in", 86400)),
            }
            cache[client_id] = entry
            _save_token_file(cache)
            return entry["token"]

    # Запросить новый токен через client_credentials
    data = _fetch_new_ads_token(client_id, client_secret)

    # При превышении лимита — удалить все токены и повторить
    if data.get("error") == "token_limit_exceeded":
        user_id = str(data.get("user_id", ""))
        _delete_ads_tokens(client_id, client_secret, user_id)
        data = _fetch_new_ads_token(client_id, client_secret)

    token = data.get("access_token", "")
    if token:
        cache[client_id] = {
            "token": token,
            "refresh_token": data.get("refresh_token", ""),
            "expires_at": now + int(data.get("expires_in", 86400)),
        }
        _save_token_file(cache)
    return token


def get_ads_stats(client_id: str, client_secret: str) -> dict:
    token = get_ads_token(client_id, client_secret)
    if not token:
        return {}

    headers = {"Authorization": f"Bearer {token}"}

    campaigns_resp = requests.get("https://target.my.com/api/v2/campaigns.json",
                                   headers=headers, params={"limit": 250})
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


def get_comments_stats(group_id: str, token: str, videos: list[dict]) -> dict:
    """Для каждого видео получает авторов комментариев и дату последнего."""
    result = {}
    for v in videos[:15]:  # ограничим 15 чтобы не перегружать API
        post_id = v.get("post_id")
        if not post_id:
            continue
        resp = requests.get("https://api.vk.com/method/wall.getComments", params={
            "owner_id": f"-{group_id}",
            "post_id": post_id,
            "count": 100,
            "sort": "desc",
            "fields": "first_name,last_name",
            "access_token": token,
            "v": VK_API_VERSION,
        })
        data = resp.json().get("response", {})
        items = data.get("items", [])
        profiles = {p["id"]: f"{p.get('first_name','')} {p.get('last_name','')}".strip()
                    for p in data.get("profiles", [])}
        unique_users = set()
        last_date = None
        for c in items:
            uid = c.get("from_id")
            if uid and uid > 0:
                unique_users.add(profiles.get(uid, f"id{uid}"))
            if not last_date and c.get("date"):
                last_date = datetime.fromtimestamp(c["date"]).strftime("%d.%m.%Y")
        result[str(v["id"])] = {
            "unique_commenters": len(unique_users),
            "last_comment": last_date,
            "sample_names": list(unique_users)[:3],
        }
    return result


def get_ads_stats_per_video(client_id: str, client_secret: str, mappings: dict) -> dict:
    """Возвращает статистику рекламы по video_id на основе ручных маппингов video_id→campaign_id."""
    if not mappings:
        return {}
    token = get_ads_token(client_id, client_secret)
    if not token:
        return {}

    headers = {"Authorization": f"Bearer {token}"}
    date_to = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    # Уникальные id из маппингов — пробуем packages, потом campaigns
    ids = list(set(mappings.values()))
    ids_str = ",".join(str(i) for i in ids)
    stats_resp = requests.get(
        "https://target.my.com/api/v2/statistics/ad_plans/day.json",
        headers=headers,
        params={"id": ids_str, "date_from": date_from, "date_to": date_to},
    )
    stats_data = stats_resp.json()

    # Суммируем статистику по campaign_id
    campaign_stats: dict[int, dict] = {}
    for item in stats_data.get("items", []):
        cid = item.get("id")
        if cid not in campaign_stats:
            campaign_stats[cid] = {"impressions": 0, "clicks": 0, "spent": 0.0}
        for row in item.get("rows", []):
            base = row.get("base", {})
            campaign_stats[cid]["impressions"] += base.get("shows", 0)
            campaign_stats[cid]["clicks"] += base.get("clicks", 0)
            campaign_stats[cid]["spent"] += float(base.get("spent", 0) or 0)

    # Сопоставляем video_id → статистика кампании
    video_stats: dict[str, dict] = {}
    for vid, cid in mappings.items():
        s = campaign_stats.get(cid, {})
        if s:
            video_stats[vid] = {
                "impressions": s["impressions"],
                "clicks": s["clicks"],
                "spent": round(s["spent"], 2),
                "ctr": round(s["clicks"] / s["impressions"] * 100, 2) if s["impressions"] else 0,
            }

    return video_stats


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
