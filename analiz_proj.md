## Анализ проекта «QR-коды рестораны» и план доработок до уровня Senior

Я детально изучил архитектуру и код проекта. Ниже — разбор по слоям и приоритетированный план того, чего не хватает до продакшен-уровня (Senior).

---

### Текущая архитектура (кратко)

Слоистая архитектура: `config → database (asyncpg + repositories) → services → handlers`, DI через middleware, два бота (guest/staff) в одном процессе, raw SQL через asyncpg, деплой в Docker Compose с PostgreSQL.

Плюсы: разделение слоёв, repository pattern, типизация, идемпотентный init, Docker с healthcheck/non-root/tini, graceful shutdown, тесты есть.

---

### 🔴 КРИТИЧНО (Security & Data Integrity)

#### 1. Пароли хранятся и проверяются в открытом виде
`AuthService.authenticate` делает `user.password != password` напрямую. В `users.password` лежит plaintext. Нет ни bcrypt, ни argon2.
- **Решение:** `passlib[bcrypt]` / `argon2-cffi`, хранить только хеш, добавить `password_hash` колонку, миграцию с принудительной сменой пароля admin.

#### 2. Захардкоженные креды администратора
`ensure_admin_exists("admin", "password123")` в `main.py` и `init_db.py`. Дефолтный пароль известен из исходников.
- **Решение:** `ADMIN_USERNAME` / `ADMIN_PASSWORD` из `.env` (обязательные при первом запуске), генерация одноразового пароля, требование смены при первом входе.

#### 3. Сессии в памяти процесса
`_sessions: Dict[int, str]` в `auth_middleware.py` — глобальный словарь. Теряется при рестарте, не масштабируется на >1 инстанс, нет TTL/ревока.
- **Решение:** Redis-backed sessions (или хотя бы таблица `sessions` в БД) с TTL и ревоком; `RedisStorage` для FSM вместо `MemoryStorage`.

#### 4. Нет транзакций в многошаговых операциях
`TableService.close_table` делает 6+ запросов (чтение assignment → update payment → чтение cart total → close → record bill → clear cart → delete cart). Если упадёт на середине — рассинхрон данных.
- **Решение:** оборачивать в `async with conn.transaction():` (нужен метод `pool.transaction()` или explicit `BEGIN/COMMIT` в репозитории). То же касается `create_order_from_cart` (создание заказа + авто-назначение официанта).

#### 5. Нет rate limiting / throttling
Перебор паролей по `login:password` ничем не ограничен.
- **Решение:** aiogram `ThrottlingMiddleware` + лимиты на `/start`, логин, кнопки корзины.

---

### 🟠 АРХИТЕКТУРА (Major)

#### 6. Миграции «вручную» вместо Alembic
В `requirements.txt` есть `alembic`, но он не используется. Вместо этого — `COLUMN_MIGRATIONS` / `TYPE_MIGRATIONS` списки в `models.py`. Это не масштабируется, нет rollback, нет версионирования.
- **Решение:** внедрить Alembic с autogenerate, вынести DDL из кода в `alembic/versions/`, убрать `init_db.py`-логику из `main.py`.

#### 7. Дублирование `init_database()`
Идентичная функция в `main.py` (строки 77–142) и `init_db.py` (строки 25–110). Нарушение DRY.
- **Решение:** вынести в `database/migrations.py` и переиспользовать.

#### 8. Нарушение инкапсуляции: handler лезет в приватный атрибут сервиса
В `staff_handlers.py` много мест вида `auth_service._user_repo.find_by_username(session)` (строки 62, 127, 146, 238, 283, 322, 408, 461). Handler не должен знать о репозитории сервиса.
- **Решение:** добавить в `AuthService` публичный метод `get_user_by_username(username)` (или `resolve_session(session) -> Optional[User]`) и использовать его.

#### 9. Нет абстракций (Protocol/ABC) у репозиториев
Репозитории — конкретные классы без интерфейсов. Сложно подменять и тестировать.
- **Решение:** ввести `typing.Protocol` (или ABC) для каждого репозитория; сервисы типизировать по интерфейсу, а не реализации.

#### 10. Бизнес-логика в handlers
`_build_table_info` (staff_handlers) и сложный `_require_active_table` (guest_handlers) — это бизнес-логика, которой место в сервисах.
- **Решение:** перенести в `TableService.get_table_overview()` / `SessionService.validate_table_session()`.

#### 11. Нет доменных исключений
Везде `raise ValueError(...)`. Нет иерархии бизнес-ошибок (`NotFoundException`, `ConflictError`, `InvalidStateError`, `PermissionError`).
- **Решение:** `exceptions.py` с доменной иерархией; единый error-handler middleware для маппинга в пользовательские сообщения.

#### 12. Глобальное состояние
`_pool` в `connection.py`, `_sessions` в `auth_middleware.py`.
- **Решение:** обернуть в класс `Database` / `SessionStore`, инстанс передавать через DI.

#### 13. N+1 запросы
- `auto_assign_waiter`: цикл `count_open_by_waiter` по каждому официанту → заменить одним `GROUP BY`.
- `_build_table_info`: `get_cart_total` на каждый стол → один запрос с агрегацией.

#### 14. Заказы не связаны с составом
`OrderRepository.create` хранит только `waiter_id, table_number, status`. Нет таблицы `order_items`. Невозможно понять, что было в заказе, после очистки корзины.
- **Решение:** таблица `order_items(order_id, menu_item_id, quantity, price)`, копирование состава корзины при `create_order_from_cart`.

