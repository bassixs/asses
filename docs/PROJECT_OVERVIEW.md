# HR Assessment Telegram Bot

Документ фиксирует состояние проекта на 2026-06-06: что сделано, как работает бот, какие проблемы уже решены и что остается следующим техническим долгом.

## Суть проекта

Проект - Telegram-бот для HR-ассессмента и ассессмент-центра.

Главная цепочка:

```text
аудиозапись упражнения -> STT расшифровка -> разметка ролей -> оценка индикаторов/компетенций -> Excel-блокнот -> DOCX отчет -> DOCX ИПР
```

Бот работает с:

- голосовыми сообщениями Telegram;
- аудиофайлами и аудио-документами;
- Excel-блокнотами наблюдателя `.xlsx`;
- простыми командами ассессмент-центра: центр, участник, упражнение, привязка записи и блокнота;
- отчетами и ИПР в `.docx`.

Репозиторий:

```text
https://github.com/bassixs/asses.git
```

Основной бот:

```text
@assessment40_bot
```

## Текущий стек

```text
Python 3.11+
aiogram 3.x
SQLAlchemy 2.0 async
Alembic
SQLite
Pydantic v2 / pydantic-settings
python-dotenv
aiohttp
boto3
openpyxl
python-docx
ffmpeg
systemd
Docker для локального Telegram Bot API Server
```

Внешние AI/STT провайдеры:

- Yandex SpeechKit, включая async через Yandex Object Storage;
- AI Tunnel Whisper через OpenAI-compatible `/audio/transcriptions`;
- NeuroAPI Whisper через OpenAI-compatible `/audio/transcriptions`;
- YandexGPT как старый/резервный LLM;
- NeuroAPI или AI Tunnel как OpenAI-compatible LLM для анализа и разметки ролей.

## Основные файлы

```text
bot/main.py                         запуск aiogram, middleware БД, media worker
bot/config.py                       настройки .env
bot/database.py                     async SQLAlchemy engine/session
bot/keyboards.py                    inline/reply клавиатуры

bot/models/record.py                InterviewRecord, хранит raw_transcript и transcript
bot/models/job.py                   MediaProcessingJob для очереди медиа
bot/models/notebook.py              ObserverNotebook, NotebookFillResult
bot/models/center.py                AssessmentCenter, Participant, Exercise, отчеты, ИПР
bot/models/assessment.py            AssessmentResult

bot/handlers/media.py               прием аудио, выбор STT, скачивание transcript txt, rebuild transcript
bot/handlers/assessment.py          /assess и /my_assessments
bot/handlers/notebook.py            загрузка и заполнение Excel-блокнота
bot/handlers/workflow.py            workflow ассессмент-центра
bot/handlers/admin.py               простая админка внутри Telegram
bot/handlers/common.py              /start, /criteria

bot/services/media_jobs.py          worker обработки аудио
bot/services/speechkit.py           Yandex SpeechKit sync/async
bot/services/aitunnel_whisper.py    AI Tunnel Whisper
bot/services/neuroapi_whisper.py    NeuroAPI Whisper
bot/services/audio_preprocessing.py подготовка аудио под лимиты Whisper (сжатие + переход к нарезке)
bot/services/audio_chunking.py       нарезка длинного аудио на перекрывающиеся чанки и склейка transcript
bot/services/role_labeling.py       разметка ролей ведущий/участник
bot/services/assessment.py          оценка компетенций
bot/services/observer_notebook.py   анализ и заполнение Excel-блокнота
bot/services/llm_json.py            OpenAI-compatible JSON completion
bot/services/yandex_gpt.py          YandexGPT JSON completion
bot/services/object_storage.py      Yandex Object Storage
bot/services/transcript_export.py   txt-файл расшифровки
bot/services/reports.py             DOCX отчет и ИПР

alembic/versions/                   миграции БД
docs/BOT_USAGE_SIMPLE.md            простая инструкция пользователя
docs/LOCAL_TELEGRAM_BOT_API.md      настройка локального Telegram Bot API
docs/YANDEX_CLOUD_SETUP.md          настройка Yandex Cloud
docs/NEXT_MODEL_PROMPT.md           prompt для следующей модели
```

