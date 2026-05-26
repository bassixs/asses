# HR Assessment Telegram Bot

## Кратко

Проект — Telegram-бот для HR-ассесмента управленческих компетенций по записям интервью.

Бот принимает голосовые сообщения, аудиофайлы или документы с записью интервью, сохраняет файл, расшифровывает речь через Yandex SpeechKit, сохраняет транскрипт в SQLite, а затем по команде `/assess <ID>` отправляет транскрипт в YandexGPT и возвращает HR-у структурированный отчет по компетенциям.

Репозиторий:

```text
https://github.com/bassixs/asses.git
```

Бот в Telegram:

```text
@assessment40_bot
```

## Что сделано

- Создан Python-проект на `aiogram 3.x`.
- Реализован Telegram-бот с командами:
  - `/start` — приветствие и инструкция;
  - `/criteria` — список текущих компетенций;
  - `/my_assessments` — список последних оценок HR;
  - `/assess <ID>` — запуск оценки по сохраненному транскрипту.
- Добавлена обработка:
  - voice messages;
  - audio files;
  - audio documents;
  - Excel-блокнотов наблюдателя `.xlsx`.
- Добавлена интеграция с Yandex SpeechKit:
  - короткие Ogg Opus / raw LPCM файлы идут через sync API v1;
  - длинные интервью и MP3 идут через Object Storage + async SpeechKit API v2.
- Добавлена интеграция с YandexGPT:
  - используется structured output через JSON schema;
  - ответ валидируется Pydantic-моделью;
  - отчет сохраняется в базу.
- Добавлена база данных:
  - SQLAlchemy 2.0 async;
  - SQLite на старте;
  - Alembic migration.
- Добавлен сценарий ассессмент-центра:
  - загрузка Excel-блокнота наблюдателя;
  - извлечение компетенций и поведенческих индикаторов из колонок B/C;
  - оценка индикаторов по транскрипту через YandexGPT;
  - заполнение колонок D/E/F;
  - расчет уровня компетенции без учета `НЗ`;
  - отправка заполненного `.xlsx` обратно HR-у.
- Добавлена Yandex Cloud инфраструктура:
  - service account `hr-assessment-bot`;
  - роли для SpeechKit, YandexGPT и Object Storage;
  - Object Storage bucket для аудиофайлов.
- Проект развернут на сервере Timeweb:
  - Ubuntu 24.04;
  - systemd service `asses-bot`;
  - бот запущен в polling-режиме.

## Стек

```text
Python 3.11+
aiogram 3.x
Yandex SpeechKit
YandexGPT
Yandex Object Storage
SQLAlchemy 2.0
Alembic
SQLite
Pydantic v2
python-dotenv
aiohttp
boto3
logging
systemd
```

## Структура проекта

```text
bot/
  main.py                 # Точка входа, запуск aiogram dispatcher
  config.py               # Настройки через .env и pydantic-settings
  database.py             # Async SQLAlchemy engine/session
  keyboards.py            # Reply/Inline keyboards
  handlers/
    common.py             # /start, /criteria
    media.py              # Загрузка и расшифровка файлов
    assessment.py         # /assess, /my_assessments, форматирование отчета
    notebook.py           # /fill_notebook и Excel-блокноты наблюдателя
  models/
    record.py             # InterviewRecord
    assessment.py         # AssessmentResult
    notebook.py           # ObserverNotebook, NotebookFillResult
  services/
    speechkit.py          # Sync/async SpeechKit transcription
    yandex_gpt.py         # YandexGPT JSON completion
    assessment.py         # analyze_transcript() и system prompt
    object_storage.py     # Upload в Yandex Object Storage
    observer_notebook.py  # Парсинг, анализ и заполнение Excel-блокнота
alembic/
  versions/
    20260524_0001_initial.py
docs/
  YANDEX_CLOUD_SETUP.md
  PROJECT_OVERVIEW.md
scripts/
  setup_yandex_cloud.ps1
.env.example
requirements.txt
alembic.ini
```

## Как работает основной сценарий

1. HR отправляет боту запись интервью.
2. `bot/handlers/media.py` получает Telegram file_id.
3. Бот скачивает файл в локальную папку:

```text
data/uploads/
```

4. `bot/services/speechkit.py` выбирает способ распознавания:
   - если файл маленький и формат подходит, используется sync SpeechKit v1;
   - если файл длинный или MP3, файл загружается в Object Storage и запускается async SpeechKit v2.
5. SpeechKit возвращает транскрипт.
6. Транскрипт сохраняется в таблицу `interview_records`.
7. Бот отвечает:

```text
✅ Расшифровано. ID: <id>. Напиши /assess <id> для оценки по компетенциям
```

8. HR отправляет:

```text
/assess <id>
```