---

### 🟡 НАДЁЖНОСТЬ И ОПЕРАЦИИ

#### 15. Нет кеширования
Меню/категории читаются из БД при каждом открытии, хотя меняются редко.
- **Решение:** in-memory кеш (TTL) или Redis для `get_all_categories` / `get_items_by_category`.

#### 16. Нет конкурентных блокировок на корзину
Два гостя за одним столом (через 2 устройства) могут одновременно менять корзину → race condition.
- **Решение:** `SELECT ... FOR UPDATE` в `add_item`/`remove_item`, либо advisory lock по `table_number`.

#### 17. FSM в `MemoryStorage`
Теряется при рестарте, не масштабируется. README заявляет «высокую нагрузку», но состояние — в RAM.
- **Решение:** `RedisStorage` (aiogram-fsm-redis).

#### 18. Нет observability
Нет Sentry, метрик (Prometheus/OpenTelemetry), структурированных логов с request-id.
- **Решение:** `sentry-sdk`, structlog/json-логи, middleware с request-id, метрики счётчиков заказов/ошибок.

#### 19. Healthcheck проверяет только БД
Не проверяет доступность Telegram API.
- **Решение:** расширить `healthcheck.py` проверкой `bot.get_me()` или хотя бы outbound HTTPS.

---

### 🟢 КАЧЕСТВО КОДА

#### 20. Magic strings вместо enum
Статусы оплат (`"unpaid"`, `"requested"`, `"payment_pending"`, `"paid"`), роли (`"admin"`, `"waiter"`), статусы заказов — разбросаны строками по всему коду.
- **Решение:** `enum.StrEnum` для `PaymentStatus`, `UserRole`, `OrderStatus`, `TableStatus`.

#### 21. Нет линтеров/форматтеров в проекте
Нет конфигов `ruff`/`black`/`mypy`/`isort`, нет `.pre-commit-config.yaml`.
- **Решение:** `pyproject.toml` с ruff + mypy, pre-commit хуки, единый стиль.

#### 22. f-strings в логах
`logger.info(f"...")` вычисляет строку всегда, даже если уровень выключен.
- **Решение:** `logger.info("msg %s", arg)` (lazy).

#### 22. `python-dotenv` в requirements, но не используется
pydantic-settings сам читает `.env`. Удалить зависимость.

---

### 🔵 ТЕСТИРОВАНИЕ И CI/CD

#### 23. Handlers не протестированы вообще
Тесты покрывают только сервисы/форматтеры/клавиатуры. Handler-логика (самая хрупкая) без тестов.
- **Решение:** тесты на роутеры через `aiogram` test-utils / mock `Message.answer`.

#### 24. Нет интеграционных тестов с БД
Всё на моках. Репозитории (сырой SQL) не проверяются против реального PostgreSQL.
- **Решение:** `testcontainers-python` со стартовым Postgres для репозиториев.

#### 25. Нет CI/CD
Нет `.github/workflows/`. Тесты и линтер не запускаются автоматически.
- **Решение:** GitHub Actions: `lint → test → build docker → (deploy)`; gate по покрытию.

#### 26. Нет gate по покрытию
В `pytest.ini` нет `--cov-fail-under`.

---

### 🟣 ПРОДУКТОВЫЕ ФИЧИ (для полноценной системы)

- Уведомления официанту при новом заказе/запросе счёта (chat_id уже хранится, но не используется).
- Жизненный цикл заказа со статусами и переходами (FSM-машина состояний).
- Управление меню через бот (админ): CRUD блюд/категорий, цены, фото.
- i18n (все строки захардкожены на русском).
- Чеки/квитки (PDF или текстовый чек с детализацией).
- Резерв столов, время открытия стола, тайм-аут неактивности.
- Audit log (кто закрыл стол, кто подтвердил оплату).

---

### Приоритеты внедрения (Roadmap)

| Приоритет | Задача | Сложность |
|-----------|--------|-----------|
| P0 | Хеширование паролей (#1), транзакции в close_table (#4), креды админа из env (#2) | Средняя |
| P0 | Alembic-миграции (#6), устранение дубликата init (#7) | Средняя |
| P1 | Сессии/FSM в Redis (#3, #17), rate limiting (#5) | Средняя |
| P1 | Убрать `_user_repo` из handlers (#8), доменные исключения (#11) | Низкая |
| P1 | Связь заказов с составом (#14) | Средняя |
| P2 | Protocol-интерфейсы репозиториев (#9), вынос логики из handlers (#10) | Средняя |
| P2 | Enums (#20), линтеры (#21), lazy-логи (#22) | Низкая |
| P2 | CI/CD (#25), тесты handlers (#23), интеграционные тесты (#24) | Средняя |
| P3 | Кеширование (#15), блокировки корзины (#16), observability (#18) | Высокая |
| P3 | Продуктовые фичи (уведомления, i18n, audit log) | Высокая |

---

**Итог:** Проект имеет хорошую базовую структуру (слои, паттерны, Docker, тесты сервисов), но до senior-уровня не хватает в первую очередь: безопасности (пароли, сессии), целостности данных (транзакции, связь заказов), инженерной культуры (миграции, CI, линтеры, покрытие handlers) и observability. Архитектурные дыры (private-доступ к репозиториям, бизнес-логика в handlers, глобальное состояние) — точечные и исправимы без переписывания.