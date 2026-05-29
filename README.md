# CherryX Creator Studio

CherryX Creator Studio is a web workspace for creators: video tools, covers, subtitles, publication packages, resumes, design canvas, background jobs, and billing-aware storage.

## Возможности

- Подписка через Telegram Stars: `100 XTR` на 30 дней.
- Бесплатные пользователи через `FREE_USER_IDS` в `.env`.
- Изображения: PNG, JPG, WEBP, PDF, BMP, TIFF, GIF.
- Видео: MP4, WEBM, GIF через FFmpeg из пакета `imageio-ffmpeg`.
- YouTube-ссылка -> до 15 вертикальных Shorts-клипов в MP4.
- Face-focus для интервью и talking-head видео: вертикальный crop старается держать лицо в кадре.
- Подсказки и команды на русском, украинском и английском.
- Переименование результата до конвертации.
- Кнопка “Поделиться”.
- Django web workspace with account, billing, jobs, designer, and video editor pages.
- SQLite для пользователей, подписок и истории конвертаций.
- Лимиты размера и TTL сессий файлов.

## Запуск

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m src.bot
```

Или:

```powershell
.\run_bot.ps1
```

Mini App / сайт:

```powershell
.\run_web.ps1
```

Локальный адрес сайта: `http://127.0.0.1:8000`

## Настройки `.env`

```env
BOT_TOKEN=...
SUBSCRIPTION_STARS=100
SUBSCRIPTION_DAYS=30
FREE_USER_IDS=8314765522
MAX_IMAGE_MB=25
MAX_VIDEO_MB=80
VIDEO_TIMEOUT_SECONDS=180
SESSION_TTL_MINUTES=60
MINI_APP_URL=
YOUTUBE_MAX_DURATION_MINUTES=360
YOUTUBE_MAX_SHORTS=15
YOUTUBE_SHORT_SECONDS=45
YOUTUBE_DOWNLOAD_TIMEOUT_SECONDS=3600
YOUTUBE_WORKERS=1
SHORTS_FOCUS_MODE=face
FACE_DETECTION_ENABLED=true
YOUTUBE_BACKSTAGE_ENABLED=true
BACKSTAGE_SAMPLE_LIMIT=420
BACKSTAGE_MIN_GAP_SECONDS=90
```

Чтобы добавить бесплатного пользователя:

1. Пользователь отправляет боту `/id`.
2. Его ID добавляется в `FREE_USER_IDS` через запятую.
3. Бот перезапускается.

Для Telegram Mini App нужен публичный HTTPS URL. Можно использовать ngrok/cloudflared, затем указать адрес в `MINI_APP_URL` и перезапустить бота.

## Команды

- `/start` - главное меню
- `/subscribe` - счет Telegram Stars
- `/status` - статус доступа
- `/id` - показать Telegram ID
- `/help` - помощь

## YouTube Shorts

Отправь боту ссылку вида `https://youtu.be/...` или `https://www.youtube.com/watch?v=...`.

Бот:

- сначала покажет этапы обработки и примерные оценки по времени;
- скачает видео через `yt-dlp`;
- проверит лимит длительности;
- сделает до `YOUTUBE_MAX_SHORTS` вертикальных клипов;
- если ролик короткий, нарежет подряд;
- если ролик длинный, возьмет равномерные фрагменты по всей длине;
- если в кадре есть лицо, попробует построить вертикальный crop вокруг него;
- в режиме “Preview” ищет более живые фрагменты по движению, лицам, паузам и интонационным всплескам;
- отправит ZIP, а если архив слишком большой, отправит клипы отдельно.

Субтитры пока не вшиваются. Используй только свои ролики или видео, на обработку которых у тебя есть права.
