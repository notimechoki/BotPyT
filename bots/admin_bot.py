import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from redis.asyncio import Redis
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder

from app.config import ADMIN_BOT_TOKEN, REDIS_URL
from app.bot.admin.router import admin_router
from app.bot.mod.router import mod_router

async def main():
    bot = Bot(ADMIN_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    redis = Redis.from_url(REDIS_URL)
    storage = RedisStorage(redis=redis, key_builder=DefaultKeyBuilder(prefix="admin", with_bot_id=True))

    dp = Dispatcher(storage=storage)
    dp.include_router(admin_router)
    dp.include_router(mod_router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
