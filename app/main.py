"""
YouTube Scraper API - FastAPI приложение.
Предоставляет REST API для парсинга данных с YouTube.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from . import __version__
from .models import (
    TaskRequest, BulkTaskRequest, TaskResult, TaskInfo, TaskStatus,
    ExportRequest, ExportFormat, APIResponse, HealthCheck, ScraperOptions
)
from .tasks import task_manager
from .exporters import export_task_result, DataExporter

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# === ЖИЗНЕННЫЙ ЦИКЛ ПРИЛОЖЕНИЯ ===

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Контекстный менеджер жизненного цикла приложения.
    Запускает и останавливает воркеры задач.
    """
    # Запуск
    logger.info("Запуск YouTube Scraper API...")
    await task_manager.start()
    logger.info("API готов к работе")

    yield

    # Остановка
    logger.info("Остановка YouTube Scraper API...")
    await task_manager.stop()
    logger.info("API остановлен")


# === СОЗДАНИЕ ПРИЛОЖЕНИЯ ===

app = FastAPI(
    title="YouTube Scraper API",
    description="""
    ## Парсер данных YouTube

    API для массового сбора данных с YouTube:
    - Видео (метаданные, лайки, просмотры)
    - Каналы (подписчики, общее количество видео)
    - Плейлисты
    - Субтитры (автоматические и ручные)
    - Комментарии

    ### Использование

    1. Создайте задачу через POST /tasks
    2. Получите результат через GET /tasks/{task_id}
    3. Экспортируйте данные через GET /tasks/{task_id}/export

    ### Интеграция с n8n

    API полностью совместим с HTTP-запросами n8n.
    Используйте webhook-узлы для отправки задач и получения результатов.
    """,
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Настройка CORS для интеграции с n8n и другими сервисами
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене укажите конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === ЭНДПОИНТЫ ===

# --- Проверка состояния ---

@app.get(
    "/health",
    response_model=HealthCheck,
    tags=["Система"],
    summary="Проверка состояния сервиса"
)
async def health_check():
    """
    Возвращает состояние сервиса и статистику задач.
    Используйте для проверки работоспособности API.
    """
    stats = task_manager.get_stats()

    return HealthCheck(
        status="ok",
        version=__version__,
        active_tasks=stats['active_tasks'],
        pending_tasks=stats['queue_size'],
    )


@app.get(
    "/",
    tags=["Система"],
    summary="Информация об API"
)
async def root():
    """Корневой эндпоинт с информацией об API."""
    return {
        "name": "YouTube Scraper API",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }


# --- Управление задачами ---

@app.post(
    "/tasks",
    response_model=APIResponse,
    tags=["Задачи"],
    summary="Создать задачу парсинга"
)
async def create_task(request: TaskRequest):
    """
    Создаёт новую задачу парсинга.

    ## Типы задач

    - **video** - парсинг одного видео
    - **channel** - парсинг всех видео канала
    - **playlist** - парсинг плейлиста
    - **search** - поиск по ключевым словам

    ## Пример запроса

    ```json
    {
        "task_type": "video",
        "input_data": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "options": {
            "get_subtitles": true,
            "subtitle_languages": ["ru", "en"],
            "get_comments": true,
            "max_comments": 100
        }
    }
    ```

    ## Возвращает

    ID созданной задачи для последующего получения результатов.
    """
    try:
        task_id = task_manager.create_task(request)

        return APIResponse(
            success=True,
            message="Задача создана и добавлена в очередь",
            data={"task_id": task_id}
        )
    except Exception as e:
        logger.error(f"Ошибка при создании задачи: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/tasks/bulk",
    response_model=APIResponse,
    tags=["Задачи"],
    summary="Создать несколько задач"
)
async def create_bulk_tasks(request: BulkTaskRequest):
    """
    Создаёт несколько задач парсинга одновременно.
    Максимум 100 задач за один запрос.

    ## Пример запроса

    ```json
    {
        "tasks": [
            {
                "task_type": "video",
                "input_data": "https://www.youtube.com/watch?v=video1"
            },
            {
                "task_type": "video",
                "input_data": "https://www.youtube.com/watch?v=video2"
            }
        ]
    }
    ```
    """
    try:
        task_ids = []
        for task_request in request.tasks:
            task_id = task_manager.create_task(task_request)
            task_ids.append(task_id)

        return APIResponse(
            success=True,
            message=f"Создано {len(task_ids)} задач",
            data={"task_ids": task_ids}
        )
    except Exception as e:
        logger.error(f"Ошибка при создании задач: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/tasks/{task_id}",
    response_model=TaskResult,
    tags=["Задачи"],
    summary="Получить результат задачи"
)
async def get_task(task_id: str):
    """
    Возвращает полный результат задачи, включая все собранные данные.

    ## Статусы задач

    - **pending** - в очереди
    - **processing** - выполняется
    - **completed** - завершено
    - **failed** - ошибка

    Используйте поле `progress` для отслеживания выполнения (0-100).
    """
    task = task_manager.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    return task


@app.get(
    "/tasks/{task_id}/status",
    response_model=TaskInfo,
    tags=["Задачи"],
    summary="Получить статус задачи"
)
async def get_task_status(task_id: str):
    """
    Возвращает краткую информацию о задаче без данных.
    Используйте для проверки статуса выполнения.
    """
    task_info = task_manager.get_task_info(task_id)

    if not task_info:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    return task_info


@app.get(
    "/tasks",
    response_model=List[TaskInfo],
    tags=["Задачи"],
    summary="Список задач"
)
async def list_tasks(
    status: Optional[TaskStatus] = Query(None, description="Фильтр по статусу"),
    limit: int = Query(50, ge=1, le=200, description="Количество задач")
):
    """
    Возвращает список всех задач с фильтрацией по статусу.
    """
    return task_manager.list_tasks(status=status, limit=limit)


@app.delete(
    "/tasks/{task_id}",
    response_model=APIResponse,
    tags=["Задачи"],
    summary="Удалить задачу"
)
async def delete_task(task_id: str):
    """
    Удаляет задачу и её результаты.
    Не влияет на задачи, которые находятся в процессе выполнения.
    """
    if task_manager.delete_task(task_id):
        return APIResponse(
            success=True,
            message="Задача удалена",
            data={"task_id": task_id}
        )
    else:
        raise HTTPException(status_code=404, detail="Задача не найдена")


# --- Экспорт данных ---

@app.get(
    "/tasks/{task_id}/export",
    tags=["Экспорт"],
    summary="Экспортировать результаты"
)
async def export_task(
    task_id: str,
    format: ExportFormat = Query(ExportFormat.JSON, description="Формат экспорта"),
    include_subtitles: bool = Query(True, description="Включить субтитры"),
    include_comments: bool = Query(True, description="Включить комментарии")
):
    """
    Экспортирует результаты задачи в указанном формате.

    ## Форматы

    - **json** - структурированный JSON
    - **csv** - плоская таблица CSV

    ## Использование в n8n

    Для загрузки в базу знаний используйте CSV формат:
    ```
    GET /tasks/{task_id}/export?format=csv&include_subtitles=true
    ```
    """
    task = task_manager.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Задача не завершена. Текущий статус: {task.status.value}"
        )

    try:
        content = export_task_result(
            task,
            format=format,
            include_subtitles=include_subtitles,
            include_comments=include_comments
        )

        if format == ExportFormat.JSON:
            return Response(
                content=content,
                media_type="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename=youtube_data_{task_id}.json"
                }
            )
        else:
            return Response(
                content=content,
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=youtube_data_{task_id}.csv"
                }
            )

    except Exception as e:
        logger.error(f"Ошибка при экспорте: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/tasks/{task_id}/export/comments",
    tags=["Экспорт"],
    summary="Экспортировать комментарии"
)
async def export_comments(task_id: str):
    """
    Экспортирует только комментарии в CSV формате.
    Удобно для анализа обратной связи.
    """
    task = task_manager.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Задача не завершена. Текущий статус: {task.status.value}"
        )

    try:
        exporter = DataExporter()
        content = exporter.export_comments_to_csv(task.data)

        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=comments_{task_id}.csv"
            }
        )

    except Exception as e:
        logger.error(f"Ошибка при экспорте комментариев: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/tasks/{task_id}/export/subtitles",
    tags=["Экспорт"],
    summary="Экспортировать субтитры"
)
async def export_subtitles(task_id: str):
    """
    Экспортирует только субтитры в CSV формате.
    """
    task = task_manager.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Задача не завершена. Текущий статус: {task.status.value}"
        )

    try:
        exporter = DataExporter()
        content = exporter.export_subtitles_to_csv(task.data)

        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=subtitles_{task_id}.csv"
            }
        )

    except Exception as e:
        logger.error(f"Ошибка при экспорте субтитров: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Статистика ---

@app.get(
    "/stats",
    tags=["Система"],
    summary="Статистика сервиса"
)
async def get_stats():
    """
    Возвращает статистику по задачам и системе.
    """
    return task_manager.get_stats()


# === БЫСТРЫЕ ЭНДПОИНТЫ ДЛЯ N8N ===

@app.post(
    "/scrape/video",
    response_model=APIResponse,
    tags=["Быстрые запросы"],
    summary="Быстрый парсинг видео"
)
async def quick_scrape_video(
    url: str = Query(..., description="URL видео"),
    get_subtitles: bool = Query(False, description="Получить субтитры"),
    get_comments: bool = Query(False, description="Получить комментарии"),
    max_comments: int = Query(50, description="Макс. комментариев")
):
    """
    Быстрый запрос на парсинг одного видео.
    Упрощённая версия для интеграции с n8n.

    ## Пример n8n HTTP Request

    ```
    POST /scrape/video?url=https://youtube.com/watch?v=xxx&get_subtitles=true
    ```
    """
    from .models import TaskType

    options = ScraperOptions(
        get_subtitles=get_subtitles,
        get_comments=get_comments,
        max_comments=max_comments,
    )

    request = TaskRequest(
        task_type=TaskType.VIDEO,
        input_data=url,
        options=options
    )

    task_id = task_manager.create_task(request)

    return APIResponse(
        success=True,
        message="Задача создана",
        data={"task_id": task_id}
    )


@app.post(
    "/scrape/search",
    response_model=APIResponse,
    tags=["Быстрые запросы"],
    summary="Быстрый поиск видео"
)
async def quick_search(
    query: str = Query(..., description="Поисковый запрос"),
    max_results: int = Query(10, description="Количество результатов"),
    get_subtitles: bool = Query(False, description="Получить субтитры"),
    get_comments: bool = Query(False, description="Получить комментарии")
):
    """
    Быстрый поиск видео по ключевым словам.

    ## Пример

    ```
    POST /scrape/search?query=python+tutorial&max_results=20
    ```
    """
    from .models import TaskType

    options = ScraperOptions(
        max_results=max_results,
        get_subtitles=get_subtitles,
        get_comments=get_comments,
    )

    request = TaskRequest(
        task_type=TaskType.SEARCH,
        input_data=query,
        options=options
    )

    task_id = task_manager.create_task(request)

    return APIResponse(
        success=True,
        message="Задача поиска создана",
        data={"task_id": task_id}
    )


# === ТОЧКА ВХОДА ===

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
