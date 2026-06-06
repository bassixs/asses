# Prompt для следующей модели

Скопируй этот prompt в новый чат/модель, чтобы она быстро поняла контекст проекта.

```text
Ты подключаешься к проекту HR Assessment Telegram Bot.

Рабочая директория проекта: E:\work\proj\asse
Репозиторий: https://github.com/bassixs/asses.git
Основной бот: @assessment40_bot
Актуальный сервер: 85.239.35.73
Путь на сервере: /opt/asses
systemd service: asses-bot
Локальный Telegram Bot API: http://127.0.0.1:8081, Docker container telegram-bot-api

Сначала прочитай эти файлы:

- docs/PROJECT_OVERVIEW.md
- docs/BOT_USAGE_SIMPLE.md
- docs/LOCAL_TELEGRAM_BOT_API.md
- bot/config.py
- bot/services/media_jobs.py
- bot/services/role_labeling.py
- bot/services/assessment.py
- bot/services/observer_notebook.py
- bot/handlers/media.py
- bot/handlers/workflow.py
- bot/handlers/assessment.py
- bot/handlers/notebook.py
- bot/models/record.py

Что делает проект:

Telegram-бот для HR-ассессмента и ассессмент-центра. Пользователь отправляет аудио упражнения, бот расшифровывает, размечает роли, оценивает компетенции/индикаторы, заполняет Excel-блокнот наблюдателя, формирует DOCX отчет и ИПР.

Текущий pipeline:

1. Пользователь отправляет аудио/voice/document.
2. bot/handlers/media.py создает MediaProcessingJob.
3. Пользователь выбирает STT: AI Tunnel Whisper, Yandex или NeuroAPI Whisper.
4. bot/services/media_jobs.py скачивает файл через локальный Telegram Bot API.
5. Выбранный STT возвращает сырой текст.
6. Сырой текст сохраняется в InterviewRecord.raw_transcript.
7. bot/services/role_labeling.py размечает роли "Ведущий" / "Участник".
8. Размеченный текст сохраняется в InterviewRecord.transcript.
9. bot/services/transcript_export.py создает txt-файл расшифровки.
10. /assess и notebook-анализ используют только реплики "Участник:" через extract_participant_transcript().

Очень важное правило ролей:

- "Участник" = оцениваемый человек, чьи компетенции проверяются.
- "Ведущий" = все остальные: ассессор, наблюдатель, интервьюер, ролевой сотрудник, клиент, подчиненный, ассистент.

Нельзя считать участником того, кто просто много говорит, отвечает от первого лица или жалуется на ситуацию. В ролевом упражнении ролевой сотрудник часто говорит от первого лица, но он не оцениваемый.

После команды /attach_record <exercise_id> <record_id> бот знает имя оцениваемого участника и запускает повторную разметку ролей от raw_transcript. Это сделано в bot/handlers/workflow.py.

Ключевые текущие настройки .env на сервере:

- TELEGRAM_API_BASE_URL=http://127.0.0.1:8081
- TELEGRAM_API_IS_LOCAL=true
- TELEGRAM_DOWNLOAD_MAX_BYTES=2000000000
- AITUNNEL_BASE_URL=https://api.aitunnel.ru/v1
- AITUNNEL_WHISPER_MODEL=whisper-1 или whisper-large-v3-turbo в зависимости от теста
- AITUNNEL_MAX_UPLOAD_BYTES=25000000
- NEUROAPI_BASE_URL=https://neuroapi.host/v1
- NEUROAPI_WHISPER_MODEL=whisper-1
- ROLE_LABELING_PROVIDER=neuroapi
- ROLE_LABELING_MODEL=deepseek-v4-flash
- ANALYSIS_LLM_PROVIDER=neuroapi
- ANALYSIS_LLM_MODEL=deepseek-v4-flash

Не повторяй реальные токены и ключи в ответах. Если ключи были засвечены в переписке, советуй перевыпустить их, но не печатай значения.

Что уже сделано:

- aiogram 3.x async бот.
- SQLAlchemy 2.0 async + Alembic + SQLite.
- Yandex SpeechKit sync/async через Object Storage.
- AI Tunnel Whisper.
- NeuroAPI Whisper.
- OpenAI-compatible LLM JSON completion.
- YandexGPT fallback.
- Очередь MediaProcessingJob для аудио.
- Локальный Telegram Bot API Server для больших файлов.
- ffmpeg-сжатие аудио под лимиты Whisper.
- raw_transcript отдельно от размеченного transcript.
- role labeling с контекстом оцениваемого после /attach_record.
- /assess в фоне через asyncio.create_task.
- /fill_notebook в фоне через asyncio.create_task.
- Excel-блокнот: извлечение индикаторов, заполнение D/E/F, расчет уровней без НЗ.
- DOCX отчет и DOCX ИПР.
- Telegram admin panel по паролю.
- Удаление локальных файлов и Yandex Object Storage prefix через админку.

Что НЕ трогали по просьбе владельца:

- усиление админки;
- обработка ошибок в /process_exercise;
- объединение дублирующих AI Tunnel/NeuroAPI Whisper сервисов;
- чистка старых миграций stt_provider.

Главные проблемы, с которыми столкнулись:

1. Telegram cloud Bot API не отдавал большие MP3 через getFile: "file is too big".
   Решили локальным Telegram Bot API Server в Docker, --network host, --local, endpoint 127.0.0.1:8081.

2. Local Telegram Bot API отдавал путь /var/lib/telegram-bot-api внутри контейнера.
   Решили symlink:
   mkdir -p /var/lib
   ln -sfn /opt/telegram-bot-api/data /var/lib/telegram-bot-api

3. Старый сервер 5.42.107.42 плохо ходил во внешние API и имел проблемы SSH/сетей.
   Перешли на сервер 85.239.35.73.

4. Yandex SpeechKit давал слабую расшифровку и роли.
   Добавили AI Tunnel/NeuroAPI Whisper и LLM role labeling.

5. Модель путала оцениваемого с ролевым сотрудником.
   Добавили raw_transcript, контекст участника после /attach_record, строгий role labeling prompt, фильтр только строк "Участник:" для анализа.

6. AI Tunnel имеет лимит 25MB.
   Добавили ffmpeg-сжатие, но полноценную нарезку на чанки еще не сделали.

Что сейчас не хватает:

1. Самый важный следующий шаг: реализовать нарезку длинного аудио на чанки для AI Tunnel Whisper.
   Нужно резать через ffmpeg, добавить overlap, отправлять части в STT, склеивать transcript.

2. Персистентная очередь для LLM-задач.
   /assess и /fill_notebook сейчас запускаются в фоне через asyncio.create_task, но не переживают restart процесса.

3. /process_exercise все еще синхронный и без нормального try/except, но владелец просил пока не трогать.

4. DOCX отчет и ИПР пока приблизительные, не идеально повторяют шаблоны заказчика.

5. PDF-export пока не реализован.

6. Админка пока слабая: один общий пароль, нет ADMIN_USER_IDS и TTL.

Как обновлять сервер после изменений:

cd /opt/asses
git pull
python -m alembic upgrade head
systemctl restart asses-bot
journalctl -u asses-bot -n 80 --no-pager

Как смотреть логи:

journalctl -u asses-bot -f

Стиль работы:

- Пользователь хочет практичные ответы и команды по шагам.
- Пиши по-русски.
- Не распечатывай секреты.
- Если делаешь код, сначала читай существующие файлы и придерживайся текущего стиля.
- Для ручных правок используй apply_patch.
- После изменений запускай:
  python -m compileall bot alembic
  git diff --check

Если нужно выбрать следующий technical task, предложи:

"Добавить chunking длинного аудио для AI Tunnel Whisper, потому что это главный блокер качества и стабильности STT на длинных записях."
```
