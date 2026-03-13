# URL Shortener API

FastAPI-сервис для сокращения ссылок с поддержкой PostgreSQL и Redis-кэша.

---

## Быстрый старт (docker-compose)

```bash
docker-compose up --build
```

API будет доступен на `http://localhost:8000`.  
Документация Swagger: `http://localhost:8000/docs`.

---

## Запуск тестов

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

> Тесты используют **SQLite в памяти** вместо PostgreSQL и **mock Redis**,
> поэтому внешние сервисы запускать не нужно.

### 2. Запуск юнит- и функциональных тестов

```bash
pytest tests/ -v
```

### 3. Запуск тестов с замером покрытия

```bash
coverage run -m pytest tests/
coverage report -m          # текстовый отчёт в терминале
coverage html               # HTML-отчёт → htmlcov/index.html
```

Открыть отчёт о покрытии:

```bash
# macOS
open htmlcov/index.html
# Linux
xdg-open htmlcov/index.html
```

> **Текущее покрытие: ≥ 90 %** (файл `htmlcov/index.html` включён в репозиторий).

---

## Структура тестов

```
tests/
├── conftest.py          # фикстуры: in-memory SQLite DB, mocked Redis, TestClient
├── test_unit.py         # юнит-тесты: utils.generate_short_code, crud, cache
├── test_functional.py   # функциональные тесты всех эндпоинтов
└── locustfile.py        # нагрузочные тесты (Locust)
```

### Что покрывают тесты

| Файл | Что тестируется |
|------|----------------|
| `test_unit.py` | `generate_short_code` (длина, алфавит, случайность), все CRUD-функции, методы кэша |
| `test_functional.py` | `POST /links/shorten`, `GET /{short_code}` (redirect + cache + expired), `DELETE /links/{short_code}`, `PUT /links/{short_code}`, `GET /links/{short_code}/stats`, `GET /links/search` — успешные сценарии и обработка ошибок |
| `locustfile.py` | Нагрузка: создание ссылок, редиректы, попадание в кэш |

---

## Нагрузочное тестирование (Locust)

### Предварительно: запустить сервис

```bash
docker-compose up -d
```

### Запуск с веб-интерфейсом

```bash
locust -f tests/locustfile.py --host http://localhost:8000
# открыть http://localhost:8089
```

### Headless-режим (50 пользователей, 30 секунд)

```bash
locust -f tests/locustfile.py \
       --headless \
       -u 50 -r 10 \
       --run-time 30s \
       --host http://localhost:8000
```

### Сценарии нагрузки

| Класс пользователя | Описание | Вес |
|--------------------|----------|-----|
| `RegularUser` | Создаёт ссылки и переходит по ним | 3 |
| `PowerUser` | Многократно обращается к одним коротким ссылкам (тест кэша) | 1 |

---

## Эндпоинты API

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/links/shorten` | Создать короткую ссылку |
| `GET` | `/{short_code}` | Редирект по короткому коду |
| `DELETE` | `/links/{short_code}` | Удалить ссылку |
| `PUT` | `/links/{short_code}` | Обновить оригинальный URL |
| `GET` | `/links/{short_code}/stats` | Статистика ссылки |
| `GET` | `/links/search?original_url=...` | Найти ссылку по оригинальному URL |
