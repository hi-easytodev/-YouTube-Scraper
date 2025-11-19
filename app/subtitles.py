"""
Модуль для получения и обработки субтитров YouTube.
Использует youtube-transcript-api для извлечения субтитров.
"""

import logging
from typing import List, Optional
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.formatters import SRTFormatter, TextFormatter

from .models import SubtitleData, SubtitleSegment, SubtitleFormat

# Настройка логирования
logger = logging.getLogger(__name__)

# Словарь названий языков
LANGUAGE_NAMES = {
    'ru': 'Русский',
    'en': 'English',
    'es': 'Español',
    'de': 'Deutsch',
    'fr': 'Français',
    'it': 'Italiano',
    'pt': 'Português',
    'ja': '日本語',
    'ko': '한국어',
    'zh': '中文',
    'ar': 'العربية',
    'hi': 'हिन्दी',
    'uk': 'Українська',
    'pl': 'Polski',
    'nl': 'Nederlands',
    'tr': 'Türkçe',
}


class SubtitleScraper:
    """
    Класс для получения субтитров с видео YouTube.
    """

    def __init__(
        self,
        languages: List[str] = None,
        format: SubtitleFormat = SubtitleFormat.TEXT,
        prefer_manual: bool = True
    ):
        """
        Инициализация парсера субтитров.

        Args:
            languages: Список кодов языков для получения субтитров
            format: Формат вывода субтитров
            prefer_manual: Предпочитать ручные субтитры автоматическим
        """
        self.languages = languages or ['ru', 'en']
        self.format = format
        self.prefer_manual = prefer_manual

    def get_available_transcripts(self, video_id: str) -> List[dict]:
        """
        Получает список доступных субтитров для видео.

        Args:
            video_id: ID видео YouTube

        Returns:
            Список словарей с информацией о доступных субтитрах
        """
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            available = []

            for transcript in transcript_list:
                available.append({
                    'language': transcript.language,
                    'language_code': transcript.language_code,
                    'is_generated': transcript.is_generated,
                    'is_translatable': transcript.is_translatable,
                })

            return available

        except TranscriptsDisabled:
            logger.warning(f"Субтитры отключены для видео {video_id}")
            return []
        except NoTranscriptFound:
            logger.warning(f"Субтитры не найдены для видео {video_id}")
            return []
        except Exception as e:
            logger.error(f"Ошибка при получении списка субтитров для {video_id}: {e}")
            return []

    async def get_subtitles(self, video_id: str) -> List[SubtitleData]:
        """
        Получает субтитры для видео в указанных языках.

        Args:
            video_id: ID видео YouTube

        Returns:
            Список SubtitleData для каждого языка
        """
        results = []

        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            for lang_code in self.languages:
                try:
                    # Пытаемся найти субтитры на нужном языке
                    transcript = None

                    if self.prefer_manual:
                        # Сначала ищем ручные субтитры
                        try:
                            transcript = transcript_list.find_manually_created_transcript([lang_code])
                        except NoTranscriptFound:
                            # Если ручных нет, ищем автоматические
                            try:
                                transcript = transcript_list.find_generated_transcript([lang_code])
                            except NoTranscriptFound:
                                pass
                    else:
                        # Ищем любые субтитры
                        try:
                            transcript = transcript_list.find_transcript([lang_code])
                        except NoTranscriptFound:
                            pass

                    if not transcript:
                        # Пробуем перевести с другого языка
                        try:
                            # Берём первые доступные субтитры
                            for available_transcript in transcript_list:
                                if available_transcript.is_translatable:
                                    transcript = available_transcript.translate(lang_code)
                                    break
                        except Exception:
                            continue

                    if transcript:
                        # Получаем данные субтитров
                        transcript_data = transcript.fetch()
                        subtitle_result = self._format_subtitles(
                            transcript_data,
                            lang_code,
                            transcript.language,
                            transcript.is_generated
                        )
                        results.append(subtitle_result)

                except Exception as e:
                    logger.warning(f"Не удалось получить субтитры на языке {lang_code} для {video_id}: {e}")
                    continue

        except TranscriptsDisabled:
            logger.warning(f"Субтитры отключены для видео {video_id}")
        except NoTranscriptFound:
            logger.warning(f"Субтитры не найдены для видео {video_id}")
        except Exception as e:
            logger.error(f"Ошибка при получении субтитров для {video_id}: {e}")

        return results

    def _format_subtitles(
        self,
        transcript_data: List[dict],
        language_code: str,
        language_name: str,
        is_auto_generated: bool
    ) -> SubtitleData:
        """
        Форматирует субтитры в нужный формат.

        Args:
            transcript_data: Сырые данные субтитров
            language_code: Код языка
            language_name: Название языка
            is_auto_generated: Автоматически сгенерированы

        Returns:
            SubtitleData с отформатированным контентом
        """
        # Получаем локализованное название языка
        display_name = LANGUAGE_NAMES.get(language_code, language_name)

        if self.format == SubtitleFormat.SRT:
            formatter = SRTFormatter()
            content = formatter.format_transcript(transcript_data)
            segments = None

        elif self.format == SubtitleFormat.TEXT:
            formatter = TextFormatter()
            content = formatter.format_transcript(transcript_data)
            segments = None

        elif self.format == SubtitleFormat.JSON:
            # Для JSON формата создаём сегменты с таймкодами
            segments = [
                SubtitleSegment(
                    start=item['start'],
                    duration=item.get('duration', 0),
                    text=item['text']
                )
                for item in transcript_data
            ]
            # Также сохраняем как текст для удобства
            content = ' '.join(item['text'] for item in transcript_data)

        else:
            content = ' '.join(item['text'] for item in transcript_data)
            segments = None

        return SubtitleData(
            language=language_code,
            language_name=display_name,
            is_auto_generated=is_auto_generated,
            format=self.format,
            content=content,
            segments=segments
        )

    def _seconds_to_srt_time(self, seconds: float) -> str:
        """
        Конвертирует секунды в формат времени SRT (HH:MM:SS,mmm).

        Args:
            seconds: Время в секундах

        Returns:
            Строка времени в формате SRT
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)

        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


async def get_video_subtitles(
    video_id: str,
    languages: List[str] = None,
    format: SubtitleFormat = SubtitleFormat.TEXT,
    prefer_manual: bool = True
) -> List[SubtitleData]:
    """
    Удобная функция для получения субтитров видео.

    Args:
        video_id: ID видео YouTube
        languages: Список языков
        format: Формат субтитров
        prefer_manual: Предпочитать ручные субтитры

    Returns:
        Список SubtitleData
    """
    scraper = SubtitleScraper(
        languages=languages,
        format=format,
        prefer_manual=prefer_manual
    )
    return await scraper.get_subtitles(video_id)


def extract_video_id_from_url(url: str) -> Optional[str]:
    """
    Извлекает ID видео из URL.

    Args:
        url: URL видео YouTube

    Returns:
        ID видео или None
    """
    import re

    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/|shorts/)([a-zA-Z0-9_-]{11})',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None
