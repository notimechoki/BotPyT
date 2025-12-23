import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from redis.asyncio import Redis
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder

from app.config import USER_BOT_TOKEN, REDIS_URL
from app.bot.user.router import user_router

async def main():
    bot = Bot(USER_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    redis = Redis.from_url(REDIS_URL)
    storage = RedisStorage(redis=redis, key_builder=DefaultKeyBuilder(prefix="user", with_bot_id=True))

    dp = Dispatcher(storage=storage)
    dp.include_router(user_router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
