"""
Система управления задачами парсинга.
Реализует асинхронную очередь задач с поддержкой параллельного выполнения.
"""

import asyncio
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

from .models import (
    TaskRequest, TaskResult, TaskStatus, TaskType, TaskInfo,
    ScrapedData, ScraperOptions
)
from .scraper import YouTubeScraper
from .subtitles import get_video_subtitles, extract_video_id_from_url
from .comments import get_video_comments

# Настройка логирования
logger = logging.getLogger(__name__)


class TaskManager:
    """
    Менеджер задач парсинга.
    Управляет очередью задач и их выполнением.
    """

    def __init__(self, max_concurrent_tasks: int = 3):
        """
        Инициализация менеджера задач.

        Args:
            max_concurrent_tasks: Максимальное количество одновременных задач
        """
        self.max_concurrent_tasks = max_concurrent_tasks
        self.tasks: Dict[str, TaskResult] = {}
        self.queue: asyncio.Queue = asyncio.Queue()
        self.active_tasks: int = 0
        self._workers: List[asyncio.Task] = []
        self._running = False

    async def start(self):
        """Запускает воркеры для обработки задач"""
        if self._running:
            return

        self._running = True

        # Создаём воркеры
        for i in range(self.max_concurrent_tasks):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self._workers.append(worker)

        logger.info(f"Запущено {self.max_concurrent_tasks} воркеров для обработки задач")

    async def stop(self):
        """Останавливает все воркеры"""
        self._running = False

        # Отменяем все воркеры
        for worker in self._workers:
            worker.cancel()

        # Ждём завершения
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []

        logger.info("Все воркеры остановлены")

    async def _worker(self, name: str):
        """
        Воркер для обработки задач из очереди.

        Args:
            name: Имя воркера для логирования
        """
        logger.info(f"Воркер {name} запущен")

        while self._running:
            try:
                # Получаем задачу из очереди с таймаутом
                try:
                    task_id = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                if task_id not in self.tasks:
                    continue

                self.active_tasks += 1

                try:
                    logger.info(f"Воркер {name} начал выполнение задачи {task_id}")
                    await self._execute_task(task_id)
                    logger.info(f"Воркер {name} завершил задачу {task_id}")
                except Exception as e:
                    logger.error(f"Ошибка в воркере {name} при выполнении задачи {task_id}: {e}")
                    self.tasks[task_id].status = TaskStatus.FAILED
                    self.tasks[task_id].errors.append(str(e))
                finally:
                    self.active_tasks -= 1
                    self.queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Критическая ошибка в воркере {name}: {e}")

        logger.info(f"Воркер {name} остановлен")

    def create_task(self, request: TaskRequest) -> str:
        """
        Создаёт новую задачу и добавляет её в очередь.

        Args:
            request: Запрос на создание задачи

        Returns:
            ID созданной задачи
        """
        task_id = str(uuid.uuid4())

        # Создаём результат задачи
        task_result = TaskResult(
            task_id=task_id,
            status=TaskStatus.PENDING,
            task_type=request.task_type,
            input_data=request.input_data,
            created_at=datetime.utcnow(),
        )

        # Сохраняем дополнительные данные в задаче
        task_result._options = request.options

        self.tasks[task_id] = task_result

        # Добавляем в очередь
        self.queue.put_nowait(task_id)

        logger.info(f"Создана задача {task_id}: {request.task_type.value} - {request.input_data}")

        return task_id

    async def _execute_task(self, task_id: str):
        """
        Выполняет задачу парсинга.

        Args:
            task_id: ID задачи
        """
        task = self.tasks[task_id]
        task.status = TaskStatus.PROCESSING
        task.started_at = datetime.utcnow()

        options: ScraperOptions = task._options
        scraper = YouTubeScraper(options)

        try:
            results = []

            # Выполняем парсинг в зависимости от типа задачи
            if task.task_type == TaskType.VIDEO:
                results = await self._scrape_single_video(
                    scraper, task.input_data, options, task
                )

            elif task.task_type == TaskType.CHANNEL:
                results = await self._scrape_channel(
                    scraper, task.input_data, options, task
                )

            elif task.task_type == TaskType.PLAYLIST:
                results = await self._scrape_playlist(
                    scraper, task.input_data, options, task
                )

            elif task.task_type == TaskType.SEARCH:
                results = await self._scrape_search(
                    scraper, task.input_data, options, task
                )

            task.data = results
            task.total_items = len(results)
            task.status = TaskStatus.COMPLETED
            task.progress = 100.0

        except Exception as e:
            logger.error(f"Ошибка при выполнении задачи {task_id}: {e}")
            task.status = TaskStatus.FAILED
            task.errors.append(f"Ошибка выполнения: {str(e)}")

        finally:
            task.completed_at = datetime.utcnow()

    async def _scrape_single_video(
        self,
        scraper: YouTubeScraper,
        url: str,
        options: ScraperOptions,
        task: TaskResult
    ) -> List[ScrapedData]:
        """
        Парсит одно видео с субтитрами и комментариями.

        Args:
            scraper: Экземпляр парсера
            url: URL видео
            options: Опции парсинга
            task: Объект задачи для обновления прогресса

        Returns:
            Список ScrapedData
        """
        results = []

        video_info, channel_info, raw_data = await scraper.scrape_video(url)

        if not video_info:
            task.errors.append(f"Не удалось получить данные видео: {url}")
            return results

        task.progress = 30.0

        # Получаем субтитры
        subtitles = []
        if options.get_subtitles:
            try:
                video_id = extract_video_id_from_url(url)
                if video_id:
                    subtitles = await get_video_subtitles(
                        video_id,
                        languages=options.subtitle_languages,
                        format=options.subtitle_format,
                        prefer_manual=options.prefer_manual_subtitles
                    )
                    task.progress = 60.0
            except Exception as e:
                task.warnings.append(f"Не удалось получить субтитры: {str(e)}")

        # Получаем комментарии
        comments = []
        if options.get_comments:
            try:
                comments = await get_video_comments(
                    url,
                    max_comments=options.max_comments,
                    get_replies=options.get_replies
                )
                task.progress = 90.0
            except Exception as e:
                task.warnings.append(f"Не удалось получить комментарии: {str(e)}")

        # Собираем результат
        scraped_data = ScrapedData(
            video=video_info,
            channel=channel_info,
            subtitles=subtitles,
            comments=comments,
        )

        results.append(scraped_data)

        return results

    async def _scrape_channel(
        self,
        scraper: YouTubeScraper,
        url: str,
        options: ScraperOptions,
        task: TaskResult
    ) -> List[ScrapedData]:
        """
        Парсит все видео с канала.

        Args:
            scraper: Экземпляр парсера
            url: URL канала
            options: Опции парсинга
            task: Объект задачи

        Returns:
            Список ScrapedData
        """
        results = []

        video_list = await scraper.scrape_channel(url)

        if not video_list:
            task.errors.append(f"Не удалось получить видео с канала: {url}")
            return results

        total = len(video_list)

        for i, (video_info, channel_info, raw_data) in enumerate(video_list):
            # Получаем дополнительные данные для каждого видео
            subtitles = []
            comments = []

            video_url = video_info.url

            if options.get_subtitles:
                try:
                    video_id = video_info.video_id
                    subtitles = await get_video_subtitles(
                        video_id,
                        languages=options.subtitle_languages,
                        format=options.subtitle_format,
                        prefer_manual=options.prefer_manual_subtitles
                    )
                except Exception as e:
                    task.warnings.append(f"Субтитры {video_id}: {str(e)}")

            if options.get_comments:
                try:
                    comments = await get_video_comments(
                        video_url,
                        max_comments=options.max_comments,
                        get_replies=options.get_replies
                    )
                except Exception as e:
                    task.warnings.append(f"Комментарии {video_info.video_id}: {str(e)}")

            scraped_data = ScrapedData(
                video=video_info,
                channel=channel_info,
                subtitles=subtitles,
                comments=comments,
            )

            results.append(scraped_data)

            # Обновляем прогресс
            task.progress = ((i + 1) / total) * 100

        return results

    async def _scrape_playlist(
        self,
        scraper: YouTubeScraper,
        url: str,
        options: ScraperOptions,
        task: TaskResult
    ) -> List[ScrapedData]:
        """
        Парсит все видео из плейлиста.

        Args:
            scraper: Экземпляр парсера
            url: URL плейлиста
            options: Опции парсинга
            task: Объект задачи

        Returns:
            Список ScrapedData
        """
        results = []

        video_list = await scraper.scrape_playlist(url)

        if not video_list:
            task.errors.append(f"Не удалось получить видео из плейлиста: {url}")
            return results

        total = len(video_list)

        for i, (video_info, channel_info, raw_data) in enumerate(video_list):
            subtitles = []
            comments = []

            if options.get_subtitles:
                try:
                    subtitles = await get_video_subtitles(
                        video_info.video_id,
                        languages=options.subtitle_languages,
                        format=options.subtitle_format,
                        prefer_manual=options.prefer_manual_subtitles
                    )
                except Exception as e:
                    task.warnings.append(f"Субтитры {video_info.video_id}: {str(e)}")

            if options.get_comments:
                try:
                    comments = await get_video_comments(
                        video_info.url,
                        max_comments=options.max_comments,
                        get_replies=options.get_replies
                    )
                except Exception as e:
                    task.warnings.append(f"Комментарии {video_info.video_id}: {str(e)}")

            scraped_data = ScrapedData(
                video=video_info,
                channel=channel_info,
                subtitles=subtitles,
                comments=comments,
            )

            results.append(scraped_data)
            task.progress = ((i + 1) / total) * 100

        return results

    async def _scrape_search(
        self,
        scraper: YouTubeScraper,
        query: str,
        options: ScraperOptions,
        task: TaskResult
    ) -> List[ScrapedData]:
        """
        Парсит результаты поиска.

        Args:
            scraper: Экземпляр парсера
            query: Поисковый запрос
            options: Опции парсинга
            task: Объект задачи

        Returns:
            Список ScrapedData
        """
        results = []

        video_list = await scraper.search_videos(query)

        if not video_list:
            task.warnings.append(f"По запросу '{query}' ничего не найдено")
            return results

        total = len(video_list)

        for i, (video_info, channel_info, raw_data) in enumerate(video_list):
            subtitles = []
            comments = []

            if options.get_subtitles:
                try:
                    subtitles = await get_video_subtitles(
                        video_info.video_id,
                        languages=options.subtitle_languages,
                        format=options.subtitle_format,
                        prefer_manual=options.prefer_manual_subtitles
                    )
                except Exception as e:
                    task.warnings.append(f"Субтитры {video_info.video_id}: {str(e)}")

            if options.get_comments:
                try:
                    comments = await get_video_comments(
                        video_info.url,
                        max_comments=options.max_comments,
                        get_replies=options.get_replies
                    )
                except Exception as e:
                    task.warnings.append(f"Комментарии {video_info.video_id}: {str(e)}")

            scraped_data = ScrapedData(
                video=video_info,
                channel=channel_info,
                subtitles=subtitles,
                comments=comments,
            )

            results.append(scraped_data)
            task.progress = ((i + 1) / total) * 100

        return results

    def get_task(self, task_id: str) -> Optional[TaskResult]:
        """
        Получает результат задачи по ID.

        Args:
            task_id: ID задачи

        Returns:
            TaskResult или None
        """
        return self.tasks.get(task_id)

    def get_task_info(self, task_id: str) -> Optional[TaskInfo]:
        """
        Получает краткую информацию о задаче.

        Args:
            task_id: ID задачи

        Returns:
            TaskInfo или None
        """
        task = self.tasks.get(task_id)
        if not task:
            return None

        return TaskInfo(
            task_id=task.task_id,
            status=task.status,
            task_type=task.task_type,
            input_data=task.input_data,
            created_at=task.created_at,
            progress=task.progress,
            total_items=task.total_items,
        )

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 50
    ) -> List[TaskInfo]:
        """
        Возвращает список задач.

        Args:
            status: Фильтр по статусу
            limit: Максимальное количество задач

        Returns:
            Список TaskInfo
        """
        tasks = []

        for task in self.tasks.values():
            if status and task.status != status:
                continue

            tasks.append(TaskInfo(
                task_id=task.task_id,
                status=task.status,
                task_type=task.task_type,
                input_data=task.input_data,
                created_at=task.created_at,
                progress=task.progress,
                total_items=task.total_items,
            ))

        # Сортируем по дате создания (новые первыми)
        tasks.sort(key=lambda x: x.created_at, reverse=True)

        return tasks[:limit]

    def delete_task(self, task_id: str) -> bool:
        """
        Удаляет задачу по ID.

        Args:
            task_id: ID задачи

        Returns:
            True если задача удалена
        """
        if task_id in self.tasks:
            del self.tasks[task_id]
            return True
        return False

    def get_stats(self) -> dict:
        """
        Возвращает статистику по задачам.

        Returns:
            Словарь со статистикой
        """
        status_counts = defaultdict(int)
        for task in self.tasks.values():
            status_counts[task.status.value] += 1

        return {
            'total_tasks': len(self.tasks),
            'active_tasks': self.active_tasks,
            'queue_size': self.queue.qsize(),
            'status_counts': dict(status_counts),
        }


# Глобальный экземпляр менеджера задач
task_manager = TaskManager(max_concurrent_tasks=3)
