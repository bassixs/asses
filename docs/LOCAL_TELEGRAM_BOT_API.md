# Локальный Telegram Bot API Server

## Зачем это нужно

Обычный облачный Telegram Bot API не отдает боту большие файлы через `getFile`.
Пользователь может отправить файл в Telegram, но бот не сможет скачать его и получит
ошибку `file is too big`.

Чтобы принимать интервью на 50 МБ и больше прямо через Telegram, на сервере нужно
поднять локальный Telegram Bot API Server и переключить aiogram на него.

## Что нужно подготовить

На странице `https://my.telegram.org/apps` нужны:

- `api_id`;
- `api_hash`.

Эти данные можно взять с любого Telegram-аккаунта. Они не обязаны быть с номера,
на котором создан бот.

## Настройка через Docker

На сервере установите Docker:

```bash
apt update
apt install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Создайте директорию для данных:

```bash
mkdir -p /opt/telegram-bot-api/data /opt/telegram-bot-api/temp
```

Запустите локальный Bot API Server. Вместо значений в угловых скобках подставьте
свои `api_id` и `api_hash`.

Рабочий вариант на сервере Timeweb — `--network host`. В bridge network контейнер
может отвечать на HTTP, но зависать на `getMe`/MTProto-подключении к Telegram.

```bash
docker run -d \
  --name telegram-bot-api \
  --restart unless-stopped \
  --network host \
  -v /opt/telegram-bot-api/data:/var/lib/telegram-bot-api \
  -v /opt/telegram-bot-api/temp:/tmp/telegram-bot-api \
  ghcr.io/bots-house/docker-telegram-bot-api:latest \
  --api-id=<API_ID> \
  --api-hash=<API_HASH> \
  --local \
  --http-ip-address=127.0.0.1 \
  --http-port=8081 \
  --dir=/var/lib/telegram-bot-api \
  --temp-dir=/tmp/telegram-bot-api \
  --verbosity=3
```

Проверьте, что контейнер работает:

```bash
docker ps
docker logs --tail 80 telegram-bot-api
```

Поскольку `--local` возвращает путь `/var/lib/telegram-bot-api/...`, а бот работает
на хосте, нужно открыть этот путь на хосте:

```bash
mkdir -p /var/lib
ln -sfn /opt/telegram-bot-api/data /var/lib/telegram-bot-api
```

Проверьте локальный API:

```bash
cd /opt/asses
set -a
. ./.env
set +a
curl -sS --max-time 30 "https://api.telegram.org/bot${BOT_TOKEN}/logOut"
echo
curl -sS --max-time 120 "http://127.0.0.1:8081/bot${BOT_TOKEN}/getMe"
echo
```

## Переключение бота

В `/opt/asses/.env` добавьте или измените строки:

```bash
TELEGRAM_API_BASE_URL=http://127.0.0.1:8081
TELEGRAM_API_IS_LOCAL=true
TELEGRAM_DOWNLOAD_MAX_BYTES=2000000000
TELEGRAM_FILE_REQUEST_TIMEOUT_SECONDS=900
TELEGRAM_FILE_DOWNLOAD_TIMEOUT_SECONDS=900
TELEGRAM_FILE_DOWNLOAD_ATTEMPTS=3
TELEGRAM_FILE_DOWNLOAD_RETRY_DELAY_SECONDS=15
```

Перезапустите бота:

```bash
cd /opt/asses
git pull
systemctl restart asses-bot
journalctl -u asses-bot -n 80 --no-pager
```

После этого пользователь может отправлять большие аудиофайлы в Telegram, бот
скачает их через локальный Bot API Server и дальше отправит в SpeechKit async
через Object Storage.
