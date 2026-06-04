# Настройка Yandex Cloud для асинхронного SpeechKit

Бот использует два режима SpeechKit:

- короткие файлы Ogg Opus / raw LPCM: синхронный SpeechKit API v1;
- длинные интервью и MP3-файлы: загрузка в Object Storage + асинхронный SpeechKit API v3 с speaker labeling;
- асинхронный SpeechKit API v2 используется как fallback, если v3 вернул ошибку.

Официальная документация:

- Для асинхронного SpeechKit v3 нужен bucket в Object Storage, сервисный аккаунт с ролями `ai.speechkit-stt.user` и `storage.uploader`, а также API-ключ или IAM-токен.
- Доступ к Object Storage из Python выполняется через S3-совместимые статические ключи и endpoint `https://storage.yandexcloud.net`.

## 1. Предварительные требования

Установите и инициализируйте Yandex Cloud CLI:

```powershell
yc init
yc config list
```

Убедитесь, что выбранная folder — это та folder, в которой должны находиться bucket и сервисный аккаунт.

## 2. Создайте сервисный аккаунт, роли, bucket и статический ключ

Запустите вспомогательный скрипт:

```powershell
.\scripts\setup_yandex_cloud.ps1 `
  -FolderId "<folder_id>" `
  -ServiceAccountName "hr-assessment-bot" `
  -BucketName "<globally-unique-bucket-name>"
```

Скрипт выведет значения для `.env`.

Необходимые роли сервисного аккаунта:

- `ai.speechkit-stt.user`
- `ai.languageModels.user`
- `storage.uploader`

Скрипт также выдаёт роль `storage.editor`, чтобы бот мог загружать объекты через S3-совместимые статические ключи. Позже это можно сузить до прав на конкретный bucket, если этого требует ваша модель безопасности.

Скрипт создаёт:

- сервисный аккаунт;
- роли на уровне folder;
- приватный bucket в Object Storage;
- статический ключ доступа к Object Storage;
- API-ключ сервисного аккаунта для SpeechKit и YandexGPT.

## 3. Заполните `.env`

```dotenv
YANDEX_SPEECHKIT_API_KEY=<api_key_secret>
YANDEX_GPT_API_KEY=<api_key_secret>
YANDEX_STORAGE_BUCKET=<bucket_name>
YANDEX_STORAGE_ACCESS_KEY_ID=<static_key_id>
YANDEX_STORAGE_SECRET_ACCESS_KEY=<static_key_secret>
YANDEX_STORAGE_ENDPOINT=https://storage.yandexcloud.net
YANDEX_STORAGE_PREFIX=interviews
```

Важно: API-ключ, который используется для асинхронного распознавания SpeechKit, должен принадлежать сервисному аккаунту. Асинхронное распознавание из Object Storage не предназначено для личных пользовательских аккаунтов.

## 4. Форматы аудио

Основной режим бота — асинхронный SpeechKit API v3. В коде включены контейнеры:

- Ogg Opus: `.ogg`, `.oga`, `.opus`
- MP3: `.mp3`
- WAV: `.wav`

Fallback-режим SpeechKit API v2 поддерживает:

- Ogg Opus: `.ogg`, `.oga`, `.opus`
- MP3: `.mp3`
- raw LPCM: `.pcm`, `.lpcm`, `.raw`

Для `.m4a`, `.aac`, `.mp4`, `.docx`, `.pdf` нужно добавить отдельный шаг конвертации или извлечения аудио перед распознаванием.
