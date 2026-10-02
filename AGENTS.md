# AGENTS.md

Следуй `ARCHITECTURE.md` как источнику истины по дизайну системы.

## Общее

- Не вводи технологии, сервисы и слои, которые не требуются архитектурой.
- Предпочитай простой явный код абстракциям.
- Не реализуй будущий функционал «на всякий случай».
- Держи функции и классы небольшими и сфокусированными.

## Архитектура

```text
Agent → Tool → SearchService → Repository → PostgreSQL
Worker → DogmaClient → Parser/Normalizer → Repository
```

Запрещено: Agent→Repository/SQL/DogmaClient; Tool→DeepSeek HTTP/SQLAlchemy; SearchService→Agent/DeepSeek/DOGMA; Parser/Worker→Agent/FastAPI/DeepSeek.

## AI

- LLM никогда не обращается к PostgreSQL напрямую и не придумывает данные о квартирах.
- Реальные данные только из `search_apartments`.
- Структурированный массив `apartments` в `/chat` — из результата tool, не из текста LLM.
- DeepSeek скрыт за `LLMProvider`.

## DOGMA / БД

- Только JSON API; `status_code` хранить как есть; `statuses=[2]` — только фильтр синхронизации.
- Идемпотентный upsert по `source_id`; никогда не деактивировать квартиры после failed/partial sync.
- SQL только в Repository; SQLAlchemy 2.x + Alembic; без физического удаления при sync.

## Тесты / стиль

- Unit-тесты: без вызовов DOGMA/DeepSeek; внешние сервисы — через mock.
- Integration-тесты с PostgreSQL для поведения repository.
- Python 3.12+, type hints, Pydantic, async там, где это реально полезно.

## Перед изменением архитектуры

Остановись и объясни: (1) зачем это нужно, (2) что меняется, (3) какие более простые альтернативы рассматривались. Не меняй `ARCHITECTURE.md` молча.
