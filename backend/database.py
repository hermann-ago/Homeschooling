import os
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL", "sqlite:///./homeschool.db")
DB_SCHEMA = os.getenv("DB_SCHEMA", "app") if not DATABASE_URL.startswith("sqlite") else None

# Path normalization for SQLite on Windows
if DATABASE_URL.startswith("sqlite:///"):
    db_path = DATABASE_URL[10:]
    # If the path contains a drive letter (e.g. G:/) or starts with ./
    # we ensure it's handled correctly by SQLAlchemy
    if ":" in db_path or db_path.startswith("./"):
        # Normalize slashes and remove any accidental quotes
        db_path = db_path.replace('"', '').replace("'", "")
        DATABASE_URL = f"sqlite:///{db_path}"

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

try:
    if DATABASE_URL.startswith("sqlite"):
        engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
            echo=False,
        )
    else:
        # Supavisor owns pooling in production; each Vercel invocation should not
        # retain an additional local pool.
        engine = create_engine(
            DATABASE_URL,
            poolclass=NullPool,
            pool_pre_ping=True,
            connect_args={"sslmode": "require", "options": "-c search_path=app,public"},
            echo=False,
        )
except Exception as e:
    print(f"CRITICAL ERROR: Failed to create database engine for {DATABASE_URL}")
    print(f"Error detail: {e}")
    raise

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base(metadata=MetaData(schema=DB_SCHEMA))


def get_db():
    """FastAPI dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
