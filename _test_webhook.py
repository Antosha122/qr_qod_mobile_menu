import asyncio
import logging

logging.basicConfig(level=logging.DEBUG)


async def t():
    from config.settings import settings
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from utils.proxy_session import ProxyAwareAiohttpSession

    proxy_url = settings.proxy_url.strip()
    print("proxy:", proxy_url)
    session = ProxyAwareAiohttpSession(proxy=proxy_url)
    bot = Bot(
        token=settings.guest_bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    print("calling delete_webhook (guest bot)...")
    try:
        await asyncio.wait_for(
            bot.delete_webhook(drop_pending_updates=True), timeout=20
        )
        print("delete_webhook OK")
    except Exception as e:
        print("delete_webhook FAILED:", type(e).__name__, e)
    finally:
        await bot.session.close()
        print("session closed")


asyncio.run(t())
print("script finished")