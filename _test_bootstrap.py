import asyncio
import logging

logging.basicConfig(level=logging.DEBUG)


async def t():
    from database.connection import check_db_connection, close_db_pool
    from database.migrations import bootstrap_database

    ok = await check_db_connection()
    print("db ok:", ok)
    await bootstrap_database()
    print("bootstrap DONE")
    await close_db_pool()
    print("pool closed")


asyncio.run(t())
print("script finished")