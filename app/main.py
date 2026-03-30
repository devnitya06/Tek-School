from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import users, auth, school, teachers, students, admin, selfsignedstudents, staff, workers, exams, business_inquiry
from app.core.config import settings
from app.db.session import create_tables, add_missing_columns, ensure_attendance_mark_columns
import os
app = FastAPI(title=settings.PROJECT_NAME)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(school.router, prefix="/school", tags=["schools"])
app.include_router(teachers.router, prefix="/teacher", tags=["Teacher"])
app.include_router(students.router, prefix="/student", tags=["Students"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(staff.router, prefix="/staff", tags=["Staff"])
app.include_router(workers.router, prefix="/worker", tags=["Workers"])
app.include_router(selfsignedstudents.router, prefix="/api", tags=["SelfSignedStudents"])
app.include_router(exams.router,prefix="/exam",tags=["Exam"])
app.include_router(business_inquiry.router, prefix="/inquiry", tags=["Business Inquiry"])

@app.on_event("startup")
def on_startup():
    # Always ensure attendance mark-in/out columns exist.
    # Prevents runtime failures when code is updated before a manual migration.
    try:
        ensure_attendance_mark_columns()
    except Exception as e:
        print(f"Error ensuring attendance mark columns: {str(e)}")

    run_schema_sync = os.getenv("RUN_SCHEMA_SYNC", "false").lower() == "true"
    if run_schema_sync:
        try:
            create_tables()
            add_missing_columns()
        except Exception as e:
            print(f"Error setting up database schema: {str(e)}")

@app.get("/")
def root():
    return {
        "message": "API Connect Successfully",
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
    }