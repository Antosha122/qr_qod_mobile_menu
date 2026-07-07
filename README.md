# Restaurant Management System

> 🌐 **Languages:** [English](README.md) | [Русский](README.ru.md)

A Telegram bot system for restaurants featuring two bots: one for guests (ordering via QR codes) and one for staff (waiters and administrators).


## ✨ Features

### Guest Bot
- 📱 Scan a table QR code to start an order
- 🍽️ Browse the menu by categories
- 🛒 Add dishes to cart with quantity selection
- 🗑️ Manage cart (add/remove dishes)
- ✅ Place an order

### Staff Bot
- 🔑 Login with username and password
- 👨‍🍳 Manage waiters (add new accounts — admin only)
- 🍽️ View orders by table
- 📋 View all orders
- 🍣 View the menu
- 🚪 Manage sessions (login/logout)


### Design Principles
- **Dependency Injection** — services are injected via middleware
- **Repository Pattern** — database access isolation
- **Service Layer** — business logic separated from UI
- **Configuration Management** — all settings in `.env`
- **Type Safety** — full typing with mypy-compatible annotations

## 🛠 Technologies

| Component | Technology |
|-----------|-----------|
| Bot Framework | aiogram 3.4.1 |
| Database | PostgreSQL + asyncpg |
| Migrations | Alembic (versioned, rollback-able) |
| Schema (DDL) | SQLAlchemy 2.0 (for Alembic autogenerate) |
| Configuration | pydantic-settings |
| QR Codes | qrcode |
| Testing | pytest + pytest-asyncio |
| Logging | Python logging (rotating files) |

## 📦 Installation

### Requirements
- Python 3.11+
- PostgreSQL 15+

### Installation Steps

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd "pythonProject(QR коды рестораны)"
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up the database**
   ```bash
   # Create a PostgreSQL database
   createdb tokio_bar **or any other name**
   ```

## ⚙️ Configuration

1. **Copy the example config**
   ```bash
   cp .env.example .env
   ```

2. **Fill in the `.env` file**
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

   # Admin bootstrap credentials (used only on first run).
   # If ADMIN_PASSWORD is empty, a random one-time password is generated
   # and logged once; the admin must change it on first login.
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=
   ```

3. **Get bot tokens**
   - Message [@BotFather](https://t.me/BotFather) on Telegram
   - Create two bots: guest and staff
   - Copy the tokens into `.env`

## 🚀 Running

### Start the system
```bash
python main.py
```

The system will automatically:
- Apply DB schema migrations (Alembic, `alembic upgrade head`)
- Create a default admin (credentials from `.env`; if `ADMIN_PASSWORD`
  is empty — generate a one-time password, log it once, and require
  a password change on first login)
- Hash legacy plain-text passwords to bcrypt (if any)
- Start both bots in parallel

### 🗄 DB Schema Migrations (Alembic)

The database schema is managed by **Alembic** — all DDL changes live in
`alembic/versions/` and are applied versionally (with rollback support).

The source of truth for the schema is the SQLAlchemy models in `database/db_schema.py`.
The initialization logic (migrations + seeds + admin) is centralized in
`database/migrations.py::bootstrap_database()` and used by both `main.py`
and `init_db.py` (DRY).

```bash
# Apply all migrations (also used on bot startup)
python -m alembic upgrade head

# Roll back the last migration
python -m alembic downgrade -1

# Show the current schema version
python -m alembic current

# Generate a new migration from changed database/db_schema.py models
python -m alembic revision --autogenerate -m "add new column"

# Apply migrations + seeds + create admin (same as the entrypoint does)
python init_db.py
```

### Password Migration (one-time)

When migrating from plain-text passwords to bcrypt, run the dedicated script:

```bash
# Dry run — check which passwords will be hashed (no writes):
python migrate_passwords.py --dry-run

# Apply the migration (idempotent — already-hashed passwords are skipped):
python migrate_passwords.py
```

> Note: `main.py` and `init_db.py` also run the migration automatically,
> so a standalone run is only needed for existing databases where the
> migration hasn't been applied yet.

### QR Code Generation
```bash
python -m utils.qr_generator --username Tokio_bar_bot --tables 7
```

QR codes are saved to the `qr_codes/` folder.

## 🐳 Docker (Production Deployment)

The project is fully containerized: PostgreSQL and the bot start with a single command.
The image is designed for production and is resilient under high load.


### Quick Start

1. **Create `.env`** from the example:
   ```bash
   cp .env.example .env
   # Edit .env: insert your bot tokens and DB password
   ```

2. **Build and run:**
   ```bash
   docker compose up -d --build
   ```

3. **View logs:**
   ```bash
   docker compose logs -f bot
   ```

4. **Stop:**
   ```bash
   docker compose down
   ```

### Managing via Docker

```bash
# Rebuild after code changes
docker compose up -d --build

# Check container status
docker compose ps

# Check container health
docker inspect --format='{{.State.Health.Status}}' tokio_bar_bot
docker inspect --format='{{.State.Health.Status}}' tokio_bar_db

# Enter the bot container
docker compose exec bot sh

# Apply DB migrations manually (migrations + seeds + admin)
docker compose exec bot python init_db.py

# Work with Alembic directly inside the container
docker compose exec bot python -m alembic upgrade head
docker compose exec bot python -m alembic current

# Generate QR codes inside the container
docker compose exec bot python -m utils.qr_generator --username Tokio_bar_bot --tables 7

# Full reset (WARNING: deletes DB data!)
docker compose down -v
```

### Load Tuning

All parameters are set in `.env` — no need to rebuild the image, just restart the container:

```env
# asyncpg connection pool
DB_POOL_MIN_SIZE=2        # persistent connections
DB_POOL_MAX_SIZE=15       # max parallel DB requests
DB_COMMAND_TIMEOUT=60     # SQL query timeout (sec)

# Logging
LOG_LEVEL=INFO            # DEBUG | INFO | WARNING | ERROR
```

> ⚠️ `DB_POOL_MAX_SIZE` must be lower than PostgreSQL's `max_connections`
> (default 100). For a single bot instance, 10–20 is optimal.

### Environment Variables (full list)

| Variable | Required | Default | Description |
|----------|:---:|---|---|
| `GUEST_BOT_TOKEN` | ✅ | — | Guest bot token |
| `STAFF_BOT_TOKEN` | ✅ | — | Staff bot token |
| `DB_PASSWORD` | ✅ | — | PostgreSQL password |
| `DB_HOST` | — | `db` | DB host (Compose service name) |
| `DB_PORT` | — | `5432` | DB port |
| `DB_NAME` | — | `tokio_bar` | Database name |
| `DB_USER` | — | `postgres` | DB user |
| `DB_POOL_MIN_SIZE` | — | `2` | Min connection pool size |
| `DB_POOL_MAX_SIZE` | — | `15` | Max connection pool size |
| `DB_COMMAND_TIMEOUT` | — | `60` | Query timeout (sec) |
| `LOG_LEVEL` | — | `INFO` | Logging level |
| `TIMEZONE` | — | `Europe/Moscow` | Timezone |
| `TOTAL_TABLES` | — | `7` | Number of tables |
| `ADMIN_USERNAME` | — | `admin` | Default admin username |
| `ADMIN_PASSWORD` | — | — | Admin password (if empty — a one-time one is generated) |
| `PROXY_URL` | — | — | Proxy for Telegram API |
| `SKIP_DB_INIT` | — | `0` | Skip `init_db.py` on startup |

### Docker Infrastructure Files

```
├── Dockerfile              # Multi-stage image build
├── .dockerignore           # Build context exclusions
├── docker-compose.yml      # Orchestration: db + bot
└── docker/
    ├── entrypoint.sh       # Wait for DB → init_db → launch
    └── healthcheck.py      # Container liveness check
```

## 🧪 Testing

### Run all tests
```bash
python -m pytest tests/ -v
```

### Run with coverage
```bash
python -m pytest tests/ --cov=. --cov-report=html
```

### Results
- ✅ **105 tests** cover all services, keyboards, formatters, and the QR generator
- ✅ Tests use mocks to isolate from the DB and Telegram API

## 📁 Project Structure

```
.
├── main.py                    # Entry point (bots)
├── init_db.py                 # DB initialization (wrapper around bootstrap_database)
├── alembic.ini                # Alembic config (URL taken from .env)
├── migrate_passwords.py       # Migrate plain-text passwords to bcrypt
├── requirements.txt           # Dependencies
├── pytest.ini                 # Test configuration
├── .env.example               # Example configuration
├── Dockerfile                 # Docker image (multi-stage build)
├── docker-compose.yml         # Orchestration: PostgreSQL + bot
├── .dockerignore              # Docker context exclusions
│
├── alembic/                   # DB schema migrations (Alembic)
│   ├── env.py                 # Migration environment config (async + asyncpg)
│   ├── script.py.mako         # Template for new migrations
│   └── versions/              # Versioned migrations (upgrade/downgrade)
│
├── docker/                    # Docker infrastructure
│   ├── entrypoint.sh          # Wait for DB → migrations/seeds → launch
│   └── healthcheck.py         # Container healthcheck
│
├── config/                    # Configuration
│   ├── __init__.py
│   └── settings.py            # Pydantic settings
│
├── database/                  # Data layer
│   ├── __init__.py
│   ├── connection.py          # asyncpg connection pool
│   ├── models.py              # Dataclass models (DTO) + seed data
│   ├── db_schema.py           # SQLAlchemy models (schema source for Alembic)
│   ├── migrations.py          # bootstrap_database() — unified initialization
│   └── repositories/          # Repository Pattern
│       ├── __init__.py
│       ├── user_repository.py
│       ├── menu_repository.py
│       ├── cart_repository.py
│       ├── order_repository.py
│       └── waiter_assignment_repository.py
│
├── services/                  # Business logic
│   ├── __init__.py
│   ├── auth_service.py        # Authentication
│   ├── menu_service.py        # Menu operations
│   ├── cart_service.py        # Cart
│   ├── order_service.py       # Orders
│   └── table_service.py       # Table management
│
├── handlers/                  # Bot handlers
│   ├── __init__.py
│   ├── guest_handlers.py      # Guest bot
│   └── staff_handlers.py      # Staff bot
│
├── keyboards/                 # Telegram keyboards
│   ├── __init__.py
│   ├── guest_keyboards.py     # Inline keyboards
│   └── staff_keyboards.py     # Reply keyboards
│
├── middlewares/               # Middlewares
│   ├── __init__.py
│   ├── service_middleware.py  # Service injection
│   └── auth_middleware.py     # Session management
│
├── utils/                     # Utilities
│   ├── __init__.py
│   ├── logger.py              # Logging setup
│   ├── qr_generator.py        # QR code generation
│   ├── formatters.py          # Message formatting
│   └── security.py            # Password hashing (bcrypt)
│
├── tests/                     # Automated tests
│   ├── __init__.py
│   ├── conftest.py            # pytest fixtures
│   ├── test_auth_service.py
│   ├── test_cart_service.py
│   ├── test_menu_order_service.py
│   ├── test_table_service_and_utils.py
│   └── test_keyboards_and_qr.py
│
└── states.py                  # FSM states
```

## 📄 License

This project is licensed under the **MIT License**. See the
[LICENSE](LICENSE) file for details.