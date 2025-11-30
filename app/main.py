from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import users, auth, school, teachers, students, admin, selfsignedstudents, staff
from app.core.config import settings
from app.db.session import create_tables, add_missing_columns

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
app.include_router(selfsignedstudents.router, prefix="/api", tags=["SelfSignedStudents"])


@app.on_event("startup")
def on_startup():
    """Called when FastAPI starts - creates tables and adds missing columns"""
    try:
        create_tables()  # This creates any missing tables
        
        add_missing_columns()  # This adds any missing columns to existing tables
        
    except Exception as e:
        print(f"Error setting up database schema: {str(e)}")
        # In production, you might want to handle this differently
        # For development, we'll just log the error and continue

@app.get("/")
def root():
    return {"message": "API Connect Successfully"}