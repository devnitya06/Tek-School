from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import time as _time
from sqlalchemy.exc import OperationalError, TimeoutError as SATimeoutError
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

# ─── CPU Load-Shedding Middleware ─────────────────────────────────────────────
# When system CPU exceeds 90%, reject new requests immediately with 503.
# This prevents the server from accepting more work when already overloaded,
# which would only make recovery slower.
#
# CPU is sampled every 5 seconds (cached) so psutil doesn't run on every request.

_CPU_SHED_THRESHOLD = 90.0   # % — start rejecting requests above this
_CPU_SAMPLE_INTERVAL = 5.0   # seconds between CPU samples
_cpu_cache: dict = {"value": 0.0, "at": 0.0}  # module-level cache

# Paths that must always work — healthcheck, docs, monitoring
_ALWAYS_ALLOW = {"/", "/docs", "/redoc", "/openapi.json", "/health"}


class CPULoadSheddingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Always allow health/docs endpoints through
        if request.url.path in _ALWAYS_ALLOW:
            return await call_next(request)

        # Re-sample CPU only if the cache has expired
        now = _time.monotonic()
        if now - _cpu_cache["at"] >= _CPU_SAMPLE_INTERVAL:
            try:
                import psutil
                _cpu_cache["value"] = psutil.cpu_percent(interval=None)
            except Exception:
                _cpu_cache["value"] = 0.0  # psutil unavailable — don't block
            _cpu_cache["at"] = now

        if _cpu_cache["value"] >= _CPU_SHED_THRESHOLD:
            from app.core.logger import logger
            logger.warning(
                "[LOAD_SHED] CPU=%.1f%% — rejecting %s %s",
                _cpu_cache["value"], request.method, request.url.path,
            )
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "message": (
                        "The server is currently under high load. "
                        "Please wait a moment and try again."
                    ),
                    "retry_after_seconds": 10,
                },
                headers={"Retry-After": "10"},
            )

        return await call_next(request)


app.add_middleware(CPULoadSheddingMiddleware)

# ─── Global Exception Handlers (5xx server errors only) ───────────────────────
# 4xx errors (404, 401, 403, 422, etc.) are left as-is — FastAPI handles them.
# Only server-side failures are caught here and returned as clean JSON.


@app.exception_handler(OperationalError)
async def db_operational_error_handler(request: Request, exc: OperationalError):
    """Catch DB connection failures and statement/lock timeouts from Postgres."""
    from app.core.logger import logger
    msg = str(exc.orig) if exc.orig else str(exc)
    # statement_timeout fires with 'canceling statement due to statement timeout'
    if "statement timeout" in msg.lower():
        logger.warning("[DB] Statement timeout on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "message": "This request took too long to process. Please try again in a moment.",
            },
        )
    # lock_timeout fires with 'canceling statement due to lock timeout'
    if "lock timeout" in msg.lower():
        logger.warning("[DB] Lock timeout on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "message": "The server is temporarily busy. Please try again in a few seconds.",
            },
        )
    # Generic DB connection failure
    logger.error("[DB] OperationalError on %s %s: %s", request.method, request.url.path, msg)
    return JSONResponse(
        status_code=503,
        content={
            "success": False,
            "message": "Database is temporarily unavailable. Please try again shortly.",
        },
    )


@app.exception_handler(SATimeoutError)
async def db_timeout_handler(request: Request, exc: SATimeoutError):
    """SQLAlchemy connection pool timeout — all DB connections were busy."""
    from app.core.logger import logger
    logger.error("[DB] Pool timeout on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=503,
        content={
            "success": False,
            "message": "Server is under high load. Please try again in a moment.",
        },
    )




@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all for any error that wasn't handled above — never expose a raw traceback."""
    from app.core.logger import logger
    logger.exception(
        "[UNHANDLED] %s on %s %s", type(exc).__name__, request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "An unexpected error occurred. Our team has been notified. Please try again later.",
        },
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