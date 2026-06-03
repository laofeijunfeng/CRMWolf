from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.get_database_url(),
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False
)

# 设置 MySQL 时区为北京时间
@event.listens_for(engine, "connect")
def set_timezone(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("SET time_zone = '+08:00'")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
