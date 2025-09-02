from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Configure SQLAlchemy engine with connection pooling
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,                  # disable SQL echo in production
    pool_pre_ping=True,          # checks if connection is alive, reconnects if needed
    pool_size=5,                 # number of connections to keep open
    max_overflow=10,             # extra connections allowed when pool is full
    pool_recycle=1800,           # recycle connections every 30 mins (fixes stale ones)
    pool_timeout=30              # wait up to 30s for a connection before error
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency for FastAPI endpoints to get a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Utility to create tables if not exist (avoid in production migrations)."""
    Base.metadata.create_all(bind=engine)
