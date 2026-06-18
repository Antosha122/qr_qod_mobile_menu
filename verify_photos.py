"""One-off verification: list menu items and whether they have photos."""
import asyncio
import os

import asyncpg
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    rows = await conn.fetch(
        "SELECT id, name, image_url, length(image_url) AS len FROM menu ORDER BY id"
    )
    print(f"Total items: {len(rows)}")
    for r in rows:
        url = r["image_url"]
        flag = "IMG" if url else "NO"
        print(f"  [{flag}] {r['id']:>2} {r['name']:<32} len={r['len']}")
        if url:
            print(f"       {url[:90]}...")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())