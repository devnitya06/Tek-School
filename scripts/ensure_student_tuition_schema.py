"""
Database migration helper to create StudentTuitionTopicProgress table

Add this to ensure_* functions in app/db/session.py if needed
"""

from sqlalchemy import text, inspect
from sqlalchemy.orm import Session

def ensure_student_tuition_topic_progress_table(db: Session):
    """Ensure StudentTuitionTopicProgress table exists"""
    
    engine = db.get_bind()
    inspector = inspect(engine)
    
    if "student_tuition_topic_progress" in inspector.get_table_names():
        print("✓ student_tuition_topic_progress table already exists")
        return
    
    print("Creating student_tuition_topic_progress table...")
    
    sql = """
    CREATE TABLE IF NOT EXISTS student_tuition_topic_progress (
        id VARCHAR NOT NULL PRIMARY KEY,
        student_id INTEGER,
        self_signed_student_id INTEGER,
        student_type VARCHAR(30) NOT NULL DEFAULT 'student',
        topic_id VARCHAR NOT NULL,
        status VARCHAR NOT NULL DEFAULT 'not_started',
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        
        FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY(self_signed_student_id) REFERENCES self_signed_students(id) ON DELETE CASCADE,
        FOREIGN KEY(topic_id) REFERENCES tuition_lesson_topics(id) ON DELETE CASCADE,
        
        UNIQUE (student_id, topic_id),
        UNIQUE (self_signed_student_id, topic_id)
    );
    
    -- Create indexes for faster lookups
    CREATE INDEX ix_student_topic_progress_student ON student_tuition_topic_progress(student_id);
    CREATE INDEX ix_student_topic_progress_self_signed ON student_tuition_topic_progress(self_signed_student_id);
    CREATE INDEX ix_student_topic_progress_topic ON student_tuition_topic_progress(topic_id);
    CREATE INDEX ix_student_topic_progress_status ON student_tuition_topic_progress(status);
    """
    
    try:
        db.execute(text(sql))
        db.commit()
        print("✓ student_tuition_topic_progress table created successfully")
    except Exception as e:
        print(f"✗ Failed to create student_tuition_topic_progress table: {str(e)}")
        db.rollback()


# Quick manual setup script for reference
if __name__ == "__main__":
    from app.db.session import SessionLocal
    
    db = SessionLocal()
    try:
        ensure_student_tuition_topic_progress_table(db)
    finally:
        db.close()
