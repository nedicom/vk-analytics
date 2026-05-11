import json
import os
from datetime import datetime
from functools import wraps

import requests as http
from dotenv import load_dotenv, set_key
from flask import Flask, jsonify, redirect, render_template, request, session

from vk_client import get_ads_stats, get_ads_stats_per_video, get_comments_stats, get_group_info, get_group_stats, get_videos

load_dotenv()


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-on-server")

VK_TOKEN = os.getenv("VK_TOKEN")
VK_GROUP_ID = os.getenv("VK_GROUP_ID")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
VK_APP_ID = os.getenv("VK_APP_ID", "54587433")
VK_APP_SECRET = os.getenv("VK_APP_SECRET", "")
VK_REDIRECT_URI = os.getenv("VK_REDIRECT_URI", "https://vk.nedicom.ru/callback")
ADS_CLIENT_ID = os.getenv("ADS_VK_CLIENT_ID", "")
ADS_CLIENT_SECRET = os.getenv("ADS_VK_SECRET", "")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")

HISTORY_FILE = "history.json"
SCRIPTS_FILE = "video_scripts.json"


def load_scripts() -> dict:
    if os.path.exists(SCRIPTS_FILE):
        with open(SCRIPTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_scripts(scripts: dict):
    with open(SCRIPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(scripts, f, ensure_ascii=False, indent=2)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if DASHBOARD_PASSWORD and not session.get("authenticated"):
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

SYSTEM_PROMPT = """Ты опытный аналитик контента ВКонтакте. Помогаешь автору видеоканала принимать решения на основе данных: что снимать, когда публиковать, как увеличить охват и продажи.

Стиль ответа: конкретно, с цифрами из данных, без воды. Сначала коротко — что работает, потом — 3-5 чётких рекомендаций с обоснованием."""


def load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_to_history(analysis: str, video_count: int):
    history = load_history()
    history.append({
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "analysis": analysis,
        "video_count": video_count,
    })
    history = history[-30:]  # хранить последние 30 анализов
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def calc_stats(videos: list) -> dict:
    if not videos:
        return {}
    total_views = sum(v["views"] for v in videos)
    total_likes = sum(v["likes"] for v in videos)
    total_comments = sum(v["comments"] for v in videos)
    total_reposts = sum(v["reposts"] for v in videos)
    best = max(videos, key=lambda v: v["views"])
    return {
        "total_views": total_views,
        "avg_views": total_views // len(videos),
        "total_likes": total_likes,
        "total_comments": total_comments,
        "total_reposts": total_reposts,
        "best_title": best["title"][:50],
        "best_views": best["views"],
        "count": len(videos),
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == DASHBOARD_PASSWORD:
            session["authenticated"] = True
            return redirect("/")
        error = "Неверный пароль"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/")
@login_required
def index():
    try:
        videos = get_videos(VK_GROUP_ID, VK_TOKEN, count=30)
        error = None
    except Exception as e:
        videos = []
        error = str(e)
    group_info = get_group_info(VK_GROUP_ID, VK_TOKEN)
    stats = calc_stats(videos)
    ads = get_ads_stats(ADS_CLIENT_ID, ADS_CLIENT_SECRET) if ADS_CLIENT_ID else {}
    history = load_history()
    scripts = load_scripts()
    comments_stats = get_comments_stats(VK_GROUP_ID, VK_TOKEN, videos)
    ads_per_video = get_ads_stats_per_video(ADS_CLIENT_ID, ADS_CLIENT_SECRET, VK_GROUP_ID) if ADS_CLIENT_ID else {}
    return render_template("index.html", videos=videos, history=history, error=error, group_info=group_info, stats=stats, ads=ads, scripts=scripts, comments_stats=comments_stats, ads_per_video=ads_per_video)


@app.route("/api/scripts", methods=["GET"])
@login_required
def get_scripts():
    return jsonify(load_scripts())


@app.route("/api/script/<video_id>", methods=["POST"])
@login_required
def save_script(video_id):
    text = request.json.get("text", "").strip()
    scripts = load_scripts()
    if text:
        scripts[video_id] = text
    else:
        scripts.pop(video_id, None)
    save_scripts(scripts)
    return jsonify({"ok": True})


@app.route("/api/ads-debug")
@login_required
def ads_debug():
    from vk_client import get_ads_token
    if not ADS_CLIENT_ID or not ADS_CLIENT_SECRET:
        return jsonify({"error": "env not set"})
    token = get_ads_token(ADS_CLIENT_ID, ADS_CLIENT_SECRET)
    if not token:
        return jsonify({"error": "no token after auto-recovery"})
    headers = {"Authorization": f"Bearer {token}"}
    banners_resp = http.get("https://target.my.com/api/v2/banners.json",
                            headers=headers, params={"limit": 1})
    banners_data = banners_resp.json()
    first = banners_data.get("items", [{}])[0]
    ad_group_id = first.get("ad_group_id")
    campaign_id = first.get("campaign_id")
    ad_group, campaign = {}, {}
    if ad_group_id:
        ad_group = http.get(f"https://target.my.com/api/v2/ad_groups/{ad_group_id}.json", headers=headers).json()
    if campaign_id:
        campaign = http.get(f"https://target.my.com/api/v2/campaigns/{campaign_id}.json", headers=headers).json()
    return jsonify({"token_ok": True, "ad_group": ad_group, "campaign": campaign})


@app.route("/api/refresh")
@login_required
def refresh():
    try:
        videos = get_videos(VK_GROUP_ID, VK_TOKEN, count=30)
        return jsonify({"ok": True, "videos": videos})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/analyze", methods=["POST"])
@login_required
def analyze():
    if not ANTHROPIC_API_KEY:
        return jsonify({"ok": False, "error": "API ключ Claude не настроен. Добавьте ANTHROPIC_API_KEY в .env"}), 503

    try:
        videos = get_videos(VK_GROUP_ID, VK_TOKEN, count=30)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    past = load_history()
    past_context = ""
    if past:
        last = past[-1]
        past_context = f"\n\nПрошлый анализ ({last['date']}):\n{last['analysis'][:800]}\n"

    question = (request.json or {}).get("question", "").strip()
    scripts = load_scripts()
    videos_text = "\n".join([
        f"• «{v['title']}» | {v['date']} | 👁 {v['views']} | ❤️ {v['likes']} | 💬 {v['comments']} | ↗️ {v['reposts']} | ⏱ {v['duration']}с"
        + (f"\n  Сценарий: {scripts[str(v['id'])]}" if str(v['id']) in scripts else "")
        for v in videos
    ])

    if question:
        user_message = (
            f"Данные последних {len(videos)} видео группы:{past_context}\n\n{videos_text}\n\n"
            f"Вопрос: {question}"
        )
    else:
        user_message = (
            f"Статистика последних {len(videos)} видео группы:{past_context}\n\n{videos_text}\n\n"
            "Проанализируй результаты с учётом сценариев там где они есть. "
            "Что работает лучше всего? Какие темы и форматы дают больший охват? "
            "Дай конкретные рекомендации для роста просмотров и продаж."
        )

    import anthropic
    import httpx
    _proxy = os.getenv("HTTPS_PROXY")
    _http_client = httpx.Client(proxy=_proxy) if _proxy else None
    claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, http_client=_http_client)
    try:
        response = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as e:
        return jsonify({"ok": False, "error": f"Anthropic API: {e.status_code} — {e.message}"}), 200

    analysis = response.content[0].text
    save_to_history(analysis, len(videos))
    return jsonify({"ok": True, "analysis": analysis})


@app.route("/auth")
def auth():
    url = (
        f"https://oauth.vk.com/authorize"
        f"?client_id={VK_APP_ID}"
        f"&redirect_uri={VK_REDIRECT_URI}"
        f"&scope=video,stats,groups"
        f"&response_type=code"
        f"&v=5.199"
    )
    return redirect(url)


@app.route("/callback")
def callback():
    code = request.args.get("code")
    error = request.args.get("error_description")
    if error:
        return f"<p>Ошибка: {error}</p>"
    if not code:
        return "<p>Код не получен</p>"

    resp = http.get("https://oauth.vk.com/access_token", params={
        "client_id": VK_APP_ID,
        "client_secret": VK_APP_SECRET,
        "redirect_uri": VK_REDIRECT_URI,
        "code": code,
    })
    data = resp.json()

    if "error" in data:
        return f"<p>Ошибка VK: {data}</p>"

    token = data.get("access_token", "")
    user_id = data.get("user_id", "")
    return f"""
    <h2>Токен получен!</h2>
    <p>User ID: {user_id}</p>
    <p>Скопируй токен в .env как VK_TOKEN:</p>
    <textarea rows="4" cols="80" onclick="this.select()">{token}</textarea>
    <br><br><a href="/">Вернуться на дашборд</a>
    """


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    app.run(host="0.0.0.0", port=port, debug=False)
