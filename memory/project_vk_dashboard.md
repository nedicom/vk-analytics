---
name: VK Analytics Dashboard
description: Flask дашборд аналитики ВКонтакте для NEDICOM, группа 72406118
type: project
originSessionId: 46dfdad0-f966-48b7-843a-f262ce6408a4
---
Flask-приложение для аналитики клипов и статистики VK-группы NEDICOM (nedicom, ID 72406118).

**Стек:** Python 3.10 (сервер), Flask, requests, python-dotenv, anthropic, httpx  
**Файлы:** app.py, vk_client.py, templates/index.html, templates/login.html  
**Сервер:** vk.nedicom.ru, /home/forge/vk.nedicom.ru  
**Сервис:** systemd + gunicorn, /etc/systemd/system/vk-analytics.service, порт 8001  
**Git:** github.com/nedicom/vk-analytics, ветка main  
**Автодеплой:** GitHub Actions (.github/workflows/deploy.yml) — пуш в main → SSH → git pull + restart  

**Env на сервере (/home/forge/vk.nedicom.ru/.env):**
- VK_TOKEN — сервисный ключ приложения 54587343 (не пользовательский, не привязан к IP)
- VK_GROUP_ID=72406118
- VK_APP_ID=54587343
- VK_APP_SECRET
- VK_REDIRECT_URI=https://vk.nedicom.ru/callback
- ADS_VK_CLIENT_ID, ADS_VK_SECRET — myTarget/VK Ads credentials
- ANTHROPIC_API_KEY — ключ из console.anthropic.com (НЕ claude.ai)
- DASHBOARD_PASSWORD — пароль для входа (Bonaqua1)
- SECRET_KEY — случайная строка для Flask сессий
- HTTPS_PROXY=socks5://127.0.0.1:1080 — прокси для Anthropic API (Россия заблокирована)

**Прокси (Shadowsocks):**
- Сервис ss-local (systemd), конфиг /etc/shadowsocks/config.json
- Сервер: 63.250.60.41:443, метод chacha20-ietf-poly1305
- Слушает на 127.0.0.1:1080, используется только приложением через HTTPS_PROXY
- Anthropic API требует явной передачи прокси: `httpx.Client(proxy=proxy)`

**VK API:**
- Клипы: wall.get (filter=owner) → вложения типа short_video (НЕ video.get)
- Комментарии: wall.getComments — первые 15 видео, уникальные авторы + дата последнего
- Статистика группы: groups.getById с fields=members_count

**myTarget/VK Ads API (target.my.com):**
- Токен: client_credentials, кешируется в ads_token_cache.json (переживает рестарты)
- При token_limit_exceeded: DELETE /token/delete.json с user_id из ответа ошибки
- Кампании: /api/v2/ad_plans.json (НЕ campaigns — там "Группа ДАТА", НЕ packages — форматы)
- ad_plans = реальные кампании с нормальными именами ("Рилс наследство Крым" и т.д.)
- Статистика: /api/v2/statistics/ad_plans/day.json
- Параметр списка: limit (НЕ _count — вызывает ошибку validation_failed)
- Маппинг video_id→campaign_id хранится в campaign_mappings.json (ручной выбор в UI)

**Что хранится на сервере (не в git):**
- .env — секреты
- history.json — история анализов Claude
- video_scripts.json — сценарии видео
- campaign_mappings.json — маппинг видео→кампания
- ads_token_cache.json — кеш токена myTarget
- Бэкап: cron 3:00 ночи → /home/forge/backups/

**Функции дашборда:**
- Таблица клипов: просмотры, лайки, комменты+авторы, репосты, длительность, реклама
- Рекламная статистика по видео: выпадающий список кампаний (ad_plans), ручной маппинг
- 📝 Сценарии: поле для текста/сценария каждого видео, Claude использует при анализе
- ✦ Анализ Claude: анализ последних 30 видео + сценарии + история
- Произвольный вопрос Claude с контекстом статистики
- История всех анализов (без лимита)
- Парольная защита (DASHBOARD_PASSWORD)
- Инструкция для новичков (раскрывающаяся панель)

**Деплой:**
```bash
git push origin main  # GitHub Actions задеплоит автоматически
# или вручную на сервере:
git pull && systemctl restart vk-analytics
```

**Why:** Проект для аналитики контента и рекламы группы ВКонтакте NEDICOM.
**How to apply:** При ошибках авторизации VK — проверить токен. При ошибках Anthropic 403 — проверить ss-local сервис. При token_limit_exceeded myTarget — код сам удаляет и перезапрашивает.
