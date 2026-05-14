# song-search-bot

Telegram-бот на **aiogram 3.x**, который ищет песни по названию, исполнителю
или строчке из текста (lyrics) и присылает полный трек в формате `.mp4`.

Поиск выполняется через `yt-dlp` (`ytsearch`), скачивание — тоже через
`yt-dlp` с ремуксом контейнера в `mp4` (FFmpeg).

## Возможности

- `/start` и `/help` — короткая инструкция.
- Принимает любой текстовый запрос и возвращает 5–10 наиболее релевантных
  вариантов inline-кнопками (название — исполнитель — длительность).
- По клику на вариант — скачивает трек и шлёт `.mp4` в чат.
- Промежуточные статусы: «Ищу…», «Скачиваю…».
- Понятные сообщения об ошибках: ничего не найдено, трек слишком длинный,
  файл превышает лимит Telegram, истёк срок выбора, неизвестная ошибка.
- In-memory кэш результатов поиска с TTL + кэш скачанных файлов по `video_id`
  в каталоге `DOWNLOADS_DIR`.
- HTML-разметка сообщений с premium custom emoji через `<tg-emoji>` (для
  пользователей без Premium отображается unicode-фолбэк).

## Почему aiogram 3.x

| Критерий | aiogram 3.x | python-telegram-bot 21.x |
|---|---|---|
| Async-native | да, без обёрток | да (через ApplicationBuilder) |
| Filters / роутеры | компактный `F`-DSL | классы `filters.X` |
| Decorator-based DI | да, через `dp.start_polling(... key=value)` | через `application.bot_data` |
| HTML parse_mode по умолчанию | `DefaultBotProperties(parse_mode=...)` | `defaults=Defaults(parse_mode=...)` |
| Размер зависимости | меньше | больше |

Выбор: **aiogram 3.x**. Лаконичный async-API (`Router`, `F.text`,
`CallbackQuery`), удобные `DefaultBotProperties` для глобального
`parse_mode=HTML`, нативная поддержка inline-клавиатур и FSM. В этом
проекте HTML parse mode критичен для premium custom emoji.

## Структура

```
bot/
  __init__.py
  main.py          # точка входа, запуск polling
  handlers.py      # /start, /help, обработка поиска и callback-выбора
  search.py        # ytsearch через yt-dlp
  downloader.py    # скачивание + remux в mp4, лимиты размера/длительности
  keyboards.py     # inline-клавиатура с результатами + кнопка «Назад»
  config.py        # загрузка переменных окружения
.env.example
requirements.txt
README.md
```

## Требования

- **Python 3.11+**
- **FFmpeg** в `$PATH` (нужен `yt-dlp` для ремукса в `mp4`)
- Токен Telegram-бота от **@BotFather**

### Установка FFmpeg

- Ubuntu / Debian: `sudo apt update && sudo apt install -y ffmpeg`
- macOS (Homebrew): `brew install ffmpeg`
- Windows (winget): `winget install -e --id Gyan.FFmpeg`
- Arch: `sudo pacman -S ffmpeg`

Проверка: `ffmpeg -version`.

## Установка проекта

```bash
git clone https://github.com/kartofelscripts-cell/song-search-bot.git
cd song-search-bot

python3.11 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

## Получение токена бота

1. Открой Telegram и напиши **@BotFather**.
2. Команда `/newbot` → введи имя и username (должен заканчиваться на `bot`).
3. Скопируй выданный токен формата `1234567890:ABC-DEF...`.

## Конфигурация

```bash
cp .env.example .env
```

Открой `.env` и впиши токен. Остальные переменные опциональны:

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `BOT_TOKEN` | Токен бота от @BotFather | — (обязательная) |
| `LOG_LEVEL` | Уровень логирования | `INFO` |
| `DOWNLOADS_DIR` | Куда складывать скачанные файлы | `./downloads` |
| `MAX_FILE_SIZE_MB` | Лимит размера файла (МБ) | `50` |
| `MAX_DURATION_S` | Лимит длительности трека (сек) | `1800` |
| `SEARCH_LIMIT` | Сколько результатов показывать | `8` |
| `CACHE_TTL_S` | TTL in-memory кэша результатов поиска (сек) | `1800` |

> Telegram Bot API позволяет отправлять файлы до **50 МБ** через публичный
> API. Если развернёшь [локальный Bot API сервер](https://core.telegram.org/bots/api#using-a-local-bot-api-server),
> лимит поднимается до **2000 МБ** — тогда увеличь `MAX_FILE_SIZE_MB`.

## Запуск

```bash
python -m bot.main
```

В логах ты увидишь старт polling. Открой бота в Telegram, нажми
`/start`, отправь название песни.

## Команды

- `/start` — приветствие и краткая инструкция.
- `/help` — подробная инструкция и информация о лимитах.
- Любое другое текстовое сообщение трактуется как поисковый запрос.

## Ограничения и лимиты

- **Размер файла:** 50 МБ (Bot API) / 2 ГБ (локальный Bot API).
- **Длительность:** по умолчанию ≤ 30 мин (`MAX_DURATION_S=1800`).
- **Качество видео:** ≤ 480p (для соответствия лимиту 50 МБ).
- **Источник:** YouTube (через `yt-dlp`). Поиск по lyrics работает за
  счёт того, что YT индексирует субтитры и описания треков. Для более
  точного lyrics-матчинга можно подменить реализацию в `bot/search.py`
  на `ytmusicapi`.

## Кэширование

Скачанные файлы остаются в `DOWNLOADS_DIR` под именем `<video_id>.mp4`.
При повторном выборе того же трека (например, после рестарта) файл
не качается заново. Чтобы освободить место — просто удали каталог
`downloads/`.

## Структура callback_data

Чтобы не упереться в 64-байтный лимит Telegram, callback_data — короткая:
- `pick:<search_id>:<index>` — выбор трека из текущего поиска,
- `cancel:<search_id>` — отмена.

`search_id` — короткий случайный токен (`secrets.token_urlsafe(6)`). Список
результатов хранится в RAM с TTL `CACHE_TTL_S`. По истечении бот ответит
«Истёк срок выбора».

## Разработка

```bash
# Синтаксическая проверка
python -m compileall bot

# Запуск с DEBUG-логированием
LOG_LEVEL=DEBUG python -m bot.main
```

## Лицензия

Без указанной лицензии. Используй на свой страх и риск, соблюдай условия
сервисов, с которых качаешь контент.
