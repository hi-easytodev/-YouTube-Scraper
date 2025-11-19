"""
Модуль для сбора комментариев с видео YouTube.
Использует yt-dlp для извлечения комментариев.
"""

import logging
from datetime import datetime
from typing import List, Optional
import yt_dlp

from .models import Comment, CommentAuthor

# Настройка логирования
logger = logging.getLogger(__name__)


class CommentScraper:
    """
    Класс для сбора комментариев с видео YouTube.
    """

    def __init__(
        self,
        max_comments: int = 100,
        get_replies: bool = False
    ):
        """
        Инициализация парсера комментариев.

        Args:
            max_comments: Максимальное количество комментариев для сбора
            get_replies: Собирать ответы на комментарии
        """
        self.max_comments = max_comments
        self.get_replies = get_replies

    async def get_comments(self, video_url: str) -> List[Comment]:
        """
        Получает комментарии к видео.

        Args:
            video_url: URL видео YouTube

        Returns:
            Список комментариев
        """
        comments = []

        # Настройки yt-dlp для получения комментариев
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'getcomments': True,
            'extractor_args': {
                'youtube': {
                    'max_comments': [str(self.max_comments)],
                    'comment_sort': ['top'],  # Сортировка по популярности
                }
            }
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)

                if not info:
                    logger.warning(f"Не удалось получить данные видео: {video_url}")
                    return comments

                raw_comments = info.get('comments', [])

                if not raw_comments:
                    logger.info(f"Комментарии не найдены или отключены для видео: {video_url}")
                    return comments

                # Обрабатываем комментарии
                comments = self._process_comments(raw_comments)

                logger.info(f"Получено {len(comments)} комментариев для {video_url}")

        except Exception as e:
            logger.error(f"Ошибка при получении комментариев для {video_url}: {e}")

        return comments

    def _process_comments(self, raw_comments: List[dict]) -> List[Comment]:
        """
        Обрабатывает сырые данные комментариев от yt-dlp.

        Args:
            raw_comments: Список сырых комментариев

        Returns:
            Список обработанных комментариев
        """
        comments = []
        comment_dict = {}  # Для быстрого поиска по ID

        for raw in raw_comments:
            if not raw:
                continue

            comment = self._parse_comment(raw)

            if comment:
                comment_dict[comment.comment_id] = comment

                # Если это не ответ, добавляем в основной список
                if not comment.is_reply:
                    comments.append(comment)

        # Привязываем ответы к родительским комментариям
        if self.get_replies:
            for raw in raw_comments:
                if not raw:
                    continue

                parent_id = raw.get('parent')
                if parent_id and parent_id in comment_dict:
                    comment_id = raw.get('id', '')
                    if comment_id in comment_dict:
                        child_comment = comment_dict[comment_id]
                        comment_dict[parent_id].replies.append(child_comment)

        return comments[:self.max_comments]

    def _parse_comment(self, raw: dict) -> Optional[Comment]:
        """
        Парсит один комментарий из сырых данных.

        Args:
            raw: Словарь с данными комментария

        Returns:
            Объект Comment или None
        """
        try:
            # Парсим дату публикации
            published_at = None
            timestamp = raw.get('timestamp')
            if timestamp:
                try:
                    published_at = datetime.fromtimestamp(timestamp)
                except (ValueError, TypeError, OSError):
                    pass

            # Создаём автора
            author = CommentAuthor(
                author_name=raw.get('author', 'Аноним'),
                author_channel_id=raw.get('author_id'),
                author_channel_url=raw.get('author_url'),
                author_avatar_url=raw.get('author_thumbnail'),
            )

            # Определяем, является ли это ответом
            is_reply = raw.get('parent') is not None

            return Comment(
                comment_id=raw.get('id', ''),
                text=raw.get('text', ''),
                author=author,
                like_count=raw.get('like_count', 0) or 0,
                published_at=published_at,
                updated_at=None,
                is_reply=is_reply,
                parent_id=raw.get('parent'),
                reply_count=0,  # Будет обновлено позже
                replies=[]
            )

        except Exception as e:
            logger.warning(f"Ошибка при парсинге комментария: {e}")
            return None


async def get_video_comments(
    video_url: str,
    max_comments: int = 100,
    get_replies: bool = False
) -> List[Comment]:
    """
    Удобная функция для получения комментариев видео.

    Args:
        video_url: URL видео YouTube
        max_comments: Максимальное количество комментариев
        get_replies: Собирать ответы

    Returns:
        Список комментариев
    """
    scraper = CommentScraper(
        max_comments=max_comments,
        get_replies=get_replies
    )
    return await scraper.get_comments(video_url)


class CommentStats:
    """
    Класс для подсчёта статистики по комментариям.
    """

    @staticmethod
    def calculate_stats(comments: List[Comment]) -> dict:
        """
        Рассчитывает статистику по комментариям.

        Args:
            comments: Список комментариев

        Returns:
            Словарь со статистикой
        """
        if not comments:
            return {
                'total_comments': 0,
                'total_replies': 0,
                'total_likes': 0,
                'avg_likes': 0,
                'most_liked': None,
                'unique_authors': 0,
            }

        total_comments = len(comments)
        total_replies = sum(len(c.replies) for c in comments)
        total_likes = sum(c.like_count for c in comments)

        # Находим самый популярный комментарий
        most_liked = max(comments, key=lambda c: c.like_count)

        # Уникальные авторы
        authors = set(c.author.author_name for c in comments)

        return {
            'total_comments': total_comments,
            'total_replies': total_replies,
            'total_likes': total_likes,
            'avg_likes': total_likes / total_comments if total_comments > 0 else 0,
            'most_liked': {
                'text': most_liked.text[:100] + '...' if len(most_liked.text) > 100 else most_liked.text,
                'likes': most_liked.like_count,
                'author': most_liked.author.author_name,
            },
            'unique_authors': len(authors),
        }
