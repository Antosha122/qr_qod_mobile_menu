# 🍣 Tokio Bar — Система управления рестораном

Telegram-бот система для ресторана с двумя ботами: для гостей (заказ через QR-коды) и для персонала (официанты и администраторы).

## 📋 Содержание

- [Возможности](#возможности)
- [Архитектура](#архитектура)
- [Технологии](#технологии)
- [Установка](#установка)
- [Настройка](#настройка)
- [Запуск](#запуск)
- [Docker (продакшн-деплой)](#-docker-продакшн-деплой)
- [Тестирование](#тестирование)
- [Структура проекта](#структура-проекта)

## ✨ Возможности

### Бот для гостей (Guest Bot)
- 📱 Сканирование QR-кода стола для начала заказа
- 🍽️ Просмотр меню по категориям
- 🛒 Добавление блюд в корзину с выбором количества
- 🗑️ Управление корзиной (добавление/удаление блюд)
- ✅ Оформление заказа

### Бот для персонала (Staff Bot)
- 🔑 Авторизация по логину и паролю
- 👨‍🍳 Управление официантами (добавление новых аккаунтов — для админа)
- 🍽️ Просмотр заказов по столам
- 📋 Просмотр всех заказов
- 🍣 Просмотр меню
- 🚪 Управление сессиями (вход/выход)

## 🏗 Архитектура

Проект построен по **Clean Architecture** с разделением на слои:

```
┌─────────────────────────────────────┐
│           Handlers (Bots)           │  ← Telegram UI слой
├─────────────────────────────────────┤
│             Services                │  ← Бизнес-логика
├─────────────────────────────────────┤
│           Repositories              │  ← Доступ к данным
├─────────────────────────────────────┤
│            Database                 │  ← PostgreSQL + asyncpg
└─────────────────────────────────────┘
```

### Принципы проектирования
- **Dependency Injection** — сервисы внедряются через middleware
- **Repository Pattern** — изоляция доступа к БД
- **Service Layer** — бизнес-логика отделена от UI
- **Configuration Management** — все настройки в `.env`
- **Type Safety** — полная типизация с mypy-совместимыми аннотациями

## 🛠 Технологии

| Компонент | Технология |
|-----------|-----------|
| Bot Framework | aiogram 3.4.1 |
| Database | PostgreSQL + asyncpg |
| Configuration | pydantic-settings |
| QR Codes | qrcode |
| Testing | pytest + pytest-asyncio |
| Logging | Python logging (rotating files) |

## 📦 Установка

### Требования
- Python 3.11+
- PostgreSQL 15+

### Шаги установки

1. **Клонирование репозитория**
   ```bash
   git clone <repository-url>
   cd "pythonProject(QR коды рестораны)"
   ```

2. **Создание виртуального окружения**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Установка зависимостей**
   ```bash
   pip install -r requirements.txt
   ```

4. **Настройка базы данных**
   ```bash
   # Создайте базу данных PostgreSQL
   createdb tokio_bar
   ```

## ⚙️ Настройка

1. **Скопируйте пример конфигурации**
   ```bash
   cp .env.example .env
   ```

2. **Заполните `.env` файл**
   ```env
   # Bot Configuration
   GUEST_BOT_TOKEN=your_guest_bot_token
   STAFF_BOT_TOKEN=your_staff_bot_token

   # Database Configuration
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=tokio_bar
   DB_USER=postgres
   DB_PASSWORD=your_password

   # Application Settings
   LOG_LEVEL=INFO
   TIMEZONE=Europe/Moscow

   # Restaurant Settings
   TOTAL_TABLES=7
   ```

3. **Получите токены ботов**
   - Напишите [@BotFather](https://t.me/BotFather) в Telegram
   - Создайте двух ботов: гостевой и персональный
   - Скопируйте токены в `.env`

## 🚀 Запуск

### Запуск системы
```bash
python main.py
```

Система автоматически:
- Создаст схему базы данных
- Создаст администратора по умолчанию (`admin:password123`)
- Запустит оба бота параллельно

### Генерация QR-кодов
```bash
python -m utils.qr_generator --username Tokio_bar_bot --tables 7
```

QR-коды сохранятся в папку `qr_codes/`.

## 🐳 Docker (продакшн-деплой)

Проект полностью контейнеризован: PostgreSQL и бот запускаются одной командой.
Образ спроектирован для продакшна и устойчив к высоким нагрузкам.

### Преимущества Docker-сборки

| Функция | Описание |
|---------|----------|
| 🔒 Non-root пользователь | Контейнер работает от `bot` (UID 1001), не от `root` |
| 🧊 Многоэтапная сборка | Builder + runtime → минимальный размер образа |
| 🩺 Healthcheck | Docker автоматически проверяет доступность БД |
| ⏳ Ожидание БД | Entrypoint ждёт готовность PostgreSQL перед запуском |
| 🔁 Graceful shutdown | Корректная остановка по SIGTERM (Docker stop) |
| 📊 Лимиты ресурсов | CPU/RAM ограничения предотвращают OOM под нагрузкой |
| 🔁 Restart policy | Автоперезапуск при сбое (`unless-stopped`) |
| 🗄️ Persistent volumes | Данные БД, логи и QR-коды переживают пересоздание |
| ⚙️ Настраиваемый пул БД | Параметры пула asyncpg задаются через env |

### Быстрый старт

1. **Создайте `.env`** на основе примера:
   ```bash
   cp .env.example .env
   # Отредактируйте .env: вставьте токены ботов и пароль БД
   ```

2. **Соберите и запустите:**
   ```bash
   docker compose up -d --build
   ```

3. **Просмотр логов:**
   ```bash
   docker compose logs -f bot
   ```

4. **Остановка:**
   ```bash
   docker compose down
   ```

### Управление через Docker

```bash
# Пересобрать после изменения кода
docker compose up -d --build

# Проверить статус контейнеров
docker compose ps

# Проверить здоровье контейнеров
docker inspect --format='{{.State.Health.Status}}' tokio_bar_bot
docker inspect --format='{{.State.Health.Status}}' tokio_bar_db

# Зайти в контейнер бота
docker compose exec bot sh

# Применить миграции БД вручную
docker compose exec bot python init_db.py

# Сгенерировать QR-коды внутри контейнера
docker compose exec bot python -m utils.qr_generator --username Tokio_bar_bot --tables 7

# Полный сброс (ВНИМАНИЕ: удаляет данные БД!)
docker compose down -v
```

### Настройка под нагрузку

Все параметры задаются в `.env` — перезапускать образ не нужно, только контейнер:

```env
# Пул соединений asyncpg
DB_POOL_MIN_SIZE=2        # постоянные соединения
DB_POOL_MAX_SIZE=15       # максимум параллельных запросов к БД
DB_COMMAND_TIMEOUT=60     # таймаут SQL-запроса (сек)

# Логирование
LOG_LEVEL=INFO            # DEBUG | INFO | WARNING | ERROR
```

> ⚠️ `DB_POOL_MAX_SIZE` должен быть меньше `max_connections` в PostgreSQL
> (по умолчанию 100). Для одного инстанса бота значение 10–20 оптимально.

### Переменные окружения (полный список)

| Переменная | Обязательная | По умолчанию | Описание |
|------------|:---:|---|---|
| `GUEST_BOT_TOKEN` | ✅ | — | Токен гостевого бота |
| `STAFF_BOT_TOKEN` | ✅ | — | Токен бота персонала |
| `DB_PASSWORD` | ✅ | — | Пароль PostgreSQL |
| `DB_HOST` | — | `db` | Хост БД (имя сервиса в Compose) |
| `DB_PORT` | — | `5432` | Порт БД |
| `DB_NAME` | — | `tokio_bar` | Имя базы данных |
| `DB_USER` | — | `postgres` | Пользователь БД |
| `DB_POOL_MIN_SIZE` | — | `2` | Мин. размер пула соединений |
| `DB_POOL_MAX_SIZE` | — | `15` | Макс. размер пула соединений |
| `DB_COMMAND_TIMEOUT` | — | `60` | Таймаут запроса (сек) |
| `LOG_LEVEL` | — | `INFO` | Уровень логирования |
| `TIMEZONE` | — | `Europe/Moscow` | Часовой пояс |
| `TOTAL_TABLES` | — | `7` | Количество столов |
| `PROXY_URL` | — | — | Прокси для Telegram API |
| `SKIP_DB_INIT` | — | `0` | Пропустить `init_db.py` при старте |

### Файлы Docker-инфраструктуры

```
├── Dockerfile              # Многоэтапная сборка образа
├── .dockerignore           # Исключения из контекста сборки
├── docker-compose.yml      # Оркестрация: db + bot
└── docker/
    ├── entrypoint.sh       # Ожидание БД → init_db → запуск
    └── healthcheck.py      # Проверка живучести контейнера
```

## 🧪 Тестирование

### Запуск всех тестов
```bash
python -m pytest tests/ -v
```

### Запуск с покрытием
```bash
python -m pytest tests/ --cov=. --cov-report=html
```

### Результаты
- ✅ **65 тестов** покрывают все сервисы, клавиатуры, форматтеры и генератор QR
- ✅ Тесты используют моки для изоляции от БД и Telegram API

## 📁 Структура проекта

```
.
├── main.py                    # Точка входа
├── requirements.txt           # Зависимости
├── pytest.ini                 # Конфигурация тестов
├── .env.example               # Пример конфигурации
├── Dockerfile                 # Docker-образ (многоэтапная сборка)
├── docker-compose.yml         # Оркестрация: PostgreSQL + бот
├── .dockerignore              # Исключения из Docker-контекста
│
├── docker/                    # Docker-инфраструктура
│   ├── entrypoint.sh          # Ожидание БД → init_db → запуск
│   └── healthcheck.py         # Healthcheck контейнера
│
├── config/                    # Конфигурация
│   ├── __init__.py
│   └── settings.py            # Pydantic settings
│
├── database/                  # Слой данных
│   ├── __init__.py
│   ├── connection.py          # Пул соединений asyncpg
│   ├── models.py              # Dataclass-модели и SQL-схема
│   └── repositories/          # Repository Pattern
│       ├── __init__.py
│       ├── user_repository.py
│       ├── menu_repository.py
│       ├── cart_repository.py
│       ├── order_repository.py
│       └── waiter_assignment_repository.py
│
├── services/                  # Бизнес-логика
│   ├── __init__.py
│   ├── auth_service.py        # Авторизация
│   ├── menu_service.py        # Работа с меню
│   ├── cart_service.py        # Корзина
│   ├── order_service.py       # Заказы
│   └── table_service.py       # Управление столами
│
├── handlers/                  # Обработчики ботов
│   ├── __init__.py
│   ├── guest_handlers.py      # Бот для гостей
│   └── staff_handlers.py      # Бот для персонала
│
├── keyboards/                 # Клавиатуры Telegram
│   ├── __init__.py
│   ├── guest_keyboards.py     # Inline-клавиатуры
│   └── staff_keyboards.py     # Reply-клавиатуры
│
├── middlewares/               # Middlewares
│   ├── __init__.py
│   ├── service_middleware.py  # Внедрение сервисов
│   └── auth_middleware.py     # Управление сессиями
│
├── utils/                     # Утилиты
│   ├── __init__.py
│   ├── logger.py              # Настройка логирования
│   ├── qr_generator.py        # Генерация QR-кодов
│   └── formatters.py          # Форматирование сообщений
│
├── tests/                     # Автотесты
│   ├── __init__.py
│   ├── conftest.py            # Фикстуры pytest
│   ├── test_auth_service.py
│   ├── test_cart_service.py
│   ├── test_menu_order_service.py
│   ├── test_table_service_and_utils.py
│   └── test_keyboards_and_qr.py
│
└── states.py                  # FSM-состояния
```

## 🔐 Безопасность

- ✅ Все sensitive-данные в `.env` (не в коде)
- ✅ `.env` добавлен в `.gitignore`
- ✅ Параметризованные SQL-запросы (защита от SQL-инъекций)
- ✅ Валидация входных данных в сервисах

## 📝 Лицензия

Этот проект создан для ресторана Tokio Bar.