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
  - длинные интервью и MP3 идут через Object Storage + async SpeechKit API v3;
  - для длинных аудио включен speaker labeling;
  - async SpeechKit API v2 оставлен как fallback.
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
- Настроен локальный Telegram Bot API Server для приема больших файлов:
  - Docker-контейнер `telegram-bot-api`;
  - локальный endpoint `http://127.0.0.1:8081`;
  - режим `--local`;
  - лимит скачивания в боте поднят до 2 GB;
  - добавлены увеличенные timeout и retry для больших медиа.
- Проверен полный pipeline на MP3-записи около 61 MB / 25 минут:
  - файл принят из Telegram;
  - файл скачан через локальный Telegram Bot API;
  - файл отправлен в Yandex Object Storage;
  - SpeechKit async вернул транскрипт;
  - YandexGPT сформировал оценку;
  - бот отправил результат в Telegram.
- Добавлена очередь задач обработки медиа:
  - handler Telegram быстро создает задачу в БД;
  - отдельный worker скачивает файл, запускает SpeechKit и сохраняет результат;
  - при перезапуске задачи в статусе `processing` возвращаются в очередь;
  - бот присылает статусы обработки в Telegram.
- Добавлен `.txt` файл расшифровки:
  - полный транскрипт в формате диалога `Ведущий: ...` / `Участник: ...`;
  - соседние реплики одного спикера объединяются, тайминги скрыты по умолчанию;
  - роли всегда приводятся к двум значениям: `ведущий` и `участник`;
  - при SpeechKit v3 роли строятся через `channelTag` дикторов, а не через построчное угадывание;
  - YandexGPT не переписывает текст построчно, чтобы не менять смысл реплик;
  - кнопка `Скачать расшифровку` под сообщением об успешной расшифровке.
- Улучшено качество текстового результата после SpeechKit:
  - добавлена автоматическая очистка явных и почти одинаковых соседних дублей;
  - дополнительно схлопываются похожие альтернативы с одинаковым таймкодом;
  - таймкод берется из альтернативы или первого слова, если SpeechKit его вернул;
  - добавлена команда `/rebuild_transcript <ID записи>` для пересборки `.txt` файла по уже сохраненной записи.

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
  BOT_USAGE_SIMPLE.md
  LOCAL_TELEGRAM_BOT_API.md
scripts/
  setup_yandex_cloud.ps1
.env.example
requirements.txt
alembic.ini
```

## Как работает основной сценарий

1. HR отправляет боту запись интервью.
2. `bot/handlers/media.py` получает Telegram file_id.
3. Бот создает запись в таблице `media_processing_jobs` со статусом `queued`.
4. Пользователь сразу получает номер задачи.
5. Worker забирает задачу и переводит ее в статус `processing`.
6. Если включен локальный Telegram Bot API Server, aiogram обращается не к
   `api.telegram.org`, а к `http://127.0.0.1:8081`.
7. Worker скачивает файл в локальную папку:

```text
data/uploads/
```

8. `bot/services/speechkit.py` выбирает способ распознавания:
   - если файл маленький и формат подходит, используется sync SpeechKit v1;
   - если файл длинный или MP3, файл загружается в Object Storage и запускается async SpeechKit v3;
   - если v3 недоступен или вернул ошибку, бот может откатиться на async SpeechKit v2.
9. SpeechKit возвращает транскрипт.
10. `bot/services/speechkit.py` очищает явные повторы и почти одинаковые соседние фразы.
11. Очищенный транскрипт сохраняется в таблицу `interview_records`.
12. Worker создает `.txt` файл с полным транскриптом в формате `Ведущий: ...` / `Участник: ...`.
13. Бот отвечает:

```text
Задача #<job_id>: расшифровано.
ID записи: <id>
```

Под сообщением есть кнопки `Оценить компетенции` и `Скачать расшифровку`.

14. HR отправляет:

```text
/assess <id>
```

15. `bot/services/assessment.py` формирует system prompt и вызывает YandexGPT.
16. YandexGPT возвращает JSON по компетенциям.
17. JSON валидируется Pydantic-моделью `AssessmentReport`.
18. Результат сохраняется в таблицу `assessment_results`.
19. Бот отправляет HR-у отчет.

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
TELEGRAM_API_BASE_URL=http://127.0.0.1:8081
TELEGRAM_API_IS_LOCAL=true
TELEGRAM_DOWNLOAD_MAX_BYTES=2000000000
TELEGRAM_FILE_REQUEST_TIMEOUT_SECONDS=900
TELEGRAM_FILE_DOWNLOAD_TIMEOUT_SECONDS=900
TELEGRAM_FILE_DOWNLOAD_ATTEMPTS=3
TELEGRAM_FILE_DOWNLOAD_RETRY_DELAY_SECONDS=15
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

### media_processing_jobs

Хранит:

- id задачи;
- chat_id и user_id;
- Telegram file_id;
- тип файла, имя и размер;
- статус `queued` / `processing` / `completed` / `failed`;
- ссылку на созданную запись `record_id`;
- текст ошибки;
- даты создания, старта и завершения.

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

Локальный Telegram Bot API Server:

```text
Docker container: telegram-bot-api
Endpoint: http://127.0.0.1:8081
Data dir: /opt/telegram-bot-api/data
Temp dir: /opt/telegram-bot-api/temp
Host symlink: /var/lib/telegram-bot-api -> /opt/telegram-bot-api/data
SSH port: 22222
```

Рабочий запуск контейнера сейчас использует `--network host`, потому что при Docker NAT
локальный `telegram-bot-api` зависал на `getMe` и нестабильно ходил в Telegram MTProto.

Админ-панель доступна прямо в Telegram:

```text
/admin
```

Пароль по умолчанию задается переменной:

```text
ADMIN_BOT_PASSWORD=1172
```

После ввода пароля бот показывает статистику и inline-кнопки для просмотра и удаления записей, блокнотов, оценок и заполненных файлов.

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

Открыть Telegram-админку:

```text
/admin
```

Логи локального Telegram Bot API:

```bash
docker logs --tail 120 telegram-bot-api
```

Проверить локальный Telegram API:

```bash
cd /opt/asses
set -a
. ./.env
set +a
curl -sS --max-time 30 "http://127.0.0.1:8081/bot${BOT_TOKEN}/getMe"
echo
```

## Что уже проверено

- Бот успешно стартует на сервере.
- Polling работает.
- `/start` отвечает.
- Локальный Telegram Bot API отвечает на `getMe`.
- Большой MP3-файл около 61 MB успешно принят из Telegram через локальный Bot API.
- SpeechKit async успешно расшифровал запись примерно на 25 минут, транскрипт около 33 000 символов.
- `/assess` успешно сформировал и отправил оценку по расшифрованной записи.
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

### Telegram file is too big

При отправке MP3 около 50-60 MB обычный облачный Telegram Bot API возвращал:

```text
Bad Request: file is too big
```

Причина: публичный `api.telegram.org` не отдаёт боту такие файлы через `getFile`.

Решение:

- получены `api_id` и `api_hash` через `https://my.telegram.org/apps`;
- поднят локальный Telegram Bot API Server;
- aiogram переключен на `TELEGRAM_API_BASE_URL=http://127.0.0.1:8081`;
- бот выведен из облачного API через `logOut`;
- лимит `TELEGRAM_DOWNLOAD_MAX_BYTES` поднят до `2000000000`.

### SSH brute force and port 22222

На сервер массово шли попытки входа по SSH на порт `22`, из-за чего `sshd`
включал `MaxStartups throttling`, а нормальное подключение зависало на `banner exchange`.

Решение:

- добавлен SSH-порт `22222`;
- подключение выполняется командой:

```bash
ssh -p 22222 root@5.42.107.42
```

В дальнейшем лучше закрыть `22`, оставить доступ по ключам и ограничить SSH по IP.

### Local Telegram Bot API Docker NAT

Первый запуск `telegram-bot-api` в Docker bridge network отвечал на `/`, но `getMe`
зависал или контейнер был `unhealthy`. Также при неверном `api_hash` локальный API
возвращал:

```text
Unauthorized: invalid api-id/api-hash
```

Что сделали:

- исправили `api_hash`;
- очистили старые state-директории;
- перезапустили контейнер в `--network host`;
- включили `--http-ip-address=127.0.0.1`;
- проверили `getMe`, он стал отвечать `ok: true`.

### Local Telegram Bot API local file path

После включения `--local` Telegram Bot API возвращал путь вида:

```text
/var/lib/telegram-bot-api/<bot_token>/music/file_0.mp3
```

Но Python-бот работает на хосте, а файл физически лежал в:

```text
/opt/telegram-bot-api/data/
```

Из-за этого был `FileNotFoundError`.

Решение:

```bash
mkdir -p /var/lib
ln -sfn /opt/telegram-bot-api/data /var/lib/telegram-bot-api
```

### Telegram media timeout and retry

Для больших MP3 локальный Telegram Bot API иногда долго готовит файл, поэтому стандартные
timeout aiogram давали:

```text
Request timeout error
ServerDisconnectedError
```

Решение:

- добавлены настройки:
  - `TELEGRAM_FILE_REQUEST_TIMEOUT_SECONDS=900`;
  - `TELEGRAM_FILE_DOWNLOAD_TIMEOUT_SECONDS=900`;
  - `TELEGRAM_FILE_DOWNLOAD_ATTEMPTS=3`;
  - `TELEGRAM_FILE_DOWNLOAD_RETRY_DELAY_SECONDS=15`;
- добавлены retry для `get_file` и `download_file`.

### YandexGPT JSON Schema required fields

YandexGPT structured output отклонял Pydantic JSON Schema:

```text
Invalid JSON Schema: all fields must be required, 'recommendations' is optional
```

Причина: в режиме structured output YandexGPT требует, чтобы все поля объектов были
перечислены в `required`, даже если в Pydantic у них есть default/default_factory.

Решение:

- в `bot/services/yandex_gpt.py` добавлена нормализация JSON Schema;
- все поля объектов рекурсивно добавляются в `required`;
- после этого `/assess` успешно вернул оценку.

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
- Есть простая очередь задач в SQLite и worker внутри процесса бота. Для высокой нагрузки лучше вынести worker в отдельный процесс и добавить Redis/Celery/Arq.
- Формирование индивидуального отчета и ИПР реализовано как `.docx`; PDF-экспорт можно добавить через LibreOffice.
- Локальный Telegram Bot API настроен вручную через Docker run. Лучше вынести его в systemd unit или docker compose.
- Docker container `telegram-bot-api` может отображаться как `unhealthy`, хотя HTTP API работает. Healthcheck образа нужно заменить или отключить.
- `api_hash` был засвечен в переписке во время настройки. Для продакшена лучше перевыпустить данные приложения Telegram, если это возможно.

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

Также нужны материалы ассессмент-центра под реальные упражнения:

- Excel-блокноты наблюдателя по каждому упражнению;
- инструкции участников;
- инструкции наблюдателей;
- инструкции ведущего;
- финальные шаблоны индивидуального отчета и ИПР;
- утвержденная шкала компетенций и список индикаторов.

## Возможные следующие доработки

- Перевести `telegram-bot-api` в docker compose или systemd unit с документированным запуском.
- Закрыть SSH-порт `22`, оставить `22222`, настроить вход по SSH-ключу и запретить password-login для root.
- Автоматическая конвертация WAV/M4A/MP4 через ffmpeg.
- PDF-экспорт отчетов через LibreOffice.
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

## Текущее состояние на 31.05.2026

Рабочий статус:

- бот развернут на Timeweb и запущен через `systemd`;
- локальный Telegram Bot API Server поднят в Docker через `--network host`;
- большие MP3 из Telegram проходят через локальный Bot API;
- проверен файл около 61 MB / 25 минут;
- SpeechKit async успешно распознал запись;
- YandexGPT успешно сформировал оценку после исправления JSON Schema;
- бот отправил результат оценки в Telegram.

Текущий основной технический риск:

- очередь задач уже отделила длинную обработку от Telegram handler, но worker пока работает внутри того же процесса, что и polling. Для нескольких одновременных больших записей лучше вынести worker в отдельный процесс и добавить управление конкурентностью.

Ближайшие рекомендуемые шаги:

- стабилизировать инфраструктуру: docker compose/systemd для `telegram-bot-api`, SSH-ключи, закрыть порт `22`;
- добавить ffmpeg-конвертацию популярных аудио/видео форматов;
- вынести worker в отдельный процесс и добавить управление несколькими задачами;
- протестировать реальные блокноты наблюдателя заказчика;
- доработать DOCX/PDF отчет и ИПР по финальным шаблонам заказчика.
