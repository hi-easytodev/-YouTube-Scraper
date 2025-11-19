"""
Модели данных для YouTube Scraper.
Содержит Pydantic модели для валидации входных данных и структурирования результатов.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime


# === ПЕРЕЧИСЛЕНИЯ (ENUMS) ===

class TaskType(str, Enum):
    """Тип задачи парсинга"""
    VIDEO = "video"           # Одиночное видео
    CHANNEL = "channel"       # Канал целиком
    PLAYLIST = "playlist"     # Плейлист
    SEARCH = "search"         # Поиск по ключевым словам


class TaskStatus(str, Enum):
    """Статус выполнения задачи"""
    PENDING = "pending"       # В очереди
    PROCESSING = "processing" # Выполняется
    COMPLETED = "completed"   # Завершено
    FAILED = "failed"         # Ошибка


class SortOrder(str, Enum):
    """Порядок сортировки результатов"""
    DATE_DESC = "date_desc"   # Новые первыми
    DATE_ASC = "date_asc"     # Старые первыми
    VIEWS = "views"           # По просмотрам
    RATING = "rating"         # По рейтингу
    RELEVANCE = "relevance"   # По релевантности (для поиска)


class VideoType(str, Enum):
    """Тип видео для фильтрации"""
    ALL = "all"               # Все типы
    VIDEO = "video"           # Обычные видео
    SHORT = "short"           # Shorts (вертикальные)
    LIVE = "live"             # Прямые эфиры


class SubtitleFormat(str, Enum):
    """Формат субтитров"""
    SRT = "srt"               # SubRip формат
    TEXT = "text"             # Чистый текст
    JSON = "json"             # JSON с таймкодами


class ExportFormat(str, Enum):
    """Формат экспорта данных"""
    JSON = "json"
    CSV = "csv"


# === МОДЕЛИ ВХОДНЫХ ДАННЫХ ===

class DateFilter(BaseModel):
    """Фильтр по датам публикации"""
    date_from: Optional[datetime] = Field(None, description="Начальная дата (включительно)")
    date_to: Optional[datetime] = Field(None, description="Конечная дата (включительно)")


class ScraperOptions(BaseModel):
    """Опции парсинга - что именно собирать"""
    # Основные данные
    get_video_info: bool = Field(True, description="Собирать информацию о видео")
    get_channel_info: bool = Field(True, description="Собирать информацию о канале")

    # Субтитры
    get_subtitles: bool = Field(False, description="Собирать субтитры")
    subtitle_languages: List[str] = Field(["ru", "en"], description="Языки субтитров")
    subtitle_format: SubtitleFormat = Field(SubtitleFormat.TEXT, description="Формат субтитров")
    prefer_manual_subtitles: bool = Field(True, description="Предпочитать ручные субтитры автоматическим")

    # Комментарии
    get_comments: bool = Field(False, description="Собирать комментарии")
    max_comments: int = Field(100, description="Максимальное количество комментариев", ge=0, le=10000)
    get_replies: bool = Field(False, description="Собирать ответы на комментарии")

    # Фильтрация и сортировка
    date_filter: Optional[DateFilter] = Field(None, description="Фильтр по датам")
    sort_order: SortOrder = Field(SortOrder.DATE_DESC, description="Порядок сортировки")
    video_type: VideoType = Field(VideoType.ALL, description="Тип видео для фильтрации")

    # Лимиты
    max_results: int = Field(50, description="Максимальное количество результатов", ge=1, le=500)


class TaskRequest(BaseModel):
    """Запрос на создание задачи парсинга"""
    task_type: TaskType = Field(..., description="Тип задачи")
    input_data: str = Field(..., description="URL или поисковый запрос")
    options: ScraperOptions = Field(default_factory=ScraperOptions, description="Опции парсинга")

    class Config:
        json_schema_extra = {
            "example": {
                "task_type": "video",
                "input_data": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "options": {
                    "get_subtitles": True,
                    "get_comments": True,
                    "max_comments": 50
                }
            }
        }


class BulkTaskRequest(BaseModel):
    """Массовый запрос на создание задач"""
    tasks: List[TaskRequest] = Field(..., description="Список задач", min_length=1, max_length=100)


# === МОДЕЛИ ВЫХОДНЫХ ДАННЫХ ===

class ChannelInfo(BaseModel):
    """Информация о канале YouTube"""
    channel_id: str = Field(..., description="ID канала")
    channel_name: str = Field(..., description="Название канала")
    channel_url: str = Field(..., description="URL канала")
    subscriber_count: Optional[int] = Field(None, description="Количество подписчиков")
    video_count: Optional[int] = Field(None, description="Количество видео")
    view_count: Optional[int] = Field(None, description="Общее количество просмотров")
    description: Optional[str] = Field(None, description="Описание канала")
    thumbnail_url: Optional[str] = Field(None, description="URL аватара канала")
    created_date: Optional[datetime] = Field(None, description="Дата создания канала")
    country: Optional[str] = Field(None, description="Страна канала")
    custom_url: Optional[str] = Field(None, description="Пользовательский URL канала")


class SubtitleSegment(BaseModel):
    """Сегмент субтитров с таймкодом"""
    start: float = Field(..., description="Время начала в секундах")
    duration: float = Field(..., description="Длительность в секундах")
    text: str = Field(..., description="Текст субтитра")


class SubtitleData(BaseModel):
    """Данные субтитров видео"""
    language: str = Field(..., description="Код языка")
    language_name: str = Field(..., description="Название языка")
    is_auto_generated: bool = Field(..., description="Автоматически сгенерированы")
    format: SubtitleFormat = Field(..., description="Формат субтитров")

    # Контент в зависимости от формата
    content: str = Field(..., description="Контент субтитров (текст или SRT)")
    segments: Optional[List[SubtitleSegment]] = Field(None, description="Сегменты с таймкодами (для JSON)")


class CommentAuthor(BaseModel):
    """Автор комментария"""
    author_name: str = Field(..., description="Имя автора")
    author_channel_id: Optional[str] = Field(None, description="ID канала автора")
    author_channel_url: Optional[str] = Field(None, description="URL канала автора")
    author_avatar_url: Optional[str] = Field(None, description="URL аватара автора")


class Comment(BaseModel):
    """Комментарий к видео"""
    comment_id: str = Field(..., description="ID комментария")
    text: str = Field(..., description="Текст комментария")
    author: CommentAuthor = Field(..., description="Автор комментария")
    like_count: int = Field(0, description="Количество лайков")
    published_at: Optional[datetime] = Field(None, description="Дата публикации")
    updated_at: Optional[datetime] = Field(None, description="Дата обновления")
    is_reply: bool = Field(False, description="Является ответом на другой комментарий")
    parent_id: Optional[str] = Field(None, description="ID родительского комментария")
    reply_count: int = Field(0, description="Количество ответов")
    replies: List["Comment"] = Field(default_factory=list, description="Ответы на комментарий")


class VideoInfo(BaseModel):
    """Полная информация о видео"""
    video_id: str = Field(..., description="ID видео")
    title: str = Field(..., description="Название видео")
    description: Optional[str] = Field(None, description="Описание видео")
    url: str = Field(..., description="URL видео")

    # Метаданные
    duration: Optional[int] = Field(None, description="Длительность в секундах")
    view_count: Optional[int] = Field(None, description="Количество просмотров")
    like_count: Optional[int] = Field(None, description="Количество лайков")
    comment_count: Optional[int] = Field(None, description="Количество комментариев")

    # Даты
    upload_date: Optional[datetime] = Field(None, description="Дата публикации")

    # Медиа
    thumbnail_url: Optional[str] = Field(None, description="URL миниатюры")
    tags: List[str] = Field(default_factory=list, description="Теги видео")
    categories: List[str] = Field(default_factory=list, description="Категории видео")

    # Тип контента
    is_live: bool = Field(False, description="Прямой эфир")
    is_short: bool = Field(False, description="YouTube Short")

    # Дополнительные данные
    age_restricted: bool = Field(False, description="Возрастные ограничения")
    language: Optional[str] = Field(None, description="Язык видео")


class ScrapedData(BaseModel):
    """Полные данные парсинга одного видео"""
    video: VideoInfo = Field(..., description="Информация о видео")
    channel: Optional[ChannelInfo] = Field(None, description="Информация о канале")
    subtitles: List[SubtitleData] = Field(default_factory=list, description="Субтитры")
    comments: List[Comment] = Field(default_factory=list, description="Комментарии")

    # Метаданные парсинга
    scraped_at: datetime = Field(default_factory=datetime.utcnow, description="Время парсинга")


class TaskResult(BaseModel):
    """Результат выполнения задачи"""
    task_id: str = Field(..., description="ID задачи")
    status: TaskStatus = Field(..., description="Статус задачи")
    task_type: TaskType = Field(..., description="Тип задачи")
    input_data: str = Field(..., description="Входные данные")

    # Результаты
    data: List[ScrapedData] = Field(default_factory=list, description="Собранные данные")
    total_items: int = Field(0, description="Общее количество элементов")

    # Временные метки
    created_at: datetime = Field(..., description="Время создания задачи")
    started_at: Optional[datetime] = Field(None, description="Время начала выполнения")
    completed_at: Optional[datetime] = Field(None, description="Время завершения")

    # Ошибки
    errors: List[str] = Field(default_factory=list, description="Список ошибок")
    warnings: List[str] = Field(default_factory=list, description="Список предупреждений")

    # Прогресс
    progress: float = Field(0.0, description="Прогресс выполнения (0-100)")


class TaskInfo(BaseModel):
    """Краткая информация о задаче (для списка)"""
    task_id: str = Field(..., description="ID задачи")
    status: TaskStatus = Field(..., description="Статус задачи")
    task_type: TaskType = Field(..., description="Тип задачи")
    input_data: str = Field(..., description="Входные данные")
    created_at: datetime = Field(..., description="Время создания")
    progress: float = Field(0.0, description="Прогресс выполнения")
    total_items: int = Field(0, description="Количество собранных элементов")


class ExportRequest(BaseModel):
    """Запрос на экспорт данных"""
    task_id: str = Field(..., description="ID задачи для экспорта")
    format: ExportFormat = Field(ExportFormat.JSON, description="Формат экспорта")
    include_subtitles: bool = Field(True, description="Включить субтитры")
    include_comments: bool = Field(True, description="Включить комментарии")


class APIResponse(BaseModel):
    """Стандартный ответ API"""
    success: bool = Field(..., description="Успешность операции")
    message: str = Field(..., description="Сообщение")
    data: Optional[Any] = Field(None, description="Данные ответа")


class HealthCheck(BaseModel):
    """Проверка состояния сервиса"""
    status: str = Field(..., description="Статус сервиса")
    version: str = Field(..., description="Версия API")
    active_tasks: int = Field(..., description="Активных задач")
    pending_tasks: int = Field(..., description="Задач в очереди")


# Обновляем forward reference для вложенных ответов
Comment.model_rebuild()
