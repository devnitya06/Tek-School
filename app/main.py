from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import users, auth, school, teachers, students, admin, selfsignedstudents, selfsignedteachers, staff, workers, exams, business_inquiry, progress_reports, academic_results, admin_sessions, news, placement
from app.routes import prospectus as prospectus_routes
from app.routes.assignments.assignment_routes import router as assignment_routes
from app.routes.tuition.lesson_plans import router as tuition_lesson_plan_router
from app.routes.tuition.teaching_setup import router as tuition_teaching_setup_router
from app.routes.tuition.class_sessions import router as tuition_class_session_router
from app.routes.tuition.student import router as tuition_student_router
from app.core.config import settings
from app.utils.cpu_monitor import start_cpu_monitor
from app.db.session import (
    create_tables,
    add_missing_columns,
    ensure_attendance_mark_columns,
    ensure_attendance_verified_at_column,
    ensure_attendance_qr_source_columns,
    ensure_attendance_qr_token_columns,
    ensure_staff_compensation_tables,
    ensure_staff_school_id_nullable,
    ensure_staff_teacher_boss_columns,
    ensure_school_settlement_schema,
    ensure_school_followup_columns,
    ensure_school_claim_columns,
    ensure_self_signed_student_teacher_id_column,
    ensure_self_signed_teacher_teaching_configuration_table,
    ensure_self_signed_student_additional_columns,
    ensure_assignment_tables,
    ensure_tuition_teaching_setup_schema,
    ensure_tuition_class_session_schema,
    ensure_worker_payment_settlement_columns,
    ensure_academic_results_tables,
    ensure_progress_report_tables,
    ensure_placement_schema,
    ensure_studentstatus_pending_enum_value,
    ensure_school_facility_enum_columns,
    ensure_excellent_student_schema,
    ensure_digital_prospectus_schema,
    ensure_class_fee_schema,
)
import os
app = FastAPI(title=settings.PROJECT_NAME)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
app.include_router(admin_sessions.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(staff.router, prefix="/staff", tags=["Staff"])
app.include_router(workers.router, prefix="/worker", tags=["Workers"])
app.include_router(selfsignedstudents.router, prefix="/api", tags=["SelfSignedStudents"])
app.include_router(selfsignedteachers.router, prefix="/api", tags=["SelfSignedTeachers"])
app.include_router(exams.router,prefix="/exam",tags=["Exam"])
app.include_router(business_inquiry.router, prefix="/inquiry", tags=["Business Inquiry"])
app.include_router(progress_reports.router, prefix="/progress-reports", tags=["Progress Reports"])
app.include_router(academic_results.router, prefix="/academic-results", tags=["Academic Results"])
app.include_router(news.router, tags=["News"])
app.include_router(placement.router, tags=["Placement"])
app.include_router(placement.public_router, tags=["Public Placement"])
app.include_router(assignment_routes, tags=["Assignments"])
app.include_router(tuition_lesson_plan_router)
app.include_router(tuition_teaching_setup_router)
app.include_router(tuition_class_session_router)
app.include_router(tuition_student_router)
app.include_router(prospectus_routes.router)

@app.on_event("startup")
def on_startup():
    # Allow skipping heavy DB/schema startup work when debugging locally.
    if os.getenv("SKIP_STARTUP_SCHEMA", "false").lower() == "true":
        print("Skipping startup schema operations due to SKIP_STARTUP_SCHEMA=true")
        return
    # Always ensure attendance mark-in/out columns exist.
    # Prevents runtime failures when code is updated before a manual migration.
    try:
        ensure_school_facility_enum_columns()
        ensure_studentstatus_pending_enum_value()
        # Ensure assignmentstatus enum labels include required values used by the code
        from app.db.session import ensure_assignmentstatus_enum_values
        ensure_assignmentstatus_enum_values()
        ensure_attendance_mark_columns()
        ensure_attendance_verified_at_column()
        ensure_attendance_qr_source_columns()
        ensure_attendance_qr_token_columns()
        ensure_staff_compensation_tables()
        ensure_staff_school_id_nullable()
        ensure_staff_teacher_boss_columns()
        ensure_school_settlement_schema()
        ensure_worker_payment_settlement_columns()
        ensure_self_signed_student_teacher_id_column()
        ensure_self_signed_teacher_teaching_configuration_table()
        ensure_self_signed_student_additional_columns()
        ensure_tuition_teaching_setup_schema()
        ensure_tuition_class_session_schema()
        ensure_school_followup_columns()
        ensure_school_claim_columns()
        ensure_excellent_student_schema()
        ensure_digital_prospectus_schema()
        ensure_class_fee_schema()
        create_tables()
        ensure_assignment_tables()
        ensure_academic_results_tables()
        ensure_progress_report_tables()
        ensure_placement_schema()
    except Exception as e:
        print(f"Error ensuring runtime schema requirements: {str(e)}")

    run_schema_sync = os.getenv("RUN_SCHEMA_SYNC", "false").lower() == "true"
    if run_schema_sync:
        try:
            create_tables()
            add_missing_columns()
        except Exception as e:
            print(f"Error setting up database schema: {str(e)}")

    # ℹ️ CPU monitor: logs only when CPU > 85% (not normal load)
    start_cpu_monitor(threshold_percent=85.0, interval_seconds=60)

@app.get("/")
def root():
    return {
        "message": "API Connect Successfully",
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
    }