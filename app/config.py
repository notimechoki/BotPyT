import os
from dotenv import load_dotenv

load_dotenv()

USER_BOT_TOKEN = os.getenv("USER_BOT_TOKEN")
MOD_BOT_TOKEN = os.getenv("MOD_BOT_TOKEN")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

ADMINS = {int(i) for i in os.getenv("ADMINS", "").split(",") if i.strip()}
MODERATORS = {int(i) for i in os.getenv("MODERATORS", "").split(",") if i.strip()}

DATABASE_URL = (
    f"mysql+mysqldb://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)