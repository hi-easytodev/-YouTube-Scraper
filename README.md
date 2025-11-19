# YouTube Scraper API

Полнофункциональный парсер данных YouTube с REST API. Аналог [Apify YouTube Scraper](https://apify.com/streamers/youtube-scraper), но полностью бесплатный и open source.

## Возможности

- **Массовый сбор данных** - видео, каналы, плейлисты, поиск по ключевым словам
- **Метаданные видео** - название, описание, теги, лайки, просмотры, дата публикации
- **Данные каналов** - подписчики, количество видео, общие просмотры
- **Субтитры** - автоматические и ручные в форматах SRT, текст, JSON
- **Комментарии** - основные и ответы с поддержкой большого количества
- **Фильтрация** - по датам, типу контента (видео, shorts, стримы), сортировка
- **Экспорт** - JSON и CSV для загрузки в базы данных
- **REST API** - полная совместимость с n8n и другими инструментами автоматизации
- **Асинхронная обработка** - очередь задач, защита от ошибок YouTube

## Быстрый старт

### Запуск через Docker (рекомендуется)

```bash
# Клонируйте репозиторий
git clone <repository-url>
cd youtube-scraper

# Запустите через Docker Compose
docker-compose up -d

# API доступен на http://localhost:8000
# Документация: http://localhost:8000/docs
```

### Локальный запуск

```bash
# Установите зависимости
pip install -r requirements.txt

# Запустите сервер
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## API Эндпоинты

### Основные операции

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| POST | `/tasks` | Создать задачу парсинга |
| POST | `/tasks/bulk` | Создать несколько задач |
| GET | `/tasks/{id}` | Получить результат задачи |
| GET | `/tasks/{id}/status` | Получить статус задачи |
| GET | `/tasks` | Список всех задач |
| DELETE | `/tasks/{id}` | Удалить задачу |

### Экспорт данных

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/tasks/{id}/export?format=json` | Экспорт в JSON |
| GET | `/tasks/{id}/export?format=csv` | Экспорт в CSV |
| GET | `/tasks/{id}/export/comments` | Экспорт комментариев |
| GET | `/tasks/{id}/export/subtitles` | Экспорт субтитров |

### Быстрые запросы (для n8n)

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| POST | `/scrape/video?url=...` | Быстрый парсинг видео |
| POST | `/scrape/search?query=...` | Быстрый поиск |

## Примеры использования

### 1. Парсинг одного видео

```bash
curl -X POST "http://localhost:8000/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "video",
    "input_data": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "options": {
      "get_subtitles": true,
      "subtitle_languages": ["ru", "en"],
      "get_comments": true,
      "max_comments": 100
    }
  }'
```

**Ответ:**
```json
{
  "success": true,
  "message": "Задача создана и добавлена в очередь",
  "data": {
    "task_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

### 2. Парсинг канала

```bash
curl -X POST "http://localhost:8000/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "channel",
    "input_data": "https://www.youtube.com/@channelname",
    "options": {
      "max_results": 50,
      "get_subtitles": false,
      "video_type": "video",
      "sort_order": "date_desc"
    }
  }'
```

### 3. Поиск по ключевым словам

```bash
curl -X POST "http://localhost:8000/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "search",
    "input_data": "python tutorial 2024",
    "options": {
      "max_results": 20,
      "date_filter": {
        "date_from": "2024-01-01T00:00:00"
      }
    }
  }'
```

### 4. Парсинг плейлиста

```bash
curl -X POST "http://localhost:8000/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "playlist",
    "input_data": "https://www.youtube.com/playlist?list=PLxxxxxxxx",
    "options": {
      "max_results": 100,
      "get_comments": true,
      "max_comments": 50
    }
  }'
```

### 5. Получение результатов

```bash
# Проверка статуса
curl "http://localhost:8000/tasks/{task_id}/status"

# Получение полных данных
curl "http://localhost:8000/tasks/{task_id}"

# Экспорт в CSV
curl "http://localhost:8000/tasks/{task_id}/export?format=csv" -o data.csv
```

### 6. Массовый парсинг

```bash
curl -X POST "http://localhost:8000/tasks/bulk" \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": [
      {
        "task_type": "video",
        "input_data": "https://youtube.com/watch?v=video1"
      },
      {
        "task_type": "video",
        "input_data": "https://youtube.com/watch?v=video2"
      }
    ]
  }'
```

## Интеграция с n8n

### HTTP Request Node

1. Создайте HTTP Request узел
2. Метод: POST
3. URL: `http://your-server:8000/scrape/video`
4. Query Parameters:
   - `url`: URL видео
   - `get_subtitles`: true/false
   - `get_comments`: true/false

### Workflow пример

```
[Trigger] → [HTTP Request: Create Task] → [Wait] → [HTTP Request: Get Result] → [Process Data]
```

### Получение результата в n8n

```javascript
// В Function узле после получения task_id
const taskId = $json.data.task_id;

// Проверяйте статус каждые 5 секунд
// GET http://localhost:8000/tasks/{taskId}/status

// Когда status = "completed":
// GET http://localhost:8000/tasks/{taskId}/export?format=json
```

## Структура данных

### Результат парсинга (ScrapedData)

```json
{
  "video": {
    "video_id": "dQw4w9WgXcQ",
    "title": "Название видео",
    "description": "Описание...",
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "duration": 212,
    "view_count": 1000000,
    "like_count": 50000,
    "comment_count": 10000,
    "upload_date": "2023-01-15T00:00:00",
    "thumbnail_url": "https://...",
    "tags": ["tag1", "tag2"],
    "categories": ["Music"],
    "is_live": false,
    "is_short": false
  },
  "channel": {
    "channel_id": "UCxxxxxx",
    "channel_name": "Channel Name",
    "channel_url": "https://www.youtube.com/channel/UCxxxxxx",
    "subscriber_count": 1000000,
    "video_count": 500
  },
  "subtitles": [
    {
      "language": "ru",
      "language_name": "Русский",
      "is_auto_generated": false,
      "format": "text",
      "content": "Текст субтитров..."
    }
  ],
  "comments": [
    {
      "comment_id": "xxx",
      "text": "Отличное видео!",
      "author": {
        "author_name": "User Name",
        "author_channel_id": "UCyyy"
      },
      "like_count": 100,
      "published_at": "2023-01-16T12:00:00",
      "replies": []
    }
  ],
  "scraped_at": "2024-01-20T10:30:00"
}
```

## Опции парсинга

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `get_video_info` | bool | true | Собирать информацию о видео |
| `get_channel_info` | bool | true | Собирать информацию о канале |
| `get_subtitles` | bool | false | Собирать субтитры |
| `subtitle_languages` | array | ["ru", "en"] | Языки субтитров |
| `subtitle_format` | string | "text" | Формат: srt, text, json |
| `prefer_manual_subtitles` | bool | true | Предпочитать ручные субтитры |
| `get_comments` | bool | false | Собирать комментарии |
| `max_comments` | int | 100 | Максимум комментариев |
| `get_replies` | bool | false | Собирать ответы на комментарии |
| `max_results` | int | 50 | Максимум результатов |
| `sort_order` | string | "date_desc" | Сортировка: date_desc, date_asc, views, rating |
| `video_type` | string | "all" | Тип: all, video, short, live |
| `date_filter` | object | null | Фильтр по датам |

## Статусы задач

| Статус | Описание |
|--------|----------|
| `pending` | Задача в очереди |
| `processing` | Выполняется |
| `completed` | Завершено успешно |
| `failed` | Ошибка выполнения |

## Форматы субтитров

### SRT
```
1
00:00:00,000 --> 00:00:05,000
Первый субтитр

2
00:00:05,000 --> 00:00:10,000
Второй субтитр
```

### Text
```
Первый субтитр Второй субтитр
```

### JSON
```json
{
  "segments": [
    {"start": 0.0, "duration": 5.0, "text": "Первый субтитр"},
    {"start": 5.0, "duration": 5.0, "text": "Второй субтитр"}
  ]
}
```

## Обработка ошибок

API защищён от типичных ошибок YouTube:
- Капча - пропуск видео с предупреждением
- Приватные видео - пропуск с ошибкой
- Отсутствие субтитров - пустой список
- Отключённые комментарии - пустой список
- Лимиты YouTube - автоматические задержки

Все ошибки логируются и возвращаются в поле `errors` результата.

## Используемые библиотеки

- **FastAPI** - веб-фреймворк
- **yt-dlp** - парсинг YouTube
- **youtube-transcript-api** - получение субтитров
- **pandas** - обработка данных
- **pydantic** - валидация данных

Все библиотеки бесплатные и open source.

## Структура проекта

```
youtube-scraper/
├── app/
│   ├── __init__.py       # Версия и метаданные
│   ├── main.py           # FastAPI приложение
│   ├── models.py         # Pydantic модели
│   ├── scraper.py        # Основной парсер
│   ├── subtitles.py      # Работа с субтитрами
│   ├── comments.py       # Сбор комментариев
│   ├── tasks.py          # Очередь задач
│   └── exporters.py      # Экспорт данных
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Производительность

- **3 параллельных воркера** по умолчанию
- **Асинхронная обработка** всех операций
- **Кэширование** данных yt-dlp
- **Очередь задач** без блокировки API

Для увеличения производительности измените `max_concurrent_tasks` в `app/tasks.py`.

## Ограничения

- YouTube может ограничивать количество запросов
- Комментарии собираются через API, возможны лимиты
- Субтитры доступны не для всех видео
- Приватные и удалённые видео недоступны

## Лицензия

MIT License

## Поддержка

При возникновении проблем создайте Issue в репозитории.
