"""
Основной модуль парсинга YouTube.
Использует yt-dlp для извлечения данных о видео, каналах и плейлистах.
"""

import re
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urlparse, parse_qs

import yt_dlp

from .models import (
    VideoInfo, ChannelInfo, ScraperOptions, TaskType,
    SortOrder, VideoType, DateFilter
)

# Настройка логирования
logger = logging.getLogger(__name__)


class YouTubeScraper:
    """
    Основной класс для парсинга данных с YouTube.
    Использует yt-dlp для извлечения метаданных.
    """

    def __init__(self, options: ScraperOptions):
        """
        Инициализация парсера.

        Args:
            options: Опции парсинга
        """
        self.options = options
        self._setup_yt_dlp()

    def _setup_yt_dlp(self):
        """Настройка параметров yt-dlp"""
        self.yt_dlp_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'ignoreerrors': True,  # Продолжать при ошибках
            'no_color': True,

            # Не скачиваем видео, только метаданные
            'skip_download': True,

            # Получаем субтитры если нужно
            'writesubtitles': self.options.get_subtitles,
            'writeautomaticsub': self.options.get_subtitles,
            'subtitleslangs': self.options.subtitle_languages if self.options.get_subtitles else [],

            # Ограничения
            'playlistend': self.options.max_results,
        }

        # Добавляем фильтр по датам если указан
        if self.options.date_filter:
            if self.options.date_filter.date_from:
                self.yt_dlp_opts['dateafter'] = self.options.date_filter.date_from.strftime('%Y%m%d')
            if self.options.date_filter.date_to:
                self.yt_dlp_opts['datebefore'] = self.options.date_filter.date_to.strftime('%Y%m%d')

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        """
        Извлекает ID видео из URL.

        Args:
            url: URL видео YouTube

        Returns:
            ID видео или None
        """
        # Поддерживаемые форматы URL
        patterns = [
            r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
            r'(?:embed/|shorts/)([a-zA-Z0-9_-]{11})',
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    @staticmethod
    def extract_channel_id(url: str) -> Optional[str]:
        """
        Извлекает ID канала из URL.

        Args:
            url: URL канала YouTube

        Returns:
            ID канала или None
        """
        patterns = [
            r'(?:channel/|c/)([a-zA-Z0-9_-]+)',
            r'@([a-zA-Z0-9_-]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    @staticmethod
    def extract_playlist_id(url: str) -> Optional[str]:
        """
        Извлекает ID плейлиста из URL.

        Args:
            url: URL плейлиста YouTube

        Returns:
            ID плейлиста или None
        """
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        return query.get('list', [None])[0]

    @staticmethod
    def detect_input_type(input_data: str) -> TaskType:
        """
        Определяет тип входных данных (видео, канал, плейлист или поиск).

        Args:
            input_data: URL или поисковый запрос

        Returns:
            Тип задачи
        """
        # Проверяем, является ли это URL
        if not input_data.startswith(('http://', 'https://', 'www.')):
            return TaskType.SEARCH

        # Определяем тип по URL
        if '/playlist' in input_data or 'list=' in input_data:
            return TaskType.PLAYLIST
        elif '/channel/' in input_data or '/c/' in input_data or '/@' in input_data:
            return TaskType.CHANNEL
        elif '/watch' in input_data or 'youtu.be/' in input_data or '/shorts/' in input_data:
            return TaskType.VIDEO
        else:
            return TaskType.SEARCH

    def _parse_video_info(self, info: Dict[str, Any]) -> VideoInfo:
        """
        Преобразует данные yt-dlp в модель VideoInfo.

        Args:
            info: Словарь с данными от yt-dlp

        Returns:
            Объект VideoInfo
        """
        # Парсим дату загрузки
        upload_date = None
        if info.get('upload_date'):
            try:
                upload_date = datetime.strptime(info['upload_date'], '%Y%m%d')
            except (ValueError, TypeError):
                pass

        # Определяем тип видео
        duration = info.get('duration', 0) or 0
        is_short = duration <= 60 and '/shorts/' in info.get('webpage_url', '')
        is_live = info.get('is_live', False) or info.get('was_live', False)

        return VideoInfo(
            video_id=info.get('id', ''),
            title=info.get('title', 'Без названия'),
            description=info.get('description'),
            url=info.get('webpage_url', f"https://www.youtube.com/watch?v={info.get('id', '')}"),
            duration=duration,
            view_count=info.get('view_count'),
            like_count=info.get('like_count'),
            comment_count=info.get('comment_count'),
            upload_date=upload_date,
            thumbnail_url=info.get('thumbnail'),
            tags=info.get('tags', []) or [],
            categories=info.get('categories', []) or [],
            is_live=is_live,
            is_short=is_short,
            age_restricted=info.get('age_limit', 0) > 0,
            language=info.get('language'),
        )

    def _parse_channel_info(self, info: Dict[str, Any]) -> ChannelInfo:
        """
        Преобразует данные yt-dlp в модель ChannelInfo.

        Args:
            info: Словарь с данными от yt-dlp

        Returns:
            Объект ChannelInfo
        """
        channel_id = info.get('channel_id', info.get('uploader_id', ''))
        channel_name = info.get('channel', info.get('uploader', 'Неизвестный канал'))

        # Формируем URL канала
        channel_url = info.get('channel_url', info.get('uploader_url', ''))
        if not channel_url and channel_id:
            channel_url = f"https://www.youtube.com/channel/{channel_id}"

        return ChannelInfo(
            channel_id=channel_id,
            channel_name=channel_name,
            channel_url=channel_url,
            subscriber_count=info.get('channel_follower_count'),
            video_count=None,  # Требует дополнительного запроса
            view_count=None,   # Требует дополнительного запроса
            description=info.get('channel_description'),
            thumbnail_url=info.get('channel_thumbnail'),
            created_date=None,
            country=None,
            custom_url=info.get('channel_url'),
        )

    def _filter_by_video_type(self, info: Dict[str, Any]) -> bool:
        """
        Проверяет, соответствует ли видео фильтру по типу.

        Args:
            info: Данные видео

        Returns:
            True если видео соответствует фильтру
        """
        if self.options.video_type == VideoType.ALL:
            return True

        duration = info.get('duration', 0) or 0
        is_short = duration <= 60 and '/shorts/' in info.get('webpage_url', '')
        is_live = info.get('is_live', False) or info.get('was_live', False)

        if self.options.video_type == VideoType.SHORT:
            return is_short
        elif self.options.video_type == VideoType.LIVE:
            return is_live
        elif self.options.video_type == VideoType.VIDEO:
            return not is_short and not is_live

        return True

    def _filter_by_date(self, info: Dict[str, Any]) -> bool:
        """
        Проверяет, соответствует ли видео фильтру по датам.

        Args:
            info: Данные видео

        Returns:
            True если видео соответствует фильтру
        """
        if not self.options.date_filter:
            return True

        upload_date_str = info.get('upload_date')
        if not upload_date_str:
            return True  # Пропускаем если нет даты

        try:
            upload_date = datetime.strptime(upload_date_str, '%Y%m%d')

            if self.options.date_filter.date_from:
                if upload_date < self.options.date_filter.date_from:
                    return False

            if self.options.date_filter.date_to:
                if upload_date > self.options.date_filter.date_to:
                    return False

        except (ValueError, TypeError):
            return True

        return True

    async def scrape_video(self, url: str) -> Tuple[Optional[VideoInfo], Optional[ChannelInfo], Dict[str, Any]]:
        """
        Парсит данные одного видео.

        Args:
            url: URL видео

        Returns:
            Кортеж (VideoInfo, ChannelInfo, raw_data)
        """
        try:
            with yt_dlp.YoutubeDL(self.yt_dlp_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                if not info:
                    logger.warning(f"Не удалось получить данные для: {url}")
                    return None, None, {}

                video_info = self._parse_video_info(info)
                channel_info = self._parse_channel_info(info) if self.options.get_channel_info else None

                return video_info, channel_info, info

        except Exception as e:
            logger.error(f"Ошибка при парсинге видео {url}: {e}")
            return None, None, {}

    async def scrape_channel(self, url: str) -> List[Tuple[VideoInfo, ChannelInfo, Dict[str, Any]]]:
        """
        Парсит все видео с канала.

        Args:
            url: URL канала

        Returns:
            Список кортежей (VideoInfo, ChannelInfo, raw_data)
        """
        results = []

        # Добавляем /videos к URL канала если нужно
        if not url.endswith('/videos'):
            if url.endswith('/'):
                url = url + 'videos'
            else:
                url = url + '/videos'

        try:
            # Настраиваем для извлечения плейлиста
            opts = self.yt_dlp_opts.copy()
            opts['extract_flat'] = 'in_playlist'

            with yt_dlp.YoutubeDL(opts) as ydl:
                playlist_info = ydl.extract_info(url, download=False)

                if not playlist_info or 'entries' not in playlist_info:
                    logger.warning(f"Не удалось получить видео с канала: {url}")
                    return results

                # Получаем информацию о канале
                channel_info = ChannelInfo(
                    channel_id=playlist_info.get('channel_id', playlist_info.get('id', '')),
                    channel_name=playlist_info.get('channel', playlist_info.get('uploader', 'Неизвестный канал')),
                    channel_url=playlist_info.get('channel_url', url),
                    subscriber_count=playlist_info.get('channel_follower_count'),
                    video_count=len(playlist_info.get('entries', [])),
                    view_count=None,
                    description=playlist_info.get('description'),
                    thumbnail_url=playlist_info.get('thumbnail'),
                )

                # Парсим каждое видео
                entries = list(playlist_info.get('entries', []))[:self.options.max_results]

                for entry in entries:
                    if not entry:
                        continue

                    video_url = entry.get('url', f"https://www.youtube.com/watch?v={entry.get('id', '')}")

                    # Получаем полные данные видео
                    video_info, _, raw_data = await self.scrape_video(video_url)

                    if video_info:
                        # Применяем фильтры
                        if self._filter_by_video_type(raw_data) and self._filter_by_date(raw_data):
                            results.append((video_info, channel_info, raw_data))

        except Exception as e:
            logger.error(f"Ошибка при парсинге канала {url}: {e}")

        return results

    async def scrape_playlist(self, url: str) -> List[Tuple[VideoInfo, ChannelInfo, Dict[str, Any]]]:
        """
        Парсит все видео из плейлиста.

        Args:
            url: URL плейлиста

        Returns:
            Список кортежей (VideoInfo, ChannelInfo, raw_data)
        """
        results = []

        try:
            opts = self.yt_dlp_opts.copy()
            opts['extract_flat'] = 'in_playlist'

            with yt_dlp.YoutubeDL(opts) as ydl:
                playlist_info = ydl.extract_info(url, download=False)

                if not playlist_info or 'entries' not in playlist_info:
                    logger.warning(f"Не удалось получить плейлист: {url}")
                    return results

                entries = list(playlist_info.get('entries', []))[:self.options.max_results]

                for entry in entries:
                    if not entry:
                        continue

                    video_url = entry.get('url', f"https://www.youtube.com/watch?v={entry.get('id', '')}")
                    video_info, channel_info, raw_data = await self.scrape_video(video_url)

                    if video_info:
                        if self._filter_by_video_type(raw_data) and self._filter_by_date(raw_data):
                            results.append((video_info, channel_info, raw_data))

        except Exception as e:
            logger.error(f"Ошибка при парсинге плейлиста {url}: {e}")

        return results

    async def search_videos(self, query: str) -> List[Tuple[VideoInfo, ChannelInfo, Dict[str, Any]]]:
        """
        Поиск видео по ключевым словам.

        Args:
            query: Поисковый запрос

        Returns:
            Список кортежей (VideoInfo, ChannelInfo, raw_data)
        """
        results = []

        # Формируем URL поиска
        search_url = f"ytsearch{self.options.max_results}:{query}"

        try:
            opts = self.yt_dlp_opts.copy()

            # Настраиваем сортировку для поиска
            sort_mapping = {
                SortOrder.RELEVANCE: '',
                SortOrder.DATE_DESC: '',  # По умолчанию
                SortOrder.DATE_ASC: '',
                SortOrder.VIEWS: '',
                SortOrder.RATING: '',
            }

            with yt_dlp.YoutubeDL(opts) as ydl:
                search_results = ydl.extract_info(search_url, download=False)

                if not search_results or 'entries' not in search_results:
                    logger.warning(f"Не удалось найти видео по запросу: {query}")
                    return results

                for entry in search_results.get('entries', []):
                    if not entry:
                        continue

                    video_info = self._parse_video_info(entry)
                    channel_info = self._parse_channel_info(entry) if self.options.get_channel_info else None

                    # Применяем фильтры
                    if self._filter_by_video_type(entry) and self._filter_by_date(entry):
                        results.append((video_info, channel_info, entry))

        except Exception as e:
            logger.error(f"Ошибка при поиске '{query}': {e}")

        # Сортируем результаты
        results = self._sort_results(results)

        return results

    def _sort_results(
        self,
        results: List[Tuple[VideoInfo, ChannelInfo, Dict[str, Any]]]
    ) -> List[Tuple[VideoInfo, ChannelInfo, Dict[str, Any]]]:
        """
        Сортирует результаты согласно опциям.

        Args:
            results: Список результатов

        Returns:
            Отсортированный список
        """
        if not results:
            return results

        if self.options.sort_order == SortOrder.DATE_DESC:
            results.sort(
                key=lambda x: x[0].upload_date or datetime.min,
                reverse=True
            )
        elif self.options.sort_order == SortOrder.DATE_ASC:
            results.sort(
                key=lambda x: x[0].upload_date or datetime.min,
                reverse=False
            )
        elif self.options.sort_order == SortOrder.VIEWS:
            results.sort(
                key=lambda x: x[0].view_count or 0,
                reverse=True
            )

        return results

    async def get_channel_details(self, channel_url: str) -> Optional[ChannelInfo]:
        """
        Получает детальную информацию о канале.

        Args:
            channel_url: URL канала

        Returns:
            ChannelInfo или None
        """
        try:
            # Добавляем /about для получения полной информации
            about_url = channel_url.rstrip('/') + '/about'

            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                info = ydl.extract_info(about_url, download=False)

                if not info:
                    return None

                return ChannelInfo(
                    channel_id=info.get('channel_id', info.get('id', '')),
                    channel_name=info.get('channel', info.get('uploader', '')),
                    channel_url=info.get('channel_url', channel_url),
                    subscriber_count=info.get('channel_follower_count'),
                    video_count=info.get('playlist_count'),
                    view_count=None,
                    description=info.get('description'),
                    thumbnail_url=info.get('thumbnail'),
                    created_date=None,
                    country=info.get('location'),
                    custom_url=info.get('channel_url'),
                )

        except Exception as e:
            logger.error(f"Ошибка при получении данных канала {channel_url}: {e}")
            return None


def create_scraper(options: ScraperOptions) -> YouTubeScraper:
    """
    Фабричная функция для создания парсера.

    Args:
        options: Опции парсинга

    Returns:
        Экземпляр YouTubeScraper
    """
    return YouTubeScraper(options)
