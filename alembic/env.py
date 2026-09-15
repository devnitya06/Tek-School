from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
import os
import sys
from pathlib import Path

# Add the project root to the path so Alembic can find your models
# env.py is at alembic/env.py, so parents[1] is the Tek-School project root
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Import Base from the correct location
from app.db.session import Base  # Base is defined in session.py

# Import all models here so Alembic autogenerate can detect them
import app.models.academic_results
import app.models.admin
import app.models.news
import app.models.placement
import app.models.progress_reports
import app.models.school
import app.models.staff
import app.models.students
import app.models.teachers
import app.models.tuition_models
import app.models.user_session
import app.models.users

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = os.environ.get("DATABASE_URL")
    if url is None:
        raise Exception("DATABASE_URL environment variable not set.")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        {'sqlalchemy.url': os.environ.get("DATABASE_URL")},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
