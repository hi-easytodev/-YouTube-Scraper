"""
Модуль экспорта данных в различные форматы.
Поддерживает JSON и CSV экспорт.
"""

import json
import csv
import io
from typing import List

from .models import ScrapedData, TaskResult, ExportFormat


class DataExporter:
    """
    Класс для экспорта данных парсинга в различные форматы.
    """

    @staticmethod
    def export_to_json(
        data: List[ScrapedData],
        include_subtitles: bool = True,
        include_comments: bool = True,
        pretty: bool = True
    ) -> str:
        """
        Экспортирует данные в JSON формат.

        Args:
            data: Список данных для экспорта
            include_subtitles: Включать субтитры
            include_comments: Включать комментарии
            pretty: Форматировать JSON

        Returns:
            JSON строка
        """
        export_data = []

        for item in data:
            video_dict = item.video.model_dump()
            channel_dict = item.channel.model_dump() if item.channel else None

            # Конвертируем datetime в строки
            if video_dict.get('upload_date'):
                video_dict['upload_date'] = video_dict['upload_date'].isoformat()

            if channel_dict and channel_dict.get('created_date'):
                channel_dict['created_date'] = channel_dict['created_date'].isoformat()

            record = {
                'video': video_dict,
                'channel': channel_dict,
                'scraped_at': item.scraped_at.isoformat(),
            }

            # Субтитры
            if include_subtitles:
                subtitles = []
                for sub in item.subtitles:
                    sub_dict = sub.model_dump()
                    subtitles.append(sub_dict)
                record['subtitles'] = subtitles
            else:
                record['subtitles'] = []

            # Комментарии
            if include_comments:
                comments = []
                for comment in item.comments:
                    comment_dict = comment.model_dump()
                    # Конвертируем даты
                    if comment_dict.get('published_at'):
                        comment_dict['published_at'] = comment_dict['published_at'].isoformat()
                    if comment_dict.get('updated_at'):
                        comment_dict['updated_at'] = comment_dict['updated_at'].isoformat()

                    # Обрабатываем ответы
                    if comment_dict.get('replies'):
                        for reply in comment_dict['replies']:
                            if reply.get('published_at'):
                                reply['published_at'] = reply['published_at'].isoformat()
                            if reply.get('updated_at'):
                                reply['updated_at'] = reply['updated_at'].isoformat()

                    comments.append(comment_dict)
                record['comments'] = comments
            else:
                record['comments'] = []

            export_data.append(record)

        if pretty:
            return json.dumps(export_data, ensure_ascii=False, indent=2)
        else:
            return json.dumps(export_data, ensure_ascii=False)

    @staticmethod
    def export_to_csv(
        data: List[ScrapedData],
        include_subtitles: bool = True,
        include_comments: bool = True
    ) -> str:
        """
        Экспортирует данные в CSV формат.
        Создаёт плоскую структуру с основными полями.

        Args:
            data: Список данных для экспорта
            include_subtitles: Включать текст субтитров
            include_comments: Включать количество комментариев

        Returns:
            CSV строка
        """
        rows = []

        for item in data:
            video = item.video
            channel = item.channel

            row = {
                # Основные данные видео
                'video_id': video.video_id,
                'title': video.title,
                'description': video.description or '',
                'url': video.url,
                'duration_seconds': video.duration or 0,
                'view_count': video.view_count or 0,
                'like_count': video.like_count or 0,
                'comment_count': video.comment_count or 0,
                'upload_date': video.upload_date.isoformat() if video.upload_date else '',
                'thumbnail_url': video.thumbnail_url or '',
                'tags': ';'.join(video.tags) if video.tags else '',
                'categories': ';'.join(video.categories) if video.categories else '',
                'is_live': video.is_live,
                'is_short': video.is_short,
                'age_restricted': video.age_restricted,
                'language': video.language or '',

                # Данные канала
                'channel_id': channel.channel_id if channel else '',
                'channel_name': channel.channel_name if channel else '',
                'channel_url': channel.channel_url if channel else '',
                'subscriber_count': channel.subscriber_count if channel else 0,
                'channel_video_count': channel.video_count if channel else 0,
                'channel_view_count': channel.view_count if channel else 0,

                # Метаданные
                'scraped_at': item.scraped_at.isoformat(),
            }

            # Добавляем субтитры
            if include_subtitles:
                # Объединяем все субтитры в одно поле
                subtitle_texts = []
                for sub in item.subtitles:
                    lang = sub.language
                    text = sub.content[:1000] if len(sub.content) > 1000 else sub.content
                    subtitle_texts.append(f"[{lang}] {text}")

                row['subtitles_text'] = ' | '.join(subtitle_texts)
                row['subtitles_count'] = len(item.subtitles)
                row['subtitles_languages'] = ';'.join(sub.language for sub in item.subtitles)

            # Добавляем статистику комментариев
            if include_comments:
                row['comments_scraped'] = len(item.comments)
                if item.comments:
                    total_likes = sum(c.like_count for c in item.comments)
                    row['comments_total_likes'] = total_likes

            rows.append(row)

        # Создаём CSV
        if not rows:
            return ''

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

        return output.getvalue()

    @staticmethod
    def export_comments_to_csv(data: List[ScrapedData]) -> str:
        """
        Экспортирует комментарии в отдельный CSV файл.

        Args:
            data: Список данных для экспорта

        Returns:
            CSV строка с комментариями
        """
        rows = []

        for item in data:
            video_id = item.video.video_id
            video_title = item.video.title

            for comment in item.comments:
                row = {
                    'video_id': video_id,
                    'video_title': video_title,
                    'comment_id': comment.comment_id,
                    'text': comment.text,
                    'author_name': comment.author.author_name,
                    'author_channel_id': comment.author.author_channel_id or '',
                    'author_channel_url': comment.author.author_channel_url or '',
                    'like_count': comment.like_count,
                    'published_at': comment.published_at.isoformat() if comment.published_at else '',
                    'is_reply': comment.is_reply,
                    'parent_id': comment.parent_id or '',
                    'reply_count': len(comment.replies),
                }
                rows.append(row)

                # Добавляем ответы
                for reply in comment.replies:
                    reply_row = {
                        'video_id': video_id,
                        'video_title': video_title,
                        'comment_id': reply.comment_id,
                        'text': reply.text,
                        'author_name': reply.author.author_name,
                        'author_channel_id': reply.author.author_channel_id or '',
                        'author_channel_url': reply.author.author_channel_url or '',
                        'like_count': reply.like_count,
                        'published_at': reply.published_at.isoformat() if reply.published_at else '',
                        'is_reply': True,
                        'parent_id': comment.comment_id,
                        'reply_count': 0,
                    }
                    rows.append(reply_row)

        if not rows:
            return ''

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

        return output.getvalue()

    @staticmethod
    def export_subtitles_to_csv(data: List[ScrapedData]) -> str:
        """
        Экспортирует субтитры в отдельный CSV файл.

        Args:
            data: Список данных для экспорта

        Returns:
            CSV строка с субтитрами
        """
        rows = []

        for item in data:
            video_id = item.video.video_id
            video_title = item.video.title

            for subtitle in item.subtitles:
                row = {
                    'video_id': video_id,
                    'video_title': video_title,
                    'language': subtitle.language,
                    'language_name': subtitle.language_name,
                    'is_auto_generated': subtitle.is_auto_generated,
                    'format': subtitle.format.value,
                    'content': subtitle.content,
                }
                rows.append(row)

        if not rows:
            return ''

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

        return output.getvalue()


def export_task_result(
    task_result: TaskResult,
    format: ExportFormat,
    include_subtitles: bool = True,
    include_comments: bool = True
) -> str:
    """
    Экспортирует результат задачи в указанный формат.

    Args:
        task_result: Результат задачи
        format: Формат экспорта
        include_subtitles: Включать субтитры
        include_comments: Включать комментарии

    Returns:
        Строка с данными в указанном формате
    """
    exporter = DataExporter()

    if format == ExportFormat.JSON:
        return exporter.export_to_json(
            task_result.data,
            include_subtitles=include_subtitles,
            include_comments=include_comments
        )
    elif format == ExportFormat.CSV:
        return exporter.export_to_csv(
            task_result.data,
            include_subtitles=include_subtitles,
            include_comments=include_comments
        )
    else:
        raise ValueError(f"Неподдерживаемый формат экспорта: {format}")