9. `bot/services/assessment.py` формирует system prompt и вызывает YandexGPT.
10. YandexGPT возвращает JSON по компетенциям.
11. JSON валидируется Pydantic-моделью `AssessmentReport`.
12. Результат сохраняется в таблицу `assessment_results`.
13. Бот отправляет HR-у отчет.

## Как работает сценарий ассессмент-центра

1. HR отправляет аудиозапись упражнения.
2. Бот расшифровывает запись и возвращает `ID записи`.
3. HR отправляет Excel-блокнот наблюдателя `.xlsx`.
4. Бот сохраняет блокнот, извлекает индикаторы из колонки C и возвращает `ID блокнота`.
5. HR запускает:

```text
/fill_notebook <ID записи> <ID блокнота>
```

6. Бот отправляет в YandexGPT транскрипт упражнения и список поведенческих индикаторов.
7. YandexGPT определяет роли и оценивает только реплики оцениваемого участника.
8. Для каждого индикатора возвращается `+`, `-` или `НЗ`.
9. Бот заполняет блокнот:
   - колонка D — проявление индикатора;
   - колонка E — цитата и таймкод для `+`, причина для `НЗ`;
   - колонка F — уровень компетенции.
10. Бот отправляет заполненный `.xlsx` обратно в Telegram.

Формула уровня компетенции:

```text
% проявления = количество "+" / количество наблюдаемых индикаторов * 100
```

`НЗ` исключается из расчета.

Шкала:

```text
90-100% -> 3
80-90%  -> 2.5
60-80%  -> 2
40-60%  -> 1.5
20-40%  -> 1
5-20%   -> 0.5
0-5%    -> 0
```

## Формат оценки

Для каждой компетенции YandexGPT возвращает:

```json
{
  "name": "Название компетенции",
  "manifested": true,
  "score": 0,
  "evidence": ["точная цитата из транскрипта"],
  "comment": "краткое пояснение"
}
```

Также возвращаются:

```json
{
  "overall_summary": "общий вывод",
  "risks": ["риски"],
  "recommendations": ["что уточнить дальше"]
}
```

## Компетенции

Список компетенций сейчас задан в `bot/config.py`:

```text
Стратегическое мышление
Лидерство и влияние
Принятие решений
Коммуникация
Управление командой
Ориентация на результат
Адаптивность
Эмоциональный интеллект
```

Это placeholder-список. Его можно доработать под методологию заказчика.

## Yandex Cloud

Создан сервисный аккаунт:

```text
hr-assessment-bot
```

Назначены роли:

```text
ai.speechkit-stt.user
ai.languageModels.user
storage.uploader
storage.editor
```

Создан Object Storage bucket:

```text
hr-assessment-audio-b1geibs546ki0iddqed8
```

Файлы для async SpeechKit загружаются с префиксом:

```text
interviews/
```

Для настройки Yandex Cloud есть инструкция:

```text
docs/YANDEX_CLOUD_SETUP.md
```

И PowerShell-скрипт:

```text
scripts/setup_yandex_cloud.ps1
```

## Переменные окружения

Пример лежит в:

```text
.env.example
```

На сервере используется `.env`, который не хранится в Git.

Основные переменные:

```dotenv
BOT_TOKEN=
YANDEX_SPEECHKIT_API_KEY=
YANDEX_GPT_API_KEY=
YANDEX_FOLDER_ID=
YANDEX_STORAGE_BUCKET=
YANDEX_STORAGE_ACCESS_KEY_ID=
YANDEX_STORAGE_SECRET_ACCESS_KEY=
YANDEX_STORAGE_ENDPOINT=https://storage.yandexcloud.net
YANDEX_STORAGE_PREFIX=interviews
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
LOG_LEVEL=INFO
DOWNLOAD_DIR=./data/uploads
YANDEX_GPT_MODEL_URI=gpt://<folder_id>/yandexgpt/rc
SPEECHKIT_SYNC_MAX_BYTES=1000000
SPEECHKIT_ASYNC_POLL_INTERVAL_SECONDS=10
SPEECHKIT_ASYNC_TIMEOUT_SECONDS=7200
```

Важно: реальные токены и ключи не должны попадать в Git.

## База данных

SQLite-файл:

```text
data/app.db
```

Таблицы:

### interview_records

Хранит:

- id записи;
- chat_id;
- user_id HR-а;
- Telegram file_id;
- тип файла;
- путь к локальному файлу;
- транскрипт;
- дату создания.

### assessment_results

Хранит:

- id оценки;
- record_id;
- chat_id;
- user_id HR-а;
- JSON-результат оценки;
- summary;
- дату создания.

### observer_notebooks

Хранит:

- id блокнота;
- chat_id;
- user_id HR-а;
- Telegram file_id;
- имя файла;
- путь к локальному `.xlsx`;
- дату загрузки.

### notebook_fill_results

Хранит:

- id результата;
- record_id;
- notebook_id;
- путь к заполненному `.xlsx`;
- JSON с оценками индикаторов и уровнями компетенций;
- дату создания.

Миграции:

```bash
python -m alembic upgrade head
```

## Сервер

Сервер Timeweb:

```text
Ubuntu 24.04
2 CPU
4 GB RAM
50 GB NVMe
```

Проект развернут в:

```text
/opt/asses
```

Виртуальное окружение:

```text
/opt/asses/.venv
```

Systemd service:

```text
asses-bot
```

Админ-панель запускается как отдельное ASGI-приложение:

```text
bot.admin:app
```

Рекомендуемый bind:

```text
127.0.0.1:8080
```

Так панель доступна только через SSH-туннель или reverse proxy с авторизацией.

## Команды эксплуатации

Статус бота:

```bash
systemctl status asses-bot --no-pager
```

Логи:

```bash
journalctl -u asses-bot -f
```

Последние логи:

```bash
journalctl -u asses-bot -n 100 --no-pager
```

Перезапуск:

```bash
systemctl restart asses-bot
```

Остановка:

```bash
systemctl stop asses-bot
```

Запуск:

```bash
systemctl start asses-bot
```

Обновление кода с GitHub:

```bash
cd /opt/asses
git pull
. .venv/bin/activate
pip install -r requirements.txt
python -m alembic upgrade head
systemctl restart asses-bot
```

Запуск админки вручную:

```bash
cd /opt/asses
. .venv/bin/activate
uvicorn bot.admin:app --host 127.0.0.1 --port 8080
```

SSH-туннель для доступа с локального компьютера:

```bash
ssh -L 8080:127.0.0.1:8080 root@5.42.107.42
```

После этого открыть:

```text
http://127.0.0.1:8080
```

## Что уже проверено

- Бот успешно стартует на сервере.
- Polling работает.
- `/start` отвечает.
- Excel-сервис проверен на тестовом блокноте: индикаторы извлекаются, колонки D/E/F заполняются, уровень считается корректно.
- YandexGPT smoke-test работает.
- Object Storage upload smoke-test был проверен локально.
- Alembic migration применена на сервере.
- `.env` на сервере создан и закрыт правами `600`.

## Важные исправления по ходу работы

### Telegram HTML parse mode

Сначала глобально был включен `parse_mode=HTML`. Из-за текста `/assess <ID>` Telegram воспринимал `<ID>` как HTML-тег и падал с ошибкой:

```text
Bad Request: can't parse entities: Unsupported start tag "id"
```

Исправление: глобальный HTML parse mode отключен в `bot/main.py`.

### Pydantic env parsing

В `bot/config.py` поля окружения переведены на `validation_alias`, чтобы `.env` корректно читался в Pydantic v2 / pydantic-settings.

### SQLite data directory

Перед миграциями на сервере нужно создать:

```bash
mkdir -p /opt/asses/data/uploads
```

Иначе SQLite не сможет создать файл `data/app.db`.

## Ограничения текущей версии

- Для `.wav`, `.m4a`, `.aac`, `.mp4`, `.docx`, `.pdf` пока нет автоматической конвертации/извлечения аудио.
- Async SpeechKit сейчас поддерживает в коде:
  - `.ogg`
  - `.oga`
  - `.opus`
  - `.mp3`
  - `.pcm`
  - `.lpcm`
  - `.raw`
- SQLite подходит для старта, но при росте нагрузки лучше перейти на PostgreSQL.
- Нет веб-дашборда.
- Нет PDF-отчетов.
- Нет отдельной админки критериев.
- Нет очереди фоновых задач: длинное распознавание выполняется в процессе бота.
- Формирование индивидуального отчета и ИПР пока заложено как следующий этап, но не реализовано как отдельные DOCX/PDF-файлы.

## Что нужно от заказчика для следующего этапа

Нужны реальные или тестовые файлы интервью:

- голосовые сообщения Telegram;
- MP3/Ogg Opus аудиофайлы;
- записи разной длины;
- желательно несколько интервью разного качества звука.

На этих файлах нужно проверить:

- качество распознавания SpeechKit;
- качество evidence-цитат;
- адекватность оценок 0-5;
- полноту списка компетенций;
- удобство формата отчета для HR.

## Возможные следующие доработки

- Автоматическая конвертация WAV/M4A/MP4 через ffmpeg.
- PDF-отчеты.
- Web dashboard для HR.
- Расширенная админка с фильтрами, скачиванием файлов и ролями доступа.
- PostgreSQL вместо SQLite.
- Очередь задач через Redis/RQ/Celery/Arq.
- Webhook вместо polling.
- Настройка критериев через админ-команды.
- Экспорт отчетов в Google Sheets / Excel.
- Роли пользователей и доступы.
- Хранение оригиналов файлов только в Object Storage без локального дубля.
- Очистка старых файлов по расписанию.
- Мониторинг и алерты.
