from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
Base = declarative_base()