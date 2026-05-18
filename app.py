import json
import os
from datetime import datetime, timedelta
from functools import wraps

import requests as _requests_lib

_http = _requests_lib.Session()
_http.trust_env = False
_app_proxy = None  # будет задан после load_dotenv
http = _http
from dotenv import load_dotenv, set_key
from flask import Flask, jsonify, redirect, render_template, request, session

from vk_client import get_ads_stats, get_ads_stats_per_video, get_comments_stats, get_detailed_campaign_stats, get_group_info, get_group_stats, get_videos

load_dotenv()

_env_proxy = os.getenv("HTTPS_PROXY") or os.getenv("ALL_PROXY")
if _env_proxy:
    _http.proxies = {"https": _env_proxy, "http": _env_proxy}


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
MAPPINGS_FILE = "campaign_mappings.json"
MEMBER_HISTORY_FILE = "member_count_history.json"


def track_member_count(count: int):
    today = datetime.now().strftime("%Y-%m-%d")
    history = {}
    if os.path.exists(MEMBER_HISTORY_FILE):
        with open(MEMBER_HISTORY_FILE, encoding="utf-8") as f:
            history = json.load(f)
    history[today] = count
    cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    history = {k: v for k, v in history.items() if k >= cutoff}
    with open(MEMBER_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f)


def get_member_count_delta() -> dict:
    if not os.path.exists(MEMBER_HISTORY_FILE):
        return {}
    with open(MEMBER_HISTORY_FILE, encoding="utf-8") as f:
        history = json.load(f)
    if len(history) < 2:
        return {}
    sorted_dates = sorted(history.keys())
    current_date = sorted_dates[-1]
    current = history[current_date]
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    past_dates = [d for d in sorted_dates[:-1] if d <= cutoff]
    past_date = past_dates[-1] if past_dates else sorted_dates[0]
    past = history[past_date]
    period = (datetime.strptime(current_date, "%Y-%m-%d") - datetime.strptime(past_date, "%Y-%m-%d")).days
    return {"delta": current - past, "period_days": period}


