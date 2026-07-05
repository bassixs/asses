# Веб-версия (сайт)

Сайт переиспользует всё ИИ-ядро бота (`bot/services`, `bot/models`) и убирает
зависимость от Telegram. Бот заморожен тегом `bot-v1.0`.

## Запуск для разработки

**Backend (FastAPI):**
```bash
# из корня репозитория, окружение как у бота (.env: AITUNNEL_API_KEY и т.д.)
.venv/bin/uvicorn web.backend.app:app --reload --port 8000
# документация API: http://127.0.0.1:8000/docs
```

**Frontend (React + Vite):**
```bash
cd web/frontend
npm install
npm run dev          # http://localhost:5173 (проксирует /api → :8000)
```

## Сценарий в UI
Дашборд → создать центр → добавить участника (код или авто) → добавить упражнение →
на странице упражнения: инструкции (по желанию) → способ оценки:
- 🎙 по аудио: загрузить блокнот-шаблон + аудио → статус обработки → скачать заполненный блокнот;
- 📊 заполненный блокнот: загрузить готовый .xlsx.
Затем на странице участника — «Сформировать отчёт» и скачать DOCX/PPTX/ИПР.

## Прод (кратко)
```bash
cd web/frontend && npm run build     # статика в web/frontend/dist
```
Дальше nginx раздаёт `dist/` и проксирует `/api` на uvicorn (systemd-сервис), либо
FastAPI отдаёт `dist/` через StaticFiles. Домен + HTTPS.

Структура и фазы — в `docs/WEB_PLAN.md`.
