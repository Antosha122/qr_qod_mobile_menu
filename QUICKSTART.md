# 🚀 Как запустить Tokio Bar Bot — инструкция

> **Кратко:** есть 2 способа — через Docker (рекомендуется) или локально через Python.

---

## 🐳 Способ 1: Docker (рекомендуется)

### Шаг 0. Установите Docker Desktop

1. Скачайте: https://www.docker.com/products/docker-desktop/
2. Установите и **запустите Docker Desktop** (иконка кита в трее должна быть активной).
3. Проверьте в терминале:
   ```bash
   docker --version
   docker compose version
   ```
   Если обе команды отвечают версиями — всё готово.

---

### Шаг 1. Настройте `.env`

Ваш файл `.env` уже существует. **Но есть важный нюанс с прокси!**

В `.env` у вас сейчас:
```
PROXY_URL=http://127.0.0.1:10808
```

Это работает для **локального запуска** (Python напрямую), но **НЕ работает в Docker**,
потому что `127.0.0.1` внутри контейнера = сам контейнер, а не ваш компьютер.

**Решение для Docker — создайте файл `.env.docker`:**

```bash
# Скопируйте основной .env и измените только одну строку:
copy .env .env.docker
```

В `.env.docker` замените прокси:
```env
# Было (для локального запуска):
PROXY_URL=http://127.0.0.:10808

# Стало (для Docker — обращение к хост-машине):
PROXY_URL=http://host.docker.internal:10808
```

> ✅ `host.docker.internal` — это специальный адрес в Docker для обращения
> к вашему компьютеру из контейнера.

---

### Шаг 2. Запуск

```bash
# Если используете .env.docker:
docker compose --env-file .env.docker up -d --build

# Если прокси НЕ нужен (Telegram доступен напрямую):
docker compose up -d --build
```

| Команда | Что делает |
|---------|-----------|
| `docker compose up -d --build` | Собирает образ и запускает контейнеры в фоне |
| `docker compose logs -f bot` | Показывает логи бота в реальном времени |
| `docker compose logs -f db` | Показывает логи PostgreSQL |
| `docker compose ps` | Статус контейнеров |
| `docker compose down` | Останавливает и удаляет контейнеры |
| `docker compose down -v` | ⚠️ Полный сброс: контейнеры + данные БД! |

---

### Шаг 3. Проверка

```bash
# Статус (оба должны быть "Up" и "healthy"):
docker compose ps

# Проверка здоровья:
docker inspect --format='{{.State.Health.Status}}' tokio_bar_bot
docker inspect --format='{{.State.Health.Status}}' tokio_bar_db

# Логи (ищите "Both bots configured. Starting polling..."):
docker compose logs bot | Select-String "Starting"
```

Если видите `polling` — **боты запущены и работают!** 🎉

---

### Что происходит при запуске Docker?

```
1. Docker скачивает PostgreSQL 16 (если ещё нет)     ~10 сек
2. Docker собирает образ бота (pip install)          ~2-3 мин (первый раз)
3. Запускается PostgreSQL (healthcheck ждёт)          ~10 сек
4. Запускается бот:
   4.1. entrypoint.sh ждёт готовности БД              ~5 сек
   4.2. python init_db.py (создание таблиц, сиды)     ~2 сек
   4.3. python main.py (запуск polling)               ~3 сек
5. Бот работает ✅
```

---

### Обновление кода

После изменения любого `.py` файла:
```bash
docker compose up -d --build
```
Образ пересоберётся, БД и данные сохранятся.

---

## 🐍 Способ 2: Локальный запуск (без Docker)

### Требования
- Python 3.11+
- PostgreSQL 15+ (установленный на компьютере)

### Запуск

```bash
# 1. Виртуальное окружение
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Установка зависимостей
pip install -r requirements.txt

# 3. Проверьте, что PostgreSQL запущен и БД существует
#    (создайте БД, если её нет):
#    psql -U postgres -c "CREATE DATABASE tokio_bar;"

# 4. Запуск
python main.py
```

Система сама:
- Создаст все таблицы в БД
- Заполнит меню и категории (сид-данные)
- Создаст администратора `admin:password123`
- Запустит оба бота (гостевой + персонал)

---

## 🔧 Частые проблемы

### "Cannot connect to database" (локально)

```bash
# Проверьте, что PostgreSQL запущен:
# Windows:
Get-Service postgresql*

# Проверьте пароль в .env — должен совпадать с паролем PostgreSQL
```

### "Cannot connect to database" (Docker)

```bash
# Проверьте логи БД:
docker compose logs db

# Если БД не поднимается — проверьте пароль в .env
# Важно: пароль задаётся ПРИ ПЕРВОМ СОЗДАНИИ тома.
# Если уже создавали с другим паролем — нужно сбросить том:
docker compose down -v          # УДАЛИТ все данные!
docker compose up -d --build
```

### Бот не отвечает (прокси)

```bash
# Локально: проверьте, что VPN/прокси запущен на 127.0.0.1:10808
curl -x http://127.0.0.1:10808 https://api.telegram.org

# Docker: проверьте, что используете host.docker.internal:
docker compose exec bot python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:10808').status)"
```

### "Port 5432 already in use"

Это значит, что PostgreSQL уже запущен на компьютере.
В docker-compose.yml можно сменить порт БД, добавив:
```yaml
  db:
    ports:
      - "5433:5432"   # внешн:внутр
```

### Очистка и полный перезапуск (Docker)

```bash
# Остановить всё:
docker compose down

# Остановить и УДАЛИТЬ данные БД:
docker compose down -v

# Начать заново:
docker compose up -d --build
```

---

## 📋 Шпаргалка команд (PowerShell)

```bash
# === Docker ===
docker compose up -d --build        # Запуск
docker compose logs -f bot          # Логи бота
docker compose logs -f db           # Логи БД
docker compose ps                   # Статус
docker compose restart bot          # Перезапуск бота
docker compose down                 # Остановка
docker compose down -v              # Остановка + удаление данных

# === Внутри контейнера ===
docker compose exec bot sh          # Зайти в shell контейнера
docker compose exec bot python init_db.py    # Миграции вручную
docker compose exec db psql -U postgres -d tokio_bar   # Подключиться к БД

# === Локально (Python) ===
python main.py                      # Запуск
python init_db.py                   # Только миграции БД
python -m pytest tests/ -v          # Тесты
python -m utils.qr_generator --username Tokio_bar_bot --tables 7   # QR-коды