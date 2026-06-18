"""Database schema constants and SQL definitions."""
from dataclasses import dataclass
from typing import Optional


class Base:
    """Base class for schema definitions."""
    pass


@dataclass(frozen=True)
class User:
    id: int
    username: str
    password: Optional[str]
    role: str
    chat_id: Optional[int]


@dataclass(frozen=True)
class Category:
    id: int
    name: str


@dataclass(frozen=True)
class MenuItem:
    id: int
    name: str
    description: Optional[str]
    price: float
    image_url: Optional[str]
    category_id: int


@dataclass(frozen=True)
class Cart:
    id: int
    table_number: int
    created_at: Optional[str]


@dataclass(frozen=True)
class CartItem:
    id: int
    cart_id: int
    menu_item_id: int
    quantity: int
    price: float


@dataclass(frozen=True)
class Order:
    id: int
    waiter_id: Optional[int]
    table_number: int
    status: str
    created_at: Optional[str]


@dataclass(frozen=True)
class WaiterAssignment:
    id: int
    waiter_id: Optional[int]
    table_number: int
    status: str
    assigned_at: Optional[str]
    payment_status: str = "unpaid"


@dataclass(frozen=True)
class ClosedBill:
    """A historical record of a closed table's payment.

    Recorded when staff closes a table, so that revenue and per-waiter
    statistics can be computed even after the table's cart has been cleared.
    """
    id: int
    waiter_id: Optional[int]
    table_number: int
    amount: float
    closed_at: Optional[str]


# SQL schema definitions
SCHEMA_SQL = """
-- Users table (staff authentication)
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255),
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'waiter')),
    chat_id BIGINT
);

-- Menu categories
CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

-- Menu items
CREATE TABLE IF NOT EXISTS menu (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    image_url VARCHAR(255),
    category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE
);

-- Shopping carts (one per table)
CREATE TABLE IF NOT EXISTS carts (
    id SERIAL PRIMARY KEY,
    table_number INTEGER NOT NULL UNIQUE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Cart items
CREATE TABLE IF NOT EXISTS cart_items (
    id SERIAL PRIMARY KEY,
    cart_id INTEGER REFERENCES carts(id) ON DELETE CASCADE,
    menu_item_id INTEGER REFERENCES menu(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0)
);

-- Orders
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    waiter_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    table_number INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Waiter-table assignments
CREATE TABLE IF NOT EXISTS waiter_assignments (
    id SERIAL PRIMARY KEY,
    waiter_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    table_number INTEGER NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    payment_status VARCHAR(20) NOT NULL DEFAULT 'unpaid',
    assigned_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Closed bills (historical revenue records kept after carts are cleared)
CREATE TABLE IF NOT EXISTS closed_bills (
    id SERIAL PRIMARY KEY,
    waiter_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    table_number INTEGER NOT NULL,
    amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    closed_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_menu_category_id ON menu(category_id);
CREATE INDEX IF NOT EXISTS idx_cart_items_cart_id ON cart_items(cart_id);
CREATE INDEX IF NOT EXISTS idx_cart_items_menu_item_id ON cart_items(menu_item_id);
CREATE INDEX IF NOT EXISTS idx_orders_table_number ON orders(table_number);
CREATE INDEX IF NOT EXISTS idx_waiter_assignments_table_number ON waiter_assignments(table_number);
CREATE INDEX IF NOT EXISTS idx_waiter_assignments_status ON waiter_assignments(status);
CREATE INDEX IF NOT EXISTS idx_closed_bills_waiter_id ON closed_bills(waiter_id);
CREATE INDEX IF NOT EXISTS idx_closed_bills_closed_at ON closed_bills(closed_at);
"""


def _split_sql(sql: str) -> list[str]:
    """Split a multi-statement SQL string into individual statements.
    
    asyncpg executes only one statement per call, so we split on ';'.
    Comment-only fragments and empty fragments are skipped.
    """
    statements = []
    for raw in sql.split(";"):
        lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if stmt:
            statements.append(stmt)
    return statements


SCHEMA_STATEMENTS: list[str] = _split_sql(SCHEMA_SQL)


# Column-level migrations: each tuple is (table, column, ALTER TABLE clause).
# Applied idempotently in init_db / main after the base schema is created.
COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    (
        "waiter_assignments",
        "payment_status",
        "ALTER TABLE waiter_assignments "
        "ADD COLUMN payment_status VARCHAR(20) NOT NULL DEFAULT 'unpaid'",
    ),
]

# Type-level migrations: widen/alter existing columns idempotently.
# ALTER TYPE is safe to run repeatedly (it's a no-op if the type already matches).
TYPE_MIGRATIONS: list[tuple[str, str, str]] = [
    # image_url holds full URLs (some Wikimedia thumbnail URLs exceed 255 chars)
    (
        "menu",
        "image_url",
        "ALTER TABLE menu ALTER COLUMN image_url TYPE TEXT",
    ),
]