## Как работает обработка аудио

1. Пользователь отправляет аудио/voice/document.
2. `bot/handlers/media.py` создает `MediaProcessingJob` со статусом `awaiting_provider`.
3. Бот показывает кнопки выбора STT:
   - `AI Tunnel Whisper`;
   - `Yandex`;
   - `NeuroAPI Whisper`.
4. После выбора провайдера задача переходит в `queued`.
5. `bot/services/media_jobs.py` забирает задачу, скачивает файл из Telegram и запускает выбранный STT.
6. Если выбран AI Tunnel или NeuroAPI, перед отправкой файл проходит через `bot/services/audio_preprocessing.py`.
   Для NeuroAPI это сжатие под лимит провайдера (`prepare_audio_for_upload`).
   Для AI Tunnel используется `prepare_audio_chunks_for_upload`: сначала сжатие, а если даже на самом низком
   битрейте файл не влезает в жёсткий лимит 25 MB, `bot/services/audio_chunking.py` режет аудио на
   перекрывающиеся части, каждая часть расшифровывается отдельно, а transcript склеивается с удалением
   дублей на стыках (`merge_chunk_transcripts`). Нарезка нужна только AI Tunnel из-за его лимита на запрос.
7. STT возвращает сырой текст.
8. Сырой текст сохраняется в `InterviewRecord.raw_transcript`.
9. `bot/services/role_labeling.py` размечает роли `Ведущий` / `Участник`.
10. Размеченный текст сохраняется в `InterviewRecord.transcript`.
11. `bot/services/transcript_export.py` создает `.txt` файл расшифровки.
12. Бот присылает сообщение с ID записи и кнопками:
    - оценить компетенции;
    - скачать расшифровку.

Важно: `raw_transcript` нужен, чтобы можно было заново разметить роли без повторного STT и без влияния старых ошибочных меток.

## Разметка ролей

Файл: `bot/services/role_labeling.py`.

Роли всегда приводятся к двум значениям:

- `Ведущий` - ассессор, наблюдатель, интервьюер, ролевой игрок, сотрудник, клиент, любой неоцениваемый человек;
- `Участник` - оцениваемый кандидат/руководитель, чьи компетенции проверяются.

Ключевое правило: модель не должна определять участника по первому лицу, объему речи или имени персонажа. В ролевом упражнении сотрудник может много говорить о проблемах, усталости и возражениях, но он не является оцениваемым участником, если оценивается руководитель.

После `/attach_record <exercise_id> <record_id>` бот знает имя участника из workflow и запускает повторную разметку ролей уже с контекстом:

```text
известный оцениваемый участник
название упражнения
сырой transcript
```

Команда `/rebuild_transcript <record_id>` также пересобирает разметку от `raw_transcript`.

## Как работает оценка компетенций

Файл: `bot/services/assessment.py`.

Команда:

```text
/assess <record_id>
```

Сейчас `/assess` не блокирует Telegram handler: handler быстро отвечает, а LLM-задача запускается в фоне через `asyncio.create_task`. Результат приходит отдельным сообщением.

Перед отправкой в LLM используется `extract_participant_transcript()` из `bot/services/role_labeling.py`: в анализ уходит только текст строк `Участник:`. Это сделано, чтобы модель не оценивала ролевого сотрудника, ведущего или наблюдателя.

Провайдер анализа задается в `.env`:

```env
ANALYSIS_LLM_PROVIDER=neuroapi
ANALYSIS_LLM_MODEL=deepseek-v4-flash
ANALYSIS_LLM_JSON_MODE=false
```

Можно вернуть YandexGPT:

```env
ANALYSIS_LLM_PROVIDER=yandex
```

## Как работает Excel-блокнот наблюдателя

Файл: `bot/services/observer_notebook.py`.

Бот читает `.xlsx` через `openpyxl`.

Ожидаемая структура:

- колонка B - компетенции и уровни;
- колонка C - поведенческие индикаторы;
- колонка D - проявление `+`, `-`, `НЗ`;
- колонка E - комментарии и цитаты;
- колонка F - уровень компетенции.

Команды:

```text
отправить .xlsx файл
/fill_notebook <record_id> <notebook_id>
```

Или в workflow:

```text
/attach_notebook <exercise_id> <notebook_id>
/process_exercise <exercise_id>
```

`/fill_notebook` сейчас запускается в фоне и присылает готовый Excel отдельным сообщением.

Перед анализом индикаторов в LLM также передается только текст оцениваемого участника. Это снижает риск, что цитаты ролевого игрока попадут в evidence.

Расчет уровня:

```text
% = количество плюсов / количество наблюдаемых индикаторов
НЗ исключается из расчета
```

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

## Workflow ассессмент-центра

Основная цепочка:

```text
/create_center <название>
/add_participant <center_id> <ФИО>
/add_exercise <participant_id> <название упражнения>
отправить аудио
выбрать STT
/attach_record <exercise_id> <record_id>
отправить Excel-блокнот
/attach_notebook <exercise_id> <notebook_id>
/process_exercise <exercise_id>
/generate_report <participant_id>
/generate_ipr <participant_id>
```

Отчет и ИПР формируются в `.docx` через `python-docx` в `bot/services/reports.py`.

## Текущее серверное состояние

Актуальный рабочий сервер:

```text
85.239.35.73
```

Проект:

```text
/opt/asses
```

Бот:

```text
systemd service: asses-bot
```

Локальный Telegram Bot API:

```text
Docker container: telegram-bot-api
endpoint: http://127.0.0.1:8081
mode: --local
```

Проверка бота:

```bash
journalctl -u asses-bot -n 80 --no-pager
```

Live logs:

```bash
journalctl -u asses-bot -f
```

Обновление на сервере:

```bash
cd /opt/asses
git pull
python -m alembic upgrade head
systemctl restart asses-bot
journalctl -u asses-bot -n 80 --no-pager
```

## Важные проблемы, которые уже решили

### Telegram file is too big

Обычный `api.telegram.org` не отдавал боту файлы около 50-60 MB через `getFile`.

Решение:

- поднят локальный Telegram Bot API Server;
- aiogram переключен на `TELEGRAM_API_BASE_URL=http://127.0.0.1:8081`;
- бот выведен из облачного Bot API через `logOut`;
- увеличены Telegram timeout/retry.

### Docker bridge зависал на local Bot API

В bridge network `getMe` зависал или контейнер был `unhealthy`.

Решение:

- запуск `telegram-bot-api` через `--network host`;
- `--http-ip-address=127.0.0.1`;
- проверка через локальный `/getMe`.

### Local Bot API отдавал путь внутри контейнера

В режиме `--local` путь был вида:

```text
/var/lib/telegram-bot-api/...
```

А реальные файлы лежали в:

```text
/opt/telegram-bot-api/data
```

Решение:

```bash
mkdir -p /var/lib
ln -sfn /opt/telegram-bot-api/data /var/lib/telegram-bot-api
```

### Старый сервер Timeweb плохо ходил во внешние API

Сервер `5.42.107.42` периодически не мог нормально подключаться к NeuroAPI/AI Tunnel и имел проблемы с SSH/сетями. Работу перенесли на сервер `85.239.35.73`, где AI Tunnel успешно отвечал.

### NeuroAPI Whisper

На новом сервере NeuroAPI стал доступен, но сам провайдер иногда возвращал HTTP 500. Поэтому NeuroAPI Whisper оставлен как тестовая кнопка, а основной путь пока AI Tunnel Whisper.

### AI Tunnel file limit

AI Tunnel Whisper возвращал:

```text
HTTP 413: файл не должен превышать 25MB
```

Добавлено ffmpeg-сжатие перед отправкой. Полной нарезки длинных файлов на чанки пока нет.

### Роли путались между ролевым сотрудником и оцениваемым

Проблема: модель могла считать `Участник` того, кто отвечает от первого лица и жалуется на ситуацию, хотя это ролевой сотрудник, а оцениваемый - руководитель.

Решения:

- усилен prompt в `bot/services/role_labeling.py`;
- добавлен контекст участника после `/attach_record`;
- добавлен `raw_transcript`;
- `/assess` и notebook-анализ используют только строки `Участник:`.

## Что сейчас не хватает

### 1. Нарезка аудио на чанки — сделано

Реализовано в `bot/services/audio_chunking.py` и `prepare_audio_chunks_for_upload`.
Применяется только к AI Tunnel (у него жёсткий лимит 25 MB на запрос); NeuroAPI и Yandex работают как раньше.

- сначала сжатие под лимит (как раньше);
- если не влезает — нарезка через ffmpeg с overlap (`WHISPER_CHUNK_OVERLAP_SECONDS`, по умолчанию 15с);
- длина чанка считается из битрейта и лимита провайдера с запасом (`WHISPER_CHUNK_SIZE_SAFETY`);
- каждая часть расшифровывается отдельно, transcript склеивается с удалением дублей на стыках.

Возможные доработки на будущее: резать по тишине (silencedetect) вместо фиксированного шага;
сохранять метаданные чанков в БД; чистить временные mp3-файлы чанков после обработки.

### 2. Персистентная очередь для LLM-задач

Медиа уже обрабатывается через `MediaProcessingJob`, но `/assess`, `/fill_notebook` и переуточнение ролей после `/attach_record` сейчас запускаются через `asyncio.create_task`.

Это быстрее для handler, но задача не переживет restart процесса.

Нужно:

- добавить отдельную таблицу для LLM/job задач или расширить текущую;
- вынести worker в отдельный процесс или хотя бы общий job worker;
- хранить статусы, ошибки, retry.

### 3. `/process_exercise` все еще синхронный

По просьбе владельца проекта этот пункт пока не трогали. Команда все еще выполняет LLM/Excel прямо в handler.

### 4. Админка слабая

По просьбе владельца проекта пока не трогали.

Текущие ограничения:

- один общий пароль;
- нет `ADMIN_USER_IDS`;
- нет TTL сессии;
- удаление всех данных доступно любому, кто знает пароль.

### 5. Отчеты и ИПР пока шаблонные

DOCX уже генерируется, но это еще не полноценное воспроизведение шаблонов заказчика.

Нужно:

- точнее повторить структуру PDF/DOCX шаблонов заказчика;
- добавить PDF-export через LibreOffice;
- улучшить формулировки рекомендаций на основе методических материалов.

### 6. Критерии и компетенции пока не управляются из интерфейса

Сейчас список компетенций лежит в `bot/config.py`, а индикаторы берутся из Excel-блокнота.

Нужно:

- загрузка/редактирование шкал и критериев;
- хранение версии критериев;
- привязка критериев к упражнению/центру.

### 7. Дублирование Whisper сервисов

`aitunnel_whisper.py` и `neuroapi_whisper.py` почти одинаковые. По просьбе владельца проекта этот пункт пока не трогали.

### 8. Старые миграции `stt_provider`

В истории есть добавление, удаление и повторное добавление `stt_provider`. Это некрасиво, но на работающем сервере лучше не переписывать историю. По просьбе владельца проекта не трогали.

## Актуальный рекомендуемый следующий шаг

Нарезка длинного аудио на чанки для AI Tunnel/NeuroAPI Whisper реализована (см. техдолг п.1).
Следующие полезные шаги:

1. проверить chunking на реальной длинной записи (>100 минут) на сервере, где доступен ffmpeg/ffprobe;
2. стабилизировать LLM queue;
3. улучшить role labeling на тестовых записях;
4. довести Excel notebook до формата заказчика;
5. довести DOCX/PDF отчет и ИПР по шаблонам.
