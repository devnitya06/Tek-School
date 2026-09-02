# Student Tuition API Matrix - NEW vs REUSED

## Quick Reference: NEW APIs (Built for Student)

| # | Endpoint | Method | Purpose | Supports Both |
|---|----------|--------|---------|---------------|
| 1 | `/tuition/student/teachers` | GET | Browse available tuition batches | ✅ Student + SelfSignedStudent |
| 2 | `/tuition/student/batches/{batch_id}/join` | POST | Enroll in a batch | ✅ Student + SelfSignedStudent |
| 3 | `/tuition/student/my` | GET | List my enrollments | ✅ Student + SelfSignedStudent |
| 4 | `/tuition/student/batches/{batch_id}/study-plan` | GET | Get lesson plan | ✅ Student + SelfSignedStudent |
| 5 | `/tuition/student/lessons/{lesson_id}` | GET | View lesson with topics | ✅ Student + SelfSignedStudent |
| 6 | `/tuition/student/topics/{topic_id}` | GET | View topic content & files | ✅ Student + SelfSignedStudent |
| 7 | `/tuition/student/topics/{topic_id}/complete` | POST | Mark topic complete | ✅ Student + SelfSignedStudent |
| 8 | `/tuition/student/batches/{batch_id}/schedule` | GET | Get class schedule | ✅ Student + SelfSignedStudent |
| 9 | `/tuition/student/classes/{schedule_id}/join` | GET | Get meeting link | ✅ Student + SelfSignedStudent |
| 10 | `/tuition/student/batches/{batch_id}/assignments` | GET | List assignments | ✅ Student + SelfSignedStudent |
| 11 | `/tuition/student/dashboard` | GET | View dashboard | ✅ Student + SelfSignedStudent |

---

## REUSED APIs (Existing Assignment & Teacher APIs)

| # | Endpoint | Method | Purpose | Supports Both | Location |
|---|----------|--------|---------|---------------|----------|
| A | `/assignments/{assignment_id}/attempts` | POST | Submit assignment answers | ✅ Student + SelfSignedStudent | /assignments |
| B | `/teachers/{teacher_id}/ratings` | POST | Rate teacher 1-5 stars | ✅ Student + SelfSignedStudent | /teachers |
| C | `/assignments/{assignment_id}/attempts` | GET | View assignment attempts | ✅ Student + SelfSignedStudent | /assignments |
| D | `/assignments/attempts/history` | GET | Get attempt history | ✅ Student + SelfSignedStudent | /assignments |
| E | `/assignments/{assignment_id}/feedback` | POST | Submit chapter feedback | ✅ Student + SelfSignedStudent | /assignments |
| F | `/assignments/{assignment_id}/doubts` | POST | Ask questions | ✅ Student + SelfSignedStudent | /assignments |
| G | `/assignments/doubts/{doubt_id}/reply` | POST | Reply to doubt | ✅ Student + SelfSignedStudent | /assignments |
| H | `/assignments/{assignment_id}/report` | POST | Report issues | ✅ Student + SelfSignedStudent | /assignments |

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Student User (Web/Mobile)                       │
│                                                                       │
│  Regular Student (role: "student")          SelfSignedStudent        │
│  - user_id: int                              - user_id: int          │
│  - Student model in DB                       - SelfSignedStudent     │
│                                                model in DB            │
└──────────────────────┬──────────────────────────────────────┬────────┘
                       │                                      │
                       ▼                                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   Tuition Student API Layer                           │
│              (/tuition/student/*)                                    │
│                                                                       │
│  • Teachers & Batch Discovery                                        │
│  • Enrollment Management                                             │
│  • Study Plan & Curriculum                                           │
│  • Schedules & Live Classes                                          │
│  • Assignment Listing                                                │
│  • Dashboard                                                         │
│                                                                       │
│  [THIN LAYER - Reuses existing CRUD & Models]                       │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Existing Tuition CRUD Layer                        │
│              (/app/crud/tuition/*)                                   │
│                                                                       │
│  • Enrollment Verification                                           │
│  • Batch Queries & Lesson Plans                                      │
│  • Topic Progress Tracking                                           │
│  • Schedule Queries                                                  │
│  • Assignment Mapping                                                │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┬─────────────────┐
        │              │              │                 │
        ▼              ▼              ▼                 ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│TuitionBatch  │ │TuitionLesson │ │TopicProgress │ │TuitionBatch  │
│  Models      │ │   Models     │ │   Models     │ │ Schedule     │
│              │ │              │ │              │ │ Models       │
│ • id         │ │ • lesson_id  │ │student_id:id │ │              │
│ • batch_name │ │ • lesson_plan│ │self_signed_  │ │• class_date  │
│ • teacher_id │ │  _id         │ │  student_id: │ │• start_time  │
│ • self_signed│ │ • display_   │ │  id          │ │• topic       │
│  _teacher_id │ │  order       │ │• status      │ │• meeting_link│
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘

                               │
                               │ (Dual Support)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│          TuitionBatchStudentMapping (Enrollment)                     │
│                                                                       │
│  • batch_id: str                                                     │
│  • student_id: int (optional) ─────→ Links to Student                │
│  • self_signed_student_id: int (optional) ─→ Links to SelfSignedStud │
│  • enrollment_status: str                                            │
│  • payment_status: str                                               │
│  • joined_date: date                                                 │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Request Flow Example: Student Enrolls and Views Progress

```
CLIENT REQUEST:
┌────────────────────────────────────────────────────────────────────┐

1. Student logs in → Gets JWT token with role="student"

2. GET /tuition/student/teachers?board=cbse&class_id=12
   → Lists available batches

3. POST /tuition/student/batches/b_abc123/join
   → Creates TuitionBatchStudentMapping(
        batch_id="b_abc123",
        student_id=456,     ← Resolved from auth token
        enrollment_status="pending"
     )

4. GET /tuition/student/my
   → Queries TuitionBatchStudentMapping WHERE student_id=456
   → Returns batch summaries with progress aggregates

5. GET /tuition/student/batches/b_abc123/study-plan
   → Verifies enrollment (checks TuitionBatchStudentMapping)
   → Queries TuitionLesson, TuitionLessonTopic
   → Queries StudentTuitionTopicProgress WHERE student_id=456
   → Calculates completion % for each lesson

6. GET /tuition/student/topics/t_001
   → Gets TuitionLessonTopic with files and content
   → Queries StudentTuitionTopicProgress for status

7. POST /tuition/student/topics/t_001/complete
   → Creates/updates StudentTuitionTopicProgress(
        topic_id="t_001",
        student_id=456,
        status="completed",
        completed_at=datetime.now()
     )

8. GET /tuition/student/dashboard
   → Aggregates all enrollments and progress
   → Lists upcoming classes and assignments
   → Shows overall study metrics

└────────────────────────────────────────────────────────────────────┘
```

---

## SelfSignedStudent Flow (Identical)

```
Same as above, but:
- Role = "self_signed_student" (instead of "student")
- TuitionBatchStudentMapping uses self_signed_student_id (instead of student_id)
- StudentTuitionTopicProgress uses self_signed_student_id (instead of student_id)
- All query filtering changes accordingly
```

---

## Database Schema: Dual Support

```
TuitionBatchStudentMapping
├─ id: UUID (primary key)
├─ batch_id: str (FK → TuitionBatch)
├─ student_id: int (nullable, FK → Student)
├─ self_signed_student_id: int (nullable, FK → SelfSignedStudent)
├─ student_type: str ("student" or "self_signed_student")
├─ enrollment_status: str
├─ payment_status: str
├─ joined_date: date
└─ is_deleted: bool

StudentTuitionTopicProgress
├─ id: int (primary key)
├─ topic_id: str (FK → TuitionLessonTopic)
├─ student_id: int (nullable, FK → Student)
├─ self_signed_student_id: int (nullable, FK → SelfSignedStudent)
├─ student_type: str ("student" or "self_signed_student")
├─ status: str ("not_started", "in_progress", "completed")
├─ started_at: datetime
├─ completed_at: datetime
└─ created_at/updated_at: datetime
```

### Key Design:
- **One table supports both student types** (not separate tables)
- **Either `student_id` OR `self_signed_student_id` is set** (not both)
- **`student_type` field tracks which type** for clarity
- **All queries filter by the appropriate ID based on user role**

---

## Integration Points with Existing APIs

### 1. Assignment Submission
```
Student uses: POST /assignments/{assignment_id}/attempts
└─ Existing API already supports student_user_id
└─ No changes needed
└─ StudentAssignmentAttempt model records the user
```

### 2. Teacher Rating
```
Student uses: POST /teachers/{teacher_id}/ratings
└─ Existing API already checks role: [UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]
└─ TeacherRating model records teacher_user_id → student_user_id
└─ Rating aggregates stored in Teacher or computed on query
```

### 3. Assignment Feedback & Doubts
```
Student uses: 
  - POST /assignments/{assignment_id}/feedback
  - POST /assignments/{assignment_id}/doubts
  - POST /assignments/doubts/{doubt_id}/reply
└─ Existing APIs already support both student roles
└─ ChapterFeedback and AssignmentDoubt models track student_user_id
```

---

## Summary: NEW vs REUSED

| Category | Count | Details |
|----------|-------|---------|
| **NEW Student APIs** | 11 | Thin layer for discovery, enrollment, study tracking, dashboard |
| **REUSED Assignment APIs** | 8 | Submission, feedback, doubts, reporting (already dual-role) |
| **NEW Database Tables** | 1 | StudentTuitionTopicProgress (for progress tracking) |
| **MODIFIED Database Tables** | 0 | (Existing models already support dual IDs) |
| **New CRUD Modules** | 1 | app/crud/tuition/student.py |
| **New Route Modules** | 1 | app/routes/tuition/student.py |
| **New Schema Modules** | 1 | app/schemas/tuition/student.py |

---

## Testing Workflow

```
Test Student Flow:
  1. Login as Student (role=student)
  2. Call all 11 NEW endpoints
  3. Call assignment/teacher/doubt endpoints (REUSED)
  4. Verify data consistency across tables

Test SelfSignedStudent Flow:
  1. Login as SelfSignedStudent (role=self_signed_student)
  2. Repeat steps 2-4 with self_signed_student_id references
  3. Verify RBAC correctly blocks non-student access

Test Mixed Scenarios:
  1. One student enrolled in multiple batches
  2. Multiple students in same batch
  3. Assignment attempts alongside topic progress
  4. Dashboard aggregates across batches
```

---

Generated: 2026-09-01
Version: 1.0