# Seed data: default categories (idempotent insert)
SEED_CATEGORIES: list[tuple[int, str]] = [
    (1, "Горячие роллы"),
    (2, "Запеченные роллы"),
    (3, "Классические роллы"),
    (4, "Супы"),
    (5, "Напитки"),
]

# Seed data: default menu items (idempotent insert)
# NOTE: image_url is intentionally NOT part of this tuple to keep backward
# compatibility. Photos are applied separately via SEED_MENU_IMAGES below.
SEED_MENU_ITEMS: list[tuple[int, str, str, int, int]] = [
    (1, "Ролл с тунцом", "Сочный ролл с свежим тунцом", 400, 1),
    (2, "Ролл с креветками", "Хрустящий ролл с креветками", 500, 1),
    (3, "Ролл с угрем", "Нежный ролл с копченым угрем", 600, 1),
    (4, "Запеченный ролл с лососем", "С сыром и соусом спайси", 550, 2),
    (5, "Запеченный ролл с угрем", "С унаги-соусом и кунжутом", 650, 2),
    (6, "Запеченный ролл с курицей", "С грибами и сыром", 450, 2),
    (7, "Классический ролл с огурцом", "Свежий и легкий", 350, 3),
    (8, "Классический ролл с авокадо", "Вегетарианский", 400, 3),
    (9, "Классический ролл с лососем", "С свежим лососем", 500, 3),
    (10, "Мисо", "Традиционный японский суп", 200, 4),
    (11, "Рамен", "Свинина, яйцо, лапша", 350, 4),
    (12, "Чай", "Зеленый или черный", 100, 5),
    (13, "Сок", "Апельсиновый или яблочный", 150, 5),
]

# Seed data: photos for default menu items (500px thumbnails from Wikimedia
# Commons). Applied via UPDATE in init_db/main so existing rows get photos too.
# URLs were verified with browser-like User-Agent; Telegram fetches them fine.
SEED_MENU_IMAGES: dict[int, str] = {
    1: "https://upload.wikimedia.org/wikipedia/commons/thumb/9/97/Fresh_and_delicious_maki_roll_from_Phengphian_Laogumnerd_Cuisine.jpg/500px-Fresh_and_delicious_maki_roll_from_Phengphian_Laogumnerd_Cuisine.jpg",
    2: "https://upload.wikimedia.org/wikipedia/commons/thumb/1/15/Chicken_Teriyaki_Bento_%2B_Shrimp_Tempura_%2B_California_Rolls_%40_Hiro_Sushi_%285691301632%29.jpg/500px-Chicken_Teriyaki_Bento_%2B_Shrimp_Tempura_%2B_California_Rolls_%40_Hiro_Sushi_%285691301632%29.jpg",
    3: "https://upload.wikimedia.org/wikipedia/commons/thumb/0/02/DragonRoll.JPG/500px-DragonRoll.JPG",
    4: "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a2/Norwegia_Roll_Salmon_Sushi.jpg/500px-Norwegia_Roll_Salmon_Sushi.jpg",
    5: "https://upload.wikimedia.org/wikipedia/commons/thumb/7/76/Kaidaya_Unadon_01.jpg/500px-Kaidaya_Unadon_01.jpg",
    6: "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5b/Chicken_Deriyakidon.jpg/500px-Chicken_Deriyakidon.jpg",
    7: "https://upload.wikimedia.org/wikipedia/commons/thumb/8/81/Beef_maki_sushi_roll.jpg/500px-Beef_maki_sushi_roll.jpg",
    8: "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5c/Avocado_Maki_sushi_%28Albert_Heijn%29%2C_Hillegersberg%2C_Rotterdam_%282023%29.jpg/500px-Avocado_Maki_sushi_%28Albert_Heijn%29%2C_Hillegersberg%2C_Rotterdam_%282023%29.jpg",
    9: "https://upload.wikimedia.org/wikipedia/commons/thumb/0/03/HSY-_Sushi%2C_Sake.jpg/500px-HSY-_Sushi%2C_Sake.jpg",
    10: "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c8/A_bowl_of_miso_soup.jpg/500px-A_bowl_of_miso_soup.jpg",
    11: "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d3/2023-08-31_Japanese_Ramen_Soup_Noodle.jpg/500px-2023-08-31_Japanese_Ramen_Soup_Noodle.jpg",
    12: "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a8/Cup_of_Green_Tea_and_Snacks.jpg/500px-Cup_of_Green_Tea_and_Snacks.jpg",
    13: "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fd/Orange_juice_1.jpg/500px-Orange_juice_1.jpg",
}
