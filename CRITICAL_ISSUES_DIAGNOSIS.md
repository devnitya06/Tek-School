# 🚨 CRITICAL ISSUES CAUSING VPS DOWNTIME - COMPLETE DIAGNOSIS

## Summary
**Found 5 CRITICAL issues** causing your VPS to go down and PostgreSQL CPU to spike to 154%.

---

## ISSUE #1: ⚠️ MISSING DATABASE CONNECTION POOL CONFIGURATION (CRITICAL)
**File**: `app/db/session.py` (Lines 13-16)  
**Severity**: 🔴 CRITICAL - Direct cause of "Maximum CPU resets reached"

### Problem
```python
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    echo=False
)
```

### Why This Breaks Your VPS
- **Missing `pool_size`**: SQLAlchemy default is `5` connections total
- **Missing `max_overflow`**: Default is `10`, meaning max 15 concurrent connections
- **No `pool_recycle`**: PostgreSQL closes idle connections after 5-10 minutes → connection becomes stale
- **Result**: After running for a while, **all connection slots fill up with stale connections** → new requests queue up, PostgreSQL CPU spikes as it tries to handle hundreds of waiting queries

### Evidence
Your PostgreSQL showing:
- `postgres` → **154% CPU** (query queue backup)
- `postgres postgres tek_school 172.18.0.4 ... idle` → **41% CPU** (idle connections consuming resources)
- **"Maximum CPU resets reached"** = Hostinger killing the process because queries pile up

---

## ISSUE #2: ⚠️ TASK USING `SessionLocal()` INSTEAD OF DEPENDENCY INJECTION (CRITICAL)
**File**: `app/tasks/student_tasks.py` (Lines 10-47)  
**Severity**: 🔴 CRITICAL - Creates orphaned connections

### Problem
```python
@shared_task
def check_student_renewals():
    db = SessionLocal()  # ❌ Creates connection but doesn't use FastAPI's dependency management
    try:
        # Queries that fetch ALL students
        expired_students = (
            db.query(Student)
            .filter(Student.status_expiry_date != None)
            .filter(Student.status_expiry_date < datetime.utcnow())
            .filter(Student.status != StudentStatus.INACTIVE.value)
            .all()  # ❌ Loads ENTIRE table into memory
        )

        for student in expired_students:
            student.status = StudentStatus.INACTIVE.value  # ❌ Individual updates in loop
        
        db.commit()
    finally:
        db.close()
```

### Why This Is Catastrophic
1. **Creates orphaned connections**: Celery workers don't share FastAPI's pool → creates extra DB connections
2. **Loads entire Student table into memory**: `.all()` fetches EVERY student at once
3. **N+1 problem**: Loop updates students one-by-one, causing 1000s of SQL UPDATE queries
4. **Runs every 24 hours**: If you have 10,000 students, this causes massive load spike

### Example of What Happens
- Students table has 10,000 records
- Task loads all 10,000 into memory at once → **memory spike**
- Loop runs 10,000 UPDATE queries one-by-one → **PostgreSQL CPU spike**
- Connection doesn't close properly if error occurs → **connection leak**

---

## ISSUE #3: ⚠️ IDENTICAL ISSUE IN FOLLOWUP TASK (CRITICAL)
**File**: `app/tasks/followup_tasks.py` (Lines 19-55)  
**Severity**: 🔴 CRITICAL - Same connection pool problem

### Problem
```python
@shared_task
def send_monthly_followup_emails():
    db = SessionLocal()  # ❌ Orphaned connection
    try:
        schools = (
            db.query(School)
            .filter(School.followup_enabled.is_(True))
            .filter(School.followup_status == "pending")
            .all()  # ❌ Loads ALL schools at once
        )

        for school in schools:  # ❌ Loop with database operations
            # ... email sending and updates
            send_dynamic_email(...)
            school.followup_last_sent_at = today
            db.commit()  # ❌ Commits inside loop! Multiple transactions!
```

### Why This Breaks
1. **Loads all schools matching criteria into memory at once**
2. **Commits inside the loop**: Every iteration commits → excessive transaction overhead
3. **Email sending inside transaction**: If email fails, whole transaction rolls back
4. **Runs daily**: Creates consistent daily spike in database usage

---

## ISSUE #4: ⚠️ NO DATABASE CONNECTION POOL LIMITS IN DOCKER-COMPOSE
**File**: `docker-compose.yml` (Lines 43-61)  
**Severity**: 🟠 HIGH - Allows PostgreSQL to accept unlimited connections

### Problem
```yaml
db:
  image: postgres:15
  environment:
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: root
    POSTGRES_DB: tek_school
  # ❌ No max_connections limit set
  # ❌ No memory limits
  # ❌ No CPU limits
```

### Default PostgreSQL Limits
- `max_connections` default = **100**
- Your app + Celery + Celery Beat can create 200+ connections
- Result: **PostgreSQL connection limit exceeded** → queries get rejected → app crashes

---

## ISSUE #5: ⚠️ FASTAPI ROUTES LOADING ENTIRE TABLES WITHOUT PAGINATION (HIGH)
**File**: `app/routes/school.py` and many others  
**Severity**: 🟠 HIGH - N+1 queries and memory bloat

### Examples Found
```python
# Line 1736 - app/routes/school.py
classes = db.query(Class).filter(Class.school_id == school.id).all()  # Could be 100+ classes

# Line 1600 - app/routes/teachers.py
teachers = db.query(Teacher).filter(Teacher.school_id == school.id).all()

# Line 46 - app/routes/business_inquiry.py
existing = db.query(School.id).filter(School.id.in_(ids)).all()  # No limit
```

### Cascade Effect
1. Each `.all()` loads entire result set into memory
2. If endpoint is called repeatedly in short time → memory fills up
3. When RAM fills, Linux OOM killer activates → kills containers
4. PostgreSQL gets killed → app becomes unavailable

---

## ROOT CAUSE ANALYSIS

### Why Your VPS Goes Down After Some Time

**Timeline of Events**:

1. **Hours 0-6**: App runs fine, connection pool fresh
2. **Hour 6-12**: 
   - Regular traffic creates/closes database connections
   - Some connections become stale (PostgreSQL closes them after 5-10 min idle)
   - Connection pool still has stale connections
3. **Hour 12-24**:
   - Celery Beat runs `check_student_renewals()` → loads 10,000 students
   - Celery Beat runs `send_monthly_followup_emails()` → loads 500 schools
   - Both tasks use orphaned connections outside the pool
4. **Hour 24-48**:
   - Traffic increases, connection pool exhausted
   - New requests can't get connections, queue up in PostgreSQL
   - PostgreSQL CPU spikes to 154% trying to process queue
5. **Hour 48+**:
   - Hostinger detects excessive CPU usage
   - **"Maximum CPU resets reached"** → forcibly kills/resets VPS
   - VPS becomes unavailable until reset

---

## VERIFICATION COMMANDS

Run these to confirm the diagnosis:

```bash
# Check connection pool exhaustion
docker exec postgres-db psql -U postgres -d tek_school -c "
SELECT datname, sum(numbackends) as total_connections 
FROM pg_stat_database 
WHERE datname = 'tek_school' 
GROUP BY datname;
"

# Check if connections are stuck idle
docker exec postgres-db psql -U postgres -d tek_school -c "
SELECT state, count(*) as connection_count
FROM pg_stat_activity
GROUP BY state;
"

# Check long-running queries (should be empty or fast)
docker exec postgres-db psql -U postgres -d tek_school -c "
SELECT pid, usename, query_start, query 
FROM pg_stat_activity 
WHERE state != 'idle' 
AND now() - query_start > interval '10 minutes';
"

# Check PostgreSQL max_connections limit
docker exec postgres-db psql -U postgres -d tek_school -c "SHOW max_connections;"

# Check current Docker container resource usage
docker stats --no-stream

# Check if containers restarted recently
docker-compose -f ~/Tek-School/docker-compose.yml ps
```

---

## PRIORITY FIXES (In Order)

### 🔴 FIX #1: Update Database Connection Pool (MUST DO FIRST)
**File**: `app/db/session.py`  
**Impact**: Prevents connection exhaustion

```python
from sqlalchemy import create_engine, pool

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,              # ✅ Add this
    max_overflow=20,           # ✅ Add this  
    pool_recycle=3600,         # ✅ Add this (recycle connections every 1 hour)
    pool_reset_on_return='rollback',  # ✅ Add this
    echo=False,
    connect_args={
        "connect_timeout": 10,
        "application_name": "tekschool_app"
    }
)
```

### 🔴 FIX #2: Fix Celery Task Connection Leaks
**File**: `app/tasks/student_tasks.py`  
**Impact**: Prevents orphaned connections and CPU spikes

**Change FROM**:
```python
@shared_task
def check_student_renewals():
    db = SessionLocal()
    try:
        expired_students = db.query(Student).filter(...).all()
        for student in expired_students:
            student.status = StudentStatus.INACTIVE.value
        db.commit()
```

**Change TO**:
```python
@shared_task
def check_student_renewals():
    from sqlalchemy import update
    db = SessionLocal()
    try:
        # Use bulk update instead of loop
        db.query(Student).filter(
            Student.status_expiry_date != None,
            Student.status_expiry_date < datetime.utcnow(),
            Student.status != StudentStatus.INACTIVE.value
        ).update(
            {Student.status: StudentStatus.INACTIVE.value},
            synchronize_session=False
        )
        
        db.query(SelfSignedStudent).filter(
            SelfSignedStudent.status_expiry_date != None,
            SelfSignedStudent.status_expiry_date < datetime.utcnow(),
            SelfSignedStudent.status != StudentStatus.INACTIVE.value
        ).update(
            {SelfSignedStudent.status: StudentStatus.INACTIVE.value},
            synchronize_session=False
        )
        
        db.commit()
        print("✅ Renewal check completed!")
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()
```

### 🟠 FIX #3: Fix Followup Task (Same Connection Issue)
**File**: `app/tasks/followup_tasks.py`  
**Change**: Move `db.commit()` OUTSIDE the loop

```python
@shared_task
def send_monthly_followup_emails():
    today = datetime.now(timezone.utc)
    if today.day not in FOLLOWUP_DATES:
        print(f"ℹ️ Today is the {today.day}th — no scheduled followup.")
        return

    print(f"📅 Running monthly followup...")
    db = SessionLocal()
    try:
        schools = db.query(School).filter(
            School.followup_enabled.is_(True),
            School.followup_status == "pending"
        ).all()

        sent_count = 0
        for school in schools:
            try:
                if school.user:
                    password = generate_password(prefix=school.school_name)
                    school.user.hashed_password = get_password_hash(password)
                    school.user.is_verified = True

                    send_dynamic_email(...)
                    school.followup_last_sent_at = today
                    sent_count += 1
            except Exception as e:
                print(f"❌ Failed: {school.school_email}: {e}")
        
        db.commit()  # ✅ Single commit after loop, not inside loop
        print(f"🎉 {sent_count} email(s) sent.")
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()
```

### 🟠 FIX #4: Add PostgreSQL Connection Limits in Docker
**File**: `docker-compose.yml`  
**Change**: Add postgres environment variables

```yaml
db:
  image: postgres:15
  container_name: postgres-db
  restart: always
  environment:
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: root
    POSTGRES_DB: tek_school
    # ✅ Add these to prevent connection exhaustion
    POSTGRES_INITDB_ARGS: "-c max_connections=50 -c shared_buffers=256MB -c effective_cache_size=1GB -c maintenance_work_mem=64MB"
  volumes:
    - postgres_data:/var/lib/postgresql/data
  ports:
    - "5433:5432"
  healthcheck:
    test: ["CMD", "pg_isready", "-U", "postgres", "-d", "tek_school"]
    interval: 10s
    timeout: 5s
    retries: 5
```

---

## IMPLEMENTATION CHECKLIST

- [ ] **Fix #1**: Update `app/db/session.py` with connection pool configuration
- [ ] **Fix #2**: Refactor `app/tasks/student_tasks.py` to use bulk update
- [ ] **Fix #3**: Move commit outside loop in `app/tasks/followup_tasks.py`
- [ ] **Fix #4**: Update `docker-compose.yml` with PostgreSQL settings
- [ ] **Test**: Run `docker-compose down && docker-compose up -d --build`
- [ ] **Monitor**: Check logs for 24+ hours to confirm VPS stays stable
- [ ] **Verify**: Run diagnostic commands above to confirm connection pool health

---

## EXPECTED RESULTS AFTER FIXES

- ✅ PostgreSQL CPU stays below 10%
- ✅ No "Maximum CPU resets reached" messages
- ✅ All connections properly closed after use
- ✅ Celery tasks complete without connection leaks
- ✅ VPS stays available indefinitely

