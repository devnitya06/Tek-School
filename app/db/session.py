from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings


SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Import all models to ensure they're registered with Base
from app.models.users import *
from app.models.school import *
from app.models.teachers import *
from app.models.students import *
from app.models.admin import *

def create_tables():
    """Create all tables that don't exist yet"""
    Base.metadata.create_all(bind=engine)

def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return False
    columns = inspector.get_columns(table_name)
    return any(column['name'] == column_name for column in columns)

def add_missing_columns():
    """Add missing columns to existing tables"""
    inspector = inspect(engine)
    
    for table_name in Base.metadata.tables.keys():
        if inspector.has_table(table_name):
            table = Base.metadata.tables[table_name]
            existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
            
            for column in table.columns:
                if column.name not in existing_columns:
                    column_type = column.type.compile(engine.dialect)
                    
                    # Add the column to the table
                    with engine.begin() as conn:
                        alter_stmt = f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {column_type}'
                        
                        # Add NULL/NOT NULL constraint
                        if not column.nullable:
                            alter_stmt += " NOT NULL"
                        
                        # Add default value if specified
                        if column.default is not None:
                            if callable(column.default.arg):
                                default_value = column.default.arg()
                            else:
                                default_value = column.default.arg
                            alter_stmt += f" DEFAULT '{default_value}'"
                        
                        conn.execute(text(alter_stmt))
def drop_extra_columns():
    inspector = inspect(engine)
    
    for table_name in Base.metadata.tables.keys():
        if inspector.has_table(table_name):
            model_columns = {c.name for c in Base.metadata.tables[table_name].columns}
            db_columns = {col['name'] for col in inspector.get_columns(table_name)}
            
            extra_columns = db_columns - model_columns
            for column in extra_columns:
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE "{table_name}" DROP COLUMN "{column}"'))


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()