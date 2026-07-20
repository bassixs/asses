# Справка: бот заморожен, работает сайт

Обновлено: 2026-07-14.

## Как оно сейчас работает

| Что | Состояние |
|---|---|
| **Сайт** (рабочий продукт) | ✅ работает: **https://hr40.ru** (Let's Encrypt, http→https). Вход по аккаунту (админ `hr40`/`1172` — сменить в разделе «Пользователи»), несколько специалистов на общем пространстве. Внутри — systemd-сервис `asses-web` на :8000 за nginx |
| Демо-витрина (без бэкенда) | ✅ https://bassixs.github.io/asses/ — автообновляется при пуше в ветку `main` |
| **Telegram-бот** | ⏸ остановлен и выключен из автозапуска (`asses-bot` disabled) |
| Контейнер `telegram-bot-api` | ⏸ остановлен, автоперезапуск отключён (`--restart=no`) |
| Cron рестарта контейнера (каждые 6ч) | 🗑 удалён |
| Код бота | 🧊 заморожен: git-тег **`bot-v1.0`** и ветка `bot-legacy` (и в `main` он тоже есть) |

Почему бот остановлен: провайдер этого сервера блокирует доступ к серверам Telegram —
бот физически не может работать. Вся его ИИ-логика живёт в сайте (общее ядро `bot/services`).

## Управление сайтом (шпаргалка)

```bash
systemctl status asses-web          # состояние
systemctl restart asses-web         # перезапуск
journalctl -u asses-web -f          # живые логи
```

Обновить сайт до свежей ветки `main`:
```bash
cd /opt/asses-web && git fetch -q origin main && git reset --hard origin/main
cd web/frontend && npm install && npm run build   # только если менялся фронтенд
systemctl restart asses-web
```

Данные: БД `/opt/asses/data/app.db`, загрузки `/opt/asses/data/uploads`,
отчёты `/opt/asses/data/reports` — общие у бота и сайта.

## Как включить бота обратно

⚠️ Сработает только если появился канал к Telegram (сменился провайдер/сервер,
или поднят прокси) — иначе бот запустится, но будет молчать, как раньше.

```bash
# 1) контейнер локального Bot API
docker update --restart=unless-stopped telegram-bot-api
docker start telegram-bot-api
sleep 30

# 2) сам бот
systemctl enable --now asses-bot

# 3) проверить
journalctl -u asses-bot -n 20 --no-pager    # ждать "Bot started" + "Start polling"
# и написать боту /start в Telegram
```

(По желанию вернуть профилактический cron:
`( crontab -l; echo "0 */6 * * * /usr/bin/docker restart telegram-bot-api && sleep 30 && /usr/bin/systemctl restart asses-bot" ) | crontab -`)

## Как развернуть код бота с нуля (на новом сервере)

```bash
git clone https://github.com/bassixs/asses && cd asses
git checkout bot-v1.0        # замороженная рабочая версия бота
# дальше по docs/PROJECT_OVERVIEW.md: venv, .env, alembic upgrade head,
# docker-контейнер telegram-bot-api, systemd asses-bot
```

Полная картина проекта и план — `docs/STATUS.md`.