def load_mappings() -> dict:
    if os.path.exists(MAPPINGS_FILE):
        with open(MAPPINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_mappings(mappings: dict):
    with open(MAPPINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(mappings, f, ensure_ascii=False, indent=2)


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

Стиль ответа: конкретно, с цифрами из данных, без воды. Сначала коротко — что работает, потом — 3-5 чётких рекомендаций с обоснованием.

Если в данных есть рекламная статистика по кампаниям — обязательно используй её: анализируй эффективность рекламы (CPM, CPC, CTR, тренды), сопоставляй с органическими показателями видео, выявляй какие кампании дают лучший результат и почему."""


def _format_campaign_stats_for_claude(detailed: dict, mappings: dict, videos: list) -> str:
    """Форматирует детальную статистику кампаний для передачи Claude."""
    if not detailed:
        return ""

    vid_by_id = {str(v["id"]): v for v in videos}
    lines = ["\n\n=== ДЕТАЛЬНАЯ СТАТИСТИКА РЕКЛАМНЫХ КАМПАНИЙ ==="]

    for video_id, plan_id in mappings.items():
        stats = detailed.get(plan_id)
        if not stats:
            continue
        video = vid_by_id.get(str(video_id), {})
        video_title = video.get("title", f"Видео {video_id}")[:60]

        lines.append(f"\n📹 КЛИП: «{video_title}»")
        lines.append(f"📣 Кампания: {stats['name']} (ID {plan_id})")

        budget_info = []
        if stats["total_budget"]:
            budget_info.append(f"общий бюджет {stats['total_budget']} ₽")
        if stats["budget_left"] is not None:
            budget_info.append(f"остаток {stats['budget_left']} ₽")
        if budget_info:
            lines.append(f"   Бюджет: {' | '.join(budget_info)}")

        lines.append(
            f"   Итого за 30 дн.: {stats['total_shows']:,} показов | "
            f"{stats['total_clicks']:,} кликов | CTR {stats['total_ctr']}% | "
            f"CPM {stats['avg_cpm']} ₽ | CPC {stats['avg_cpc']} ₽ | "
            f"Расход {stats['spent']} ₽"
        )
        lines.append(f"   Тренд CTR: {stats['ctr_trend']} | Активных дней: {stats['active_days']}")

        if stats["daily"]:
            lines.append("   По дням (последние 14):")
            for d in stats["daily"][-14:]:
                lines.append(
                    f"     {d['date']}: {d['shows']:,} пок. | {d['clicks']} кл. | "
                    f"CTR {d['ctr']}% | CPM {d['cpm']} ₽ | CPC {d['cpc']} ₽ | {d['spent']} ₽"
                )

    return "\n".join(lines)


def load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def _extract_title(analysis: str) -> str:
    for line in analysis.split("\n"):
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:100]
    return "Анализ"


def save_to_history(analysis: str, video_count: int, question: str = ""):
    history = load_history()
    title = question.strip() if question.strip() else _extract_title(analysis)
    history.append({
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "analysis": analysis,
        "video_count": video_count,
        "title": title,
        "is_question": bool(question.strip()),
    })
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
        msg = str(e).lower()
        if "internal server error" in msg or "unknown error" in msg:
            error = "ВКонтакте временно не отвечает — обновите страницу через минуту."
        elif "invalid token" in msg or "access_token" in msg or "token has expired" in msg:
            error = "Токен ВКонтакте недействителен — обратитесь к разработчику."
        elif "too many requests" in msg or "rate limit" in msg:
            error = "Слишком много запросов к ВК — подождите минуту и обновите страницу."
        else:
            error = f"Ошибка ВКонтакте: {e} — обратитесь к разработчику если ошибка повторяется."
    group_info = get_group_info(VK_GROUP_ID, VK_TOKEN)
    if group_info.get("members_count"):
        track_member_count(group_info["members_count"])
    member_delta = get_member_count_delta()
    stats = calc_stats(videos)
    ads = get_ads_stats(ADS_CLIENT_ID, ADS_CLIENT_SECRET) if ADS_CLIENT_ID else {}
    history = load_history()
    scripts = load_scripts()
    mappings = load_mappings()
    comments_stats = get_comments_stats(VK_GROUP_ID, VK_TOKEN, videos)
    ads_per_video = get_ads_stats_per_video(ADS_CLIENT_ID, ADS_CLIENT_SECRET, mappings) if ADS_CLIENT_ID else {}
    return render_template("index.html", videos=videos, history=history, error=error, group_info=group_info, stats=stats, ads=ads, scripts=scripts, comments_stats=comments_stats, ads_per_video=ads_per_video, mappings=mappings, member_delta=member_delta)


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


@app.route("/api/campaigns")
@login_required
def get_campaigns():
    from vk_client import get_ads_token
    if not ADS_CLIENT_ID or not ADS_CLIENT_SECRET:
        return jsonify([])
    token = get_ads_token(ADS_CLIENT_ID, ADS_CLIENT_SECRET)
    if not token:
        return jsonify([])
    headers = {"Authorization": f"Bearer {token}"}
    data = http.get("https://target.my.com/api/v2/ad_plans.json",
                    headers=headers, params={"limit": 250}).json()
    items = sorted(data.get("items", []), key=lambda x: x["id"], reverse=True)
    return jsonify([{"id": p["id"], "name": p["name"]} for p in items])


@app.route("/api/ads-debug")
@login_required
def ads_debug():
    from vk_client import get_ads_token
    token = get_ads_token(ADS_CLIENT_ID, ADS_CLIENT_SECRET)
    headers = {"Authorization": f"Bearer {token}"}
    results = {}
    for ep in ["ad_plans", "packages", "campaigns"]:
        r = http.get(f"https://target.my.com/api/v2/{ep}.json", headers=headers, params={"limit": 3})
        results[ep] = {"status": r.status_code, "first_items": r.json().get("items", [])[:2]}
    return jsonify(results)


@app.route("/api/mapping/<video_id>", methods=["POST"])
@login_required
def save_mapping(video_id):
    campaign_id = request.json.get("campaign_id")
    mappings = load_mappings()
    if campaign_id:
        mappings[video_id] = int(campaign_id)
    else:
        mappings.pop(video_id, None)
    save_mappings(mappings)
    return jsonify({"ok": True})


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

    body = request.json or {}
    question = body.get("question", "").strip()
    messages_history = body.get("messages", [])

    if not messages_history:
        # Новый диалог — собираем контекст видео
        try:
            videos = get_videos(VK_GROUP_ID, VK_TOKEN, count=30)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

        past = load_history()
        past_context = ""
        if past:
            last = past[-1]
            past_context = f"\n\nПрошлый анализ ({last['date']}):\n{last['analysis'][:800]}\n"

        scripts = load_scripts()
        mappings = load_mappings()
        videos_text = "\n".join([
            f"• «{v['title']}» | {v['date']} | 👁 {v['views']} | ❤️ {v['likes']} | 💬 {v['comments']} | ↗️ {v['reposts']} | ⏱ {v['duration']}с"
            + (f"\n  Сценарий: {scripts[str(v['id'])]}" if str(v['id']) in scripts else "")
            for v in videos
        ])

        # Детальная рекламная статистика по привязанным кампаниям
        campaign_context = ""
        if ADS_CLIENT_ID and mappings:
            try:
                plan_ids = list(set(int(v) for v in mappings.values()))
                detailed = get_detailed_campaign_stats(ADS_CLIENT_ID, ADS_CLIENT_SECRET, plan_ids)
                campaign_context = _format_campaign_stats_for_claude(detailed, mappings, videos)
            except Exception:
                pass

        if question:
            user_content = (
                f"Данные последних {len(videos)} видео группы:{past_context}\n\n{videos_text}"
                f"{campaign_context}\n\nВопрос: {question}"
            )
        else:
            user_content = (
                f"Статистика последних {len(videos)} видео группы:{past_context}\n\n{videos_text}"
                f"{campaign_context}\n\n"
                "Проанализируй результаты с учётом сценариев там где они есть. "
                "Что работает лучше всего? Какие темы и форматы дают больший охват? "
                "Дай конкретные рекомендации для роста просмотров и продаж."
            )
        messages = [{"role": "user", "content": user_content}]
        video_count = len(videos)
    else:
        # Продолжение диалога — добавляем новое сообщение пользователя
        messages = list(messages_history)
        if question:
            messages.append({"role": "user", "content": question})
        video_count = 0

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
            messages=messages,
        )
    except anthropic.APIError as e:
        code = e.status_code
        if code == 529:
            msg = "Серверы Claude перегружены — подождите 1-2 минуты и попробуйте снова."
        elif code == 503:
            msg = "Сервис Claude временно недоступен — попробуйте через несколько минут."
        elif code == 401:
            msg = "Неверный API ключ Claude — обратитесь к разработчику."
        elif code == 403:
            msg = "Доступ к Claude заблокирован (возможно, проблема с прокси) — обратитесь к разработчику."
        elif code == 429:
            msg = "Превышен лимит запросов к Claude — подождите минуту и попробуйте снова."
        else:
            msg = f"Ошибка Claude ({code}) — обратитесь к разработчику."
        return jsonify({"ok": False, "error": msg}), 200

    analysis = response.content[0].text
    messages.append({"role": "assistant", "content": analysis})

    if not messages_history:
        title = question.strip() if question.strip() else _extract_title(analysis)
        save_to_history(analysis, video_count, question)
    else:
        title = question

    return jsonify({
        "ok": True,
        "analysis": analysis,
        "messages": messages,
        "title": title,
        "is_question": bool(question),
    })


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
