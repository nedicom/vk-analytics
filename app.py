import json
import os
from datetime import datetime

import anthropic
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from vk_client import get_group_stats, get_videos

load_dotenv()

app = Flask(__name__)

VK_TOKEN = os.getenv("VK_TOKEN")
VK_GROUP_ID = os.getenv("VK_GROUP_ID")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

HISTORY_FILE = "history.json"

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


@app.route("/")
def index():
    try:
        videos = get_videos(VK_GROUP_ID, VK_TOKEN, count=30)
        error = None
    except Exception as e:
        videos = []
        error = str(e)
    history = load_history()
    return render_template("index.html", videos=videos, history=history, error=error)


@app.route("/api/refresh")
def refresh():
    try:
        videos = get_videos(VK_GROUP_ID, VK_TOKEN, count=30)
        return jsonify({"ok": True, "videos": videos})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/analyze", methods=["POST"])
def analyze():
    try:
        videos = get_videos(VK_GROUP_ID, VK_TOKEN, count=30)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    past = load_history()
    past_context = ""
    if past:
        last = past[-1]
        past_context = f"\n\nПрошлый анализ ({last['date']}):\n{last['analysis'][:800]}\n"

    videos_text = "\n".join([
        f"• «{v['title']}» | {v['date']} | 👁 {v['views']} | ❤️ {v['likes']} | 💬 {v['comments']} | ↗️ {v['reposts']} | ⏱ {v['duration']}с"
        for v in videos
    ])

    user_message = (
        f"Статистика последних {len(videos)} видео группы:{past_context}\n\n{videos_text}\n\n"
        "Проанализируй результаты. Что работает лучше всего? Какие паттерны видишь? "
        "Дай конкретные рекомендации для роста просмотров и продаж."
    )

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    analysis = response.content[0].text
    save_to_history(analysis, len(videos))
    return jsonify({"ok": True, "analysis": analysis})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
