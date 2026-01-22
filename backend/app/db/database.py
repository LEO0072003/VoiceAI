from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.url import make_url
from app.core.config import settings

# Ensure target database exists (PostgreSQL)
def _ensure_database_exists(db_url: str) -> None:
    url = make_url(db_url)
    if url.get_backend_name() != "postgresql":
        return

    import psycopg2

    admin_url = url.set(database="postgres")
    conn = psycopg2.connect(
        dbname=admin_url.database,
        user=admin_url.username,
        password=admin_url.password,
        host=admin_url.host,
        port=admin_url.port,
    )
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (url.database,))
        exists = cur.fetchone() is not None
        if not exists:
            cur.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        cur.close()
        conn.close()

# Create DB if needed, then initialize engine/session
_ensure_database_exists(settings.DATABASE_URL)
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
