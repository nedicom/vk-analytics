---
name: VK Analytics Dashboard
description: Flask дашборд аналитики ВКонтакте для NEDICOM, группа 72406118
type: project
originSessionId: f1a8e801-236f-456d-a0bf-5822956094c2
---
Flask-приложение для аналитики клипов и статистики VK-группы NEDICOM (nedicom, ID 72406118).

**Стек:** Python 3.7 (сервер), Flask, requests, python-dotenv (anthropic убран)  
**Шаблон:** templates/index.html (тёмная тема, таблица видео + боковой анализ Claude)  
**VK клиент:** vk_client.py — video.get (album_id=-16 для клипов), stats.get, API v5.199  
**Сервер:** vk.nedicom.ru, /home/forge/vk.nedicom.ru, запуск: `python3 app.py &`  
**Git remote:** github.com/nedicom/vk-analytics, деплой через `git pull origin main`

**Env на сервере (/home/forge/vk.nedicom.ru/.env):**
- VK_TOKEN — пользовательский OAuth токен (истекает через 24ч, нужно периодически обновлять)
- VK_GROUP_ID=72406118
- VK_APP_ID=54587343 (старое приложение nedicom-stats на vk.com/apps)
- VK_APP_SECRET — защищённый ключ приложения
- VK_REDIRECT_URI=https://vk.nedicom.ru/callback

**Токен (VK_TOKEN):**
Использовать СЕРВИСНЫЙ КЛЮЧ приложения 54587343 (nedicom-stats) — он не привязан к IP.
Найти: vk.com/apps?act=manage → приложение 54587343 → Сервисный ключ.
Пользовательские токены привязаны к IP браузера и не работают с сервера.

**Что работает:**
- wall.get с filter=owner → извлечение short_video вложений (клипы) — РАБОТАЕТ с сервисным ключом
- groups.getById — работает с любым токеком
- Деплой: `git pull origin main && systemctl restart vk-analytics`
- Сервис: systemd, gunicorn на порту 8001, /etc/systemd/system/vk-analytics.service

**Что не работает / ограничения:**
- Групповой токен не работает с video.get ("invalid token type")
- ads scope заблокирован VK — нужно спец. разрешение
- Python 3.7 на локальной машине — используй `from __future__ import annotations`
- video.get не работает для клипов — клипы берутся через wall.get (тип вложения short_video)

**Следующие задачи:**
- Добавить статистику группы (stats.get)
- Разобраться с рекламным кабинетом (ads API)

**Why:** Проект для аналитики контента и рекламы группы ВКонтакте NEDICOM.
**How to apply:** Всегда использовать пользовательский OAuth токен (не групповой). При ошибках авторизации — сначала проверить не истёк ли токен.
