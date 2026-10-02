# Architecture: DOGMA Apartment Search Chat Service

**Статус:** проектирование (код не реализован)  
**Дата:** 2026-10-02 (rev. 2)  
**Ограничение:** тестовое задание — простая, объяснимая, тестируемая архитектура

---

## 0. Executive Summary

Сервис состоит из двух независимых процессов:

1. **Worker** — периодически забирает квартиры из HTTP JSON API DOGMA и upsert’ит их в PostgreSQL.
2. **API** — принимает свободный текст в `POST /chat`, через DeepSeek tool calling вызывает детерминированный `search_apartments`, возвращает top 3–5 квартир и краткое объяснение.

Ключевой вывод исследования: **HTML-парсинг и browser automation не нужны**. Frontend использует публичный HTTP JSON API `service.dogma.ru`.

MVP: один tool `search_apartments`. Без Celery, Redis, Kafka, Kubernetes и дополнительных AI tools.

---

## 1. Исследование DOGMA

### 1.1. Источник данных

```text
Base URL:
  https://service.dogma.ru/api/layouts-filter

POST /v4/objects/filter   — листинг с фильтрами и пагинацией
GET  /v4/objects/{id}     — карточка объекта
POST /v4/config/all       — справочники фильтров / ЖК
POST /v4/projects/config  — список проектов
```

Авторизация не требуется. GraphQL нет. Browser automation не нужна.

### 1.2. Flow получения квартир

```text
POST https://service.dogma.ru/api/layouts-filter/v4/objects/filter
Content-Type: application/json

{
  "type": 1,
  "statuses": [2],
  "limit": 100,
  "offset": 0,
  "group_by": ""
}

        ↓

{
  "status": "200",
  "error": null,
  "data": {
    "count": ...,
    "objects": [ { ... } ]
  }
}
```

`statuses=[2]` — **только фильтр синхронизации текущего каталога**, как его запрашивает frontend.  
**Не интерпретируем** `status_code=2` как `"available"` и не храним выдуманный текстовый статус.

### 1.3. Ключевые поля объекта

| Поле DOGMA | Использование у нас |
|------------|---------------------|
| `id` | `source_id` (unique) |
| `project_id` / `project_name` | ЖК |
| `cost` / `cost_sale` | цена: effective = `cost_sale` если `> 0`, иначе `cost` |
| `area` | площадь |
| `room` | комнаты (`0` = студия) |
| `type` | тип объекта (`1` = квартира) |
| `status` | хранится как `status_code` as-is |
| `floor` / `floor_max` | этаж |
| `address` | адрес |

URL: `https://dogma.ru/flat/{id}`.

### 1.4. Стратегия получения данных

```text
HTTP client → service.dogma.ru layouts-filter v4
Пагинация offset/limit
Фильтр синхронизации: type=1, statuses=[2]
Upsert по source_id = objects[].id
```

Не использовать Playwright/Selenium и HTML-парсинг каталога.

---

## 2. Общая архитектура

```text
                         ┌──────────────────────────────┐
                         │ service.dogma.ru             │
                         │ /api/layouts-filter/v4/...   │
                         └──────────────┬───────────────┘
                                        │ HTTP JSON
                                        ▼
                         ┌──────────────────────────────┐
                         │ DogmaClient                  │
                         └──────────────┬───────────────┘
                                        ▼
                         ┌──────────────────────────────┐
                         │ Parser / Normalizer          │
                         └──────────────┬───────────────┘
                                        ▼
┌────────────┐           ┌──────────────────────────────┐
│  Worker    │──────────▶│ ApartmentRepository (write)  │
└────────────┘           └──────────────┬───────────────┘
                                        ▼
                         ┌──────────────────────────────┐
                         │         PostgreSQL           │
                         └──────────────▲───────────────┘
                                        │
                         ┌──────────────┴───────────────┐
                         │ ApartmentRepository (read)   │
                         └──────────────▲───────────────┘
                                        │
                         ┌──────────────┴───────────────┐
                         │ SearchService                │
                         └──────────────▲───────────────┘
                                        │
                         ┌──────────────┴───────────────┐
                         │ search_apartments Tool       │
                         └──────────────▲───────────────┘
                                        │
User ──POST /chat──▶ FastAPI ──▶ Agent ──▶ LLM Provider (DeepSeek)
                                        │
                                   tool_call / tool result
```

### Зависимости (строго)

```text
Chat path:
  Agent → Tool → SearchService → Repository → PostgreSQL

Sync path:
  Worker → DogmaClient → Parser/Normalizer → Repository → PostgreSQL

Запрещено:
  Agent ↛ Repository / SQL / DogmaClient
  Tool ↛ DeepSeek HTTP / SQLAlchemy details
  SearchService ↛ Agent / DeepSeek / Dogma
  Parser/Worker ↛ Agent / FastAPI / DeepSeek
```

### Процессы

| Process | Роль |
|---------|------|
| `api` | HTTP + Agent |
| `worker` | Periodic sync |
| `postgres` | Storage |

---

## 3. Структура файлов проекта

```text
app/
├── main.py
├── api/
│   ├── deps.py
│   ├── routes_chat.py
│   ├── routes_health.py
│   └── schemas.py
├── agent/
│   ├── service.py
│   ├── prompts.py
│   └── tool_loop.py
├── llm/
│   ├── base.py
│   ├── types.py
│   └── deepseek.py
├── tools/
│   ├── registry.py
│   ├── schemas.py
│   └── search_apartments.py
├── apartments/
│   ├── models.py
│   ├── repository.py
│   ├── schemas.py
│   └── search_service.py
├── parser/
│   ├── dogma_client.py
│   ├── dogma_parser.py
│   ├── normalizer.py
│   └── sync_service.py
├── worker/
│   └── main.py
├── db/
│   ├── base.py
│   ├── session.py
│   └── migrations/
└── config/
    └── settings.py

tests/
├── unit/
│   ├── test_normalizer.py
│   ├── test_search_service.py
│   ├── test_agent_tool_selection.py
│   └── test_upsert.py
└── integration/
    ├── test_search_repo.py
    └── test_chat_endpoint.py

.env.example
ARCHITECTURE.md
README.md
Dockerfile                 # позже
docker-compose.yml         # позже
```

### Ответственность слоёв

| Слой | Ответственность |
|------|-----------------|
| Agent | LLM orchestration, tool loop, финальный текст |
| Tool | валидация args LLM → вызов SearchService → JSON для LLM |
| SearchService | детерминированные фильтры, сортировка, top N |
| Repository | SQL / upsert / queries |
| Worker | interval + lock + запуск sync |
| DogmaClient | только HTTP |
| Parser/Normalizer | extract + type mapping без AI |

---

## 4. AI Agent

### System prompt (обязательные правила)

1. Для поиска квартир всегда вызывать `search_apartments`.
2. **Никогда не придумывать** квартиры и их характеристики (цена, площадь, этаж, ЖК, URL и т.д.).
3. Все реальные данные брать **только** из результата `search_apartments`.
4. Если tool вернул пусто — сказать об этом; не подставлять вымышленные варианты.
5. В ответе: 3–5 вариантов + краткое объяснение соответствия запросу.

### Agent loop

```text
user message
    ↓
messages = [system, user]
    ↓
loop i = 1..MAX_TOOL_ITERATIONS (≤ 3)
    ↓
LLM.chat(messages, tools=[search_apartments])
    ↓
tool_calls?
    ├── no → final text
    └── yes → execute tool → append tool result → continue
    ↓
если лимит превышен → безопасный ответ + уже полученные tool results
```

Защита от циклов: `MAX_TOOL_ITERATIONS`, dedup одинаковых tool+args, timeout всего `/chat`.

---

## 5. Tool: `search_apartments`

### Назначение

Детерминированный поиск квартир в PostgreSQL по фильтрам из запроса пользователя.

### Input (все поля optional)

```text
ApartmentSearchToolInput:
  min_price: Optional[int]
  max_price: Optional[int]
  min_area: Optional[float]
  max_area: Optional[float]
  residential_complex: Optional[str]
  rooms: Optional[int]              # 0 = студия
  property_type: Optional[str]
  min_floor: Optional[int]
  max_floor: Optional[int]
  limit: Optional[int] = 5          # default 5, maximum 5
```

Backend: `limit = min(requested or 5, 5)`; при `limit < 1` → трактовать как default `5` (или clamp в `[1, 5]` — зафиксировать в реализации как default 5 / max 5).

### Output

```json
{
  "total": 42,
  "returned": 5,
  "items": [
    {
      "id": "uuid",
      "source_id": "60685",
      "residential_complex": "МКР Самолёт",
      "rooms": 0,
      "area": 35.7,
      "price": 4956509,
      "price_base": 6608679,
      "floor": 2,
      "floors_total": 16,
      "status_code": 2,
      "address": "Краснодар, ул. Западный обход",
      "url": "https://dogma.ru/flat/60685"
    }
  ]
}
```

В item **нет** выдуманного `status: "available"` — только `status_code` из DOGMA.

---

## 6. DeepSeek / LLM

```text
LLMProvider (protocol)
  chat(messages, tools=None) -> LLMResponse

DeepSeekClient(LLMProvider)
```

Agent зависит от абстракции, не от HTTP DeepSeek.

Конфиг: `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`, timeout, limited retry на 429/5xx.

---

## 7. SearchService

```text
in:  ApartmentSearchFilters
out: SearchResult(total, items)
```

### Фильтры (AND, отсутствующие пропускаются)

| Filter | Logic |
|--------|-------|
| price | `price >= min_price`, `price <= max_price` |
| area | `area >= min_area`, `area <= max_area` |
| rooms | exact |
| property_type | exact |
| floor | optional range |
| residential_complex | см. ниже |
| always | `is_active = true` |

### Поиск ЖК

```text
1) normalize input (trim, lower, ё→е)
2) exact match по residential_complexes.name_normalized
3) если 0 — partial match (ILIKE %normalized%)
4) фильтр apartments по найденным complex_id
```

### Сортировка и limit

```text
ORDER BY price ASC, area ASC
LIMIT clamp(limit or 5, max=5)
```

Пустой результат: `total=0, items=[]`.

SearchService не зависит от DeepSeek.

---

## 8. PostgreSQL

### `residential_complexes`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `source_project_id` | INT UNIQUE | DOGMA `project_id` |
| `name` | TEXT NOT NULL | |
| `name_normalized` | TEXT NOT NULL | для exact/partial search |
| `city_name` | TEXT NULL | |
| `created_at` / `updated_at` | TIMESTAMPTZ | |

Indexes: UNIQUE(`source_project_id`), INDEX(`name_normalized`).

### `apartments`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `source_id` | TEXT UNIQUE NOT NULL | DOGMA `id` |
| `residential_complex_id` | UUID FK | |
| `price` | BIGINT NOT NULL | effective price |
| `price_base` | BIGINT NULL | raw `cost` |
| `area` | NUMERIC(10,2) NOT NULL | |
| `rooms` | INT NOT NULL | `0` = студия |
| `property_type` | TEXT NOT NULL | |
| `floor` | INT NULL | |
| `floors_total` | INT NULL | |
| `status_code` | INT NOT NULL | **DOGMA status as-is** |
| `url` | TEXT NOT NULL | |
| `address` | TEXT NULL | |
| `flat_number` | TEXT NULL | |
| `raw_payload` | JSONB NULL | optional |
| `is_active` | BOOLEAN NOT NULL | см. семантику ниже |
| `last_seen_at` | TIMESTAMPTZ NOT NULL | |
| `created_at` / `updated_at` | TIMESTAMPTZ | |

**Семантика `is_active`:**  
`true` = квартира присутствует в **текущем синхронизируемом каталоге** DOGMA (последний успешный full sync с фильтром `type=1, statuses=[2]`).  
`false` = в последнем успешном sync объект больше не вернулся.  
Это **не** синоним бизнес-статуса продажи и **не** интерпретация `status_code`.

Indexes:

```text
UNIQUE (source_id)
(is_active, price)   WHERE is_active
(is_active, area)    WHERE is_active
(is_active, rooms)   WHERE is_active
(is_active, residential_complex_id) WHERE is_active
```

### `parser_runs`

| Column | Type |
|--------|------|
| `id` | UUID PK |
| `started_at` | TIMESTAMPTZ (`sync_started_at`) |
| `finished_at` | TIMESTAMPTZ NULL |
| `status` | `running` / `success` / `failed` |
| `apartments_parsed/created/updated/deactivated` | INT |
| `error_message` | TEXT NULL |
| `trigger` | `schedule` / `manual` |

---

## 9. Parser Layer

```text
DogmaClient → DogmaParser → Normalizer → Repository
```

- **DogmaClient** — HTTP only.
- **DogmaParser** — extract `data.objects` / `data.count`; schema validation.
- **Normalizer** — mapping чисел/URL/`rooms`; **`status_code = raw status` без текстовой интерпретации**; effective price.

Parser не знает про AI и FastAPI.

---

## 10. Worker / Sync

Простой Python process + interval. Без Celery/Redis/Kafka/K8s.

### Алгоритм одного запуска

```text
sync_started_at = now()          # единый timestamp на весь run
create parser_run(started_at=sync_started_at, status=running)

upsert residential_complexes from config/projects

offset = 0
WHILE pages remain:
  page = DogmaClient.filter(type=1, statuses=[2], limit, offset)
  IF network/HTTP/timeout/invalid JSON/unexpected schema:
      mark parser_run = failed
      STOP
      DO NOT deactivate anything
  FOR each object:
      normalize
      upsert apartment
      set last_seen_at = sync_started_at
      set is_active = true
  offset += limit

# сюда попадаем только если ВСЕ страницы успешно обработаны
deactivate:
  UPDATE apartments
  SET is_active = false, updated_at = now()
  WHERE is_active = true
    AND last_seen_at < sync_started_at
    AND property_type = 'apartment'

parser_run = success
```

### Правила

1. Один `sync_started_at` на весь run — пишется во все `last_seen_at`.
2. `is_active=false` **только** после полностью успешной пагинации.
3. Любая ошибка страницы / неожиданный формат → **failed**, деактивация **запрещена**.
4. Неожиданный пустой каталог (например `count=0` при ранее ненулевом) → failed, без deactivate.
5. Lock от параллельных job: Postgres advisory lock.

---

## 11. Upsert

```text
ON CONFLICT (source_id) DO UPDATE
  SET fields...,
      is_active = true,
      last_seen_at = :sync_started_at,
      updated_at = now()
```

Физически не удаляем квартиры.

---

## 12. API

### `POST /chat`

Request:

```json
{ "message": "Найди студию в ЖК X до 7 млн, от 30 м²" }
```

Response:

```json
{
  "reply": "...",
  "apartments": [ /* из tool result.items */ ],
  "meta": {
    "tool_called": "search_apartments",
    "total_found": 42,
    "model": "deepseek-chat"
  }
}
```

**Важно:** массив `apartments` формирует **backend** из результата `search_apartments`, а не парсит текст LLM.  
Текст `reply` — от модели, но опирается только на tool result; structured data всегда из SearchService.

### `GET /health`

```json
{ "status": "ok" }
```

Других endpoints в MVP нет.

---

## 13. Error handling (кратко)

| Источник | Поведение |
|----------|-----------|
| DOGMA page fail / bad schema | parser_run=failed, no deactivate |
| DeepSeek down / timeout | `/chat` 502/503 |
| invalid tool args | tool error → model once; затем graceful stop |
| search empty | `items=[]`, честный reply |
| Postgres down | API 503; worker fail run |

---

## 14. Configuration

```text
DATABASE_URL=
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
DOGMA_BASE_URL=https://service.dogma.ru/api/layouts-filter
DOGMA_PUBLIC_BASE_URL=https://dogma.ru
DOGMA_REQUEST_TIMEOUT=30
DOGMA_PAGE_LIMIT=100
WORKER_INTERVAL_SECONDS=3600
CHAT_MAX_TOOL_ITERATIONS=3
```

Secrets не в Git.

---

## 15. Docker Compose (концепт)

```text
postgres | api | worker
```

Один Python image, разные commands. Без оркестраторов очередей.

---

## 16. Testing

- Unit: normalizer, search filters/sort/limit, tool→SearchService, upsert/deactivate rules, agent с mock LLM.
- Integration: repo search на PostgreSQL, sync с mock DogmaClient, `/chat` с mock LLMProvider.
- Не бить в DeepSeek/DOGMA из unit tests.

---

## 17. Observability

Логировать: parser_run start/finish, parsed/created/updated/deactivated, chat request, tool call, tool time, search counts, LLM errors.  
Не логировать secrets.

---

## 18. Architectural Decisions (актуализировано)

1. **PostgreSQL** — фильтры, upsert, индексы.  
2. **Отдельный worker** — sync не блокирует API.  
3. **FastAPI** — простой async API.  
4. **Один tool `search_apartments`** — достаточно для MVP.  
5. **AI не ищет сам** — только tool → SQL.  
6. **Agent → Tool → SearchService → Repository** — чёткие границы.  
7. **Worker → DogmaClient → Parser/Normalizer → Repository** — ingest отдельно.  
8. **Upsert + `sync_started_at`/`last_seen_at`** — идемпотентность и безопасная деактивация.  
9. **`status_code` as-is** — без догадок о семантике статусов; `statuses=[2]` только sync-фильтр.  
10. **`is_active` = присутствие в текущем sync-каталоге**, не бизнес-статус.  
11. **Без Celery/Redis/Kafka/K8s** — простой loop worker.  
12. **Без browser automation** — прямой JSON API.  
13. **`apartments` в HTTP-ответе из tool result** — LLM не источник structured data.

---

## 19. Flows

### Flow A — sync

```text
Worker
 → sync_started_at
 → DogmaClient (pages)
 → Parser/Normalizer
 → Repository upsert (last_seen_at=sync_started_at)
 → on full success only: is_active=false for stale rows
 → PostgreSQL
```

### Flow B — chat

```text
User → POST /chat → Agent → DeepSeek
 → tool_call search_apartments
 → Tool → SearchService → Repository → PostgreSQL
 → tool result
 → DeepSeek reply text
 → backend builds response {reply, apartments=tool.items}
 → User
```

---

## 20. Architecture Review

| Вопрос | Ответ |
|--------|-------|
| Поиск без LLM? | Да |
| Worker без API? | Да |
| Parser без AI? | Да |
| Замена DeepSeek? | Да, через LLMProvider |
| Дубли при sync? | Нет, UNIQUE(source_id) |
| DOGMA partial fail? | failed run, no deactivate |
| Квартира пропала из каталога sync? | после успешного full sync `is_active=false` |
| LLM придумывает квартиру в `apartments[]`? | Нет |
| LLM выполняет SQL? | Нет |
| Оверкилл MVP? | Нет: 1 tool, 3 контейнера |

---

**Конец документа (rev. 2).**
