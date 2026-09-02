# Student Tuition Module Phase 1 — API Implementation Matrix

**Date:** 2026-09-01  
**Scope:** Student Learning/Enrollment Experience (No Payment)  
**Base Path:** `/tuition/student/`

---

## Executive Summary

Based on thorough analysis of the existing Tek-School codebase, the Student Tuition Phase 1 can be built with **~12-15 NEW endpoints** plus extensive **REUSE of existing Teacher, Assignment, and Lesson Plan APIs**.

### Key Findings

| Category | Status | Details |
|----------|--------|---------|
| **Enrollment** | NEW | 2 endpoints needed (join, list) |
| **Study Plan** | REUSE + NEW | Read APIs exist; need student-scoped access |
| **Lessons/Topics** | REUSE + NEW | Exist for teachers; wrap with student auth |
| **Topic Progress** | NEED MODEL | No existing student progress model |
| **Schedules** | REUSE | `TuitionBatchSchedule` exists; filter by student |
| **Assignments** | REUSE | `POST /assignments/{id}/attempts` exists |
| **Tests/Exams** | NEED NEW | No tuition-specific test model; use StudentExamData |
| **Questions to Teacher** | REUSE | Assignment doubts system can work |
| **Rating** | REUSE | `POST /teachers/{id}/ratings` exists |
| **Dashboard** | NEW | Aggregate endpoint |

---

## SECTION 1: TEACHER DISCOVERY (Can Mostly Reuse)

### 1.1 List Available Teachers/Batches
**Requirement:** Student discovers teachers and their tuition batches by board/class/subject

#### Options:
**Option A (Preferred): Reuse existing teacher discovery APIs**
- Existing: `GET /tuition/teaching-setups/` (needs to be made public/filterable)
- Status: Teaching setups = tuition batches
- Need: Add public list endpoint with filters

**Option B: Create new student-specific endpoint**
```
GET /tuition/student/teachers
GET /tuition/student/teachers?board=cbse&class=12&subject=Math
```

**Recommendation:** Create one new wrapper endpoint that reuses teaching setup queries.

---

## SECTION 2: ENROLLMENT (NEW ENDPOINTS)

### 2.1 Join Tuition Batch
```
POST /tuition/student/batches/{batch_id}/join
```
**Purpose:** Student enrolls in a tuition batch  
**Model Used:** `TuitionBatchStudentMapping` (already exists)  
**Request Body:**
```json
{}  // Empty for Phase 1 (payment in Phase 2)
```
**Response:**
```json
{
  "enrollment_id": "BSM-123456",
  "batch_id": "ID-ABC123",
  "student_id": 42,
  "enrollment_status": "PENDING",
  "joined_date": "2026-09-01"
}
```
**Validation:**
- Authenticate student
- Check batch exists & is active
- Check student not already enrolled
- Check batch capacity (if enforced)
- Create/use `TuitionBatchStudentMapping`

**Status:** ✅ **MUST CREATE**

---

### 2.2 List My Enrollments
```
GET /tuition/student/my
GET /tuition/student/enrollments
```
**Purpose:** Student sees all tuition batches they're enrolled in  
**Returns:**
```json
[
  {
    "enrollment_id": "BSM-123456",
    "batch_id": "ID-ABC123",
    "batch_name": "Advanced Physics",
    "teacher_name": "Dr. John Doe",
    "board": "CBSE",
    "class": "12",
    "subject": "Physics",
    "enrollment_status": "APPROVED",
    "status": "active",
    "schedule": {
      "start_date": "2026-08-15",
      "end_date": "2026-12-31",
      "days": ["Monday", "Wednesday", "Friday"],
      "time": "6:00 PM - 7:00 PM"
    },
    "progress": {
      "lessons_completed": 5,
      "lessons_total": 12,
      "topics_completed": 18,
      "topics_total": 45,
      "completion_percentage": 40
    }
  }
]
```
**Query Params:**
- `status` - filter by enrollment_status (PENDING, APPROVED, REJECTED)
- `board`, `class`, `subject` - filter by curriculum
- `page`, `page_size` - pagination

**Reuse:** Query `TuitionBatchStudentMapping` + join `TuitionBatch`, `TuitionLessonPlan`

**Status:** ✅ **MUST CREATE**

---

## SECTION 3: STUDY PLAN / CURRICULUM (Reuse + Wrap)

### 3.1 Get Batch Study Plan
```
GET /tuition/student/batches/{batch_id}/study-plan
```
**Purpose:** View full curriculum for an enrolled batch  
**Returns:**
```json
{
  "batch_id": "ID-ABC123",
  "lesson_plan_id": "LP-999",
  "subject": "Physics",
  "board": "CBSE",
  "class": "12",
  "lessons": [
    {
      "lesson_id": "LSN-001",
      "lesson_number": 1,
      "lesson_title": "Motion in One Dimension",
      "topics_count": 5,
      "topics_completed": 2,
      "completion_percentage": 40
    }
  ]
}
```
**Reuse:** Existing `TuitionLessonPlan` CRUD; wrap with student enrollment check

**Status:** ⚠️ **WRAP EXISTING (1 new endpoint)**

---

### 3.2 Get Lesson Details
```
GET /tuition/student/lessons/{lesson_id}
```
**Purpose:** View lesson title, topics, and progress  
**Returns:**
```json
{
  "lesson_id": "LSN-001",
  "lesson_title": "Motion in One Dimension",
  "lesson_objective": "...",
  "topics": [
    {
      "topic_id": "TOP-001",
      "topic_title": "Velocity and Acceleration",
      "status": "not_started"  // or "in_progress" / "completed"
    }
  ]
}
```
**Validation:** Verify student enrolled in batch containing lesson

**Reuse:** Existing `GET /tuition/lesson-plans/lessons/{lesson_id}` + student auth filter

**Status:** ⚠️ **WRAP EXISTING (1 new endpoint)**

---

### 3.3 Get Topic Details
```
GET /tuition/student/topics/{topic_id}
```
**Purpose:** View topic content, videos, files, assignments  
**Returns:**
```json
{
  "topic_id": "TOP-001",
  "topic_title": "Velocity and Acceleration",
  "topic_content": "...",
  "reference_video_link": "https://youtube.com/...",
  "files": [
    {
      "file_id": "FIL-001",
      "file_name": "Chapter 1 Notes.pdf",
      "file_url": "https://s3.../...",
      "file_type": "pdf"
    }
  ],
  "assignments": [
    {
      "assignment_id": 42,
      "assignment_title": "Motion Problems"
    }
  ],
  "student_progress": {
    "status": "in_progress",
    "started_at": "2026-09-01T10:00:00Z",
    "completed_at": null
  }
}
```
**Reuse:** Existing `GET /tuition/lesson-plans/topics/{topic_id}` + files

**Status:** ⚠️ **WRAP EXISTING (1 new endpoint)**

---

### 3.4 Mark Topic as Completed
```
POST /tuition/student/topics/{topic_id}/complete
```
**Purpose:** Student marks topic as done  
**Request Body:**
```json
{}
```
**Response:**
```json
{
  "topic_id": "TOP-001",
  "status": "completed",
  "completed_at": "2026-09-01T10:30:00Z"
}
```
**Logic:**
- Check student enrolled in batch
- Create/update student topic progress record
- Idempotent (calling twice = same result)

**Model Needed:** ❓ `StudentTuitionTopicProgress` (NEW MODEL)

**Status:** ✅ **MUST CREATE** (requires new model)

---

## SECTION 4: BATCHES & SCHEDULES (Mostly Reuse)

### 4.1 Get Batch Schedule
```
GET /tuition/student/batches/{batch_id}/schedule
```
**Purpose:** See upcoming and past class sessions  
**Query Params:**
- `from_date`, `to_date` - filter by date range
- `status` - scheduled, completed, cancelled

**Returns:**
```json
[
  {
    "schedule_id": "SCH-001",
    "class_date": "2026-09-03",
    "start_time": "18:00",
    "end_time": "19:00",
    "topic": "Velocity Calculations",
    "meeting_link": "https://meet.google.com/...",
    "meeting_link_override": null,
    "status": "scheduled"
  },
  {
    "schedule_id": "SCH-002",
    "class_date": "2026-09-01",
    "start_time": "18:00",
    "end_time": "19:00",
    "topic": "Introduction to Motion",
    "meeting_link": "https://meet.google.com/...",
    "status": "completed",
    "class_summary": "Covered basics of motion and velocity concepts"
  }
]
```
**Reuse:** Query `TuitionBatchSchedule` + `TuitionClassDoneRecord`

**Status:** ⚠️ **WRAP EXISTING (1 new endpoint)**

---

### 4.2 Join Live Class
```
GET /tuition/student/classes/{schedule_id}/join
```
**Purpose:** Get meeting link for live class  
**Returns:**
```json
{
  "schedule_id": "SCH-001",
  "class_date": "2026-09-03",
  "meeting_provider": "google_meet",
  "meeting_link": "https://meet.google.com/abc-def-ghi"
}
```
**Validation:**
- Student enrolled
- Schedule belongs to student's batch
- Class not in past (or allow with warning)

**Status:** ✅ **MUST CREATE** (simple wrapper)

---

## SECTION 5: ASSIGNMENTS (Mostly Reuse)

### 5.1 List Batch Assignments
```
GET /tuition/student/batches/{batch_id}/assignments
```
**Purpose:** See assignments for this batch  
**Returns:**
```json
[
  {
    "assignment_id": 42,
    "title": "Motion Problems Set 1",
    "chapter": "Motion",
    "topic_ids": ["TOP-001", "TOP-002"],
    "question_count": 5,
    "due_date": "2026-09-05",
    "status": "published",
    "student_attempt_status": "not_attempted"  // or "in_progress" / "submitted" / "graded"
  }
]
```
**Reuse:** `TuitionLessonAssignmentMapping` to find assignments; query `Assignment`

**Status:** ⚠️ **WRAP EXISTING (1 new endpoint)**

---

### 5.2 Get Assignment Details
```
GET /tuition/student/assignments/{assignment_id}
```
**Purpose:** Full assignment details (questions, files, etc.)  
**Reuse:** Existing `GET /assignments/{id}` with auth check (student enrolled)

**Status:** ⚠️ **WRAP EXISTING**

---

### 5.3 Submit Assignment
```
POST /tuition/student/assignments/{assignment_id}/attempt
```
**Purpose:** Student submits assignment  
**Reuse:** **DIRECT REUSE** of existing `POST /assignments/{id}/attempts`

```
POST /assignments/{assignment_id}/attempts
{
  "submitted_answers": {
    "1": "A",
    "2": "B"
  }
}
```
**Note:** No wrapping needed if endpoint already supports student identification

**Status:** ✅ **REUSE (no new endpoint)**

---

### 5.4 Get Assignment Result
```
GET /tuition/student/assignments/{assignment_id}/result
```
**Reuse:** `GET /assignments/{id}/my-results`

**Status:** ✅ **REUSE (no new endpoint)**

---

### 5.5 Ask Teacher / Doubts
```
POST /tuition/student/assignments/{assignment_id}/doubts
GET /tuition/student/assignments/{assignment_id}/doubts
POST /tuition/student/assignments/{assignment_id}/doubts/{doubt_id}/reply
```
**Reuse:** Existing assignment doubts system

**Status:** ✅ **REUSE (no new endpoints)**

---

## SECTION 6: TESTS / EXAMS (Partial Reuse, Needs Investigation)

### 6.1 List Batch Tests
```
GET /tuition/student/batches/{batch_id}/tests
```
**Problem:** Existing test/exam system is school-focused, not tuition-specific  
**Options:**
- **Option A:** Create new `TuitionTest` model (complex)
- **Option B:** Link `Assignment` as test (reuse assignment submission)
- **Option C:** Skip for Phase 1 (wait for Phase 2 requirements)

**Current Status:** ❓ **UNCLEAR** — Need clarification on test model

**Recommendation:** Check if `StudentExamData` model can be reused or create minimal `TuitionAssignment` variant

**Status:** ❓ **TBD (requires architecture decision)**

---

## SECTION 7: TEACHER INTERACTION

### 7.1 Rate Teacher
```
POST /tuition/student/teachers/{teacher_id}/rating
```
**Reuse:** Existing `POST /teachers/{id}/ratings`

**Status:** ✅ **REUSE (no new endpoint)**

---

### 7.2 Ask Teacher Questions
```
POST /tuition/student/teachers/{teacher_id}/questions
GET /tuition/student/teachers/{teacher_id}/questions
```
**Note:** Can use assignment doubts system OR create simple message model

**Status:** ⚠️ **REUSE doubts system OR CREATE simple messaging (Phase 1: Optional)**

---

## SECTION 8: DASHBOARD (NEW)

### 8.1 Student Dashboard
```
GET /tuition/student/dashboard
```
**Purpose:** Aggregate overview  
**Returns:**
```json
{
  "active_tuitions": 3,
  "tuitions": [
    {
      "batch_name": "Physics Advanced",
      "teacher": "Dr. Doe",
      "progress": 40
    }
  ],
  "upcoming_classes": [
    {
      "class_date": "2026-09-03",
      "subject": "Physics",
      "time": "6:00 PM"
    }
  ],
  "recent_assignments": [...],
  "study_progress": {
    "topics_completed": 18,
    "topics_total": 45
  }
}
```
**Status:** ✅ **MUST CREATE**

---

## IMPLEMENTATION SUMMARY

### New Endpoints to Create (15 Total)

| # | Endpoint | Model | Reuse? | Priority |
|---|----------|-------|--------|----------|
| 1 | `POST /tuition/student/batches/{id}/join` | TuitionBatchStudentMapping | Query existing | P0 |
| 2 | `GET /tuition/student/my` | TuitionBatchStudentMapping | Query existing | P0 |
| 3 | `GET /tuition/student/batches/{id}/study-plan` | TuitionLessonPlan | Wrap existing | P1 |
| 4 | `GET /tuition/student/lessons/{id}` | TuitionLesson | Wrap existing | P1 |
| 5 | `GET /tuition/student/topics/{id}` | TuitionLessonTopic | Wrap existing | P1 |
| 6 | `POST /tuition/student/topics/{id}/complete` | **StudentTuitionTopicProgress (NEW)** | New model | P1 |
| 7 | `GET /tuition/student/batches/{id}/schedule` | TuitionBatchSchedule | Wrap existing | P1 |
| 8 | `GET /tuition/student/classes/{id}/join` | TuitionBatchSchedule | Query existing | P1 |
| 9 | `GET /tuition/student/batches/{id}/assignments` | Assignment + Mapping | Wrap existing | P1 |
| 10 | `GET /tuition/student/assignments/{id}` | Assignment | Wrap existing | P1 |
| 11 | `GET /tuition/student/batches/{id}/tests` | ❓ StudentExamData or NEW | TBD | P2 |
| 12 | `GET /tuition/student/teachers` | TuitionTeachingSetup | Wrap/create | P0 |
| 13 | `POST /tuition/student/teachers/{id}/questions` | ❓ Messaging or Doubts | Reuse or NEW | P2 |
| 14 | `GET /tuition/student/dashboard` | Aggregate | New aggregate | P0 |
| 15 | `GET /tuition/student/batches/{id}/study-materials` | TuitionTopicFile | Wrap existing | P2 |

### Endpoints to REUSE (No new endpoints needed)

| Endpoint | Purpose | Status |
|----------|---------|--------|
| `POST /assignments/{id}/attempts` | Submit assignment | ✅ Reuse as-is |
| `GET /assignments/{id}/my-results` | View result | ✅ Reuse as-is |
| `GET /assignments/{id}` | Assignment details | ⚠️ Add auth check |
| `POST /assignments/{id}/doubts` | Ask question | ✅ Reuse as-is |
| `GET /assignments/{id}/doubts` | View questions | ✅ Reuse as-is |
| `POST /assignments/doubts/{id}/reply` | Reply to question | ✅ Reuse as-is |
| `POST /teachers/{id}/ratings` | Rate teacher | ✅ Reuse as-is |

---

## NEW MODELS NEEDED

### StudentTuitionTopicProgress
**Purpose:** Track which topics student has completed  
**Fields:**
```python
class StudentTuitionTopicProgress(Base):
    id = Column(String, primary_key=True)
    student_id = Column(Integer, FK → Student)
    self_signed_student_id = Column(Integer, FK → SelfSignedStudent)
    topic_id = Column(String, FK → TuitionLessonTopic)
    status = Column(Enum: "not_started" | "in_progress" | "completed")
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
```

**Status:** ✅ **MUST CREATE**

---

## MIGRATIONS NEEDED

1. Create `StudentTuitionTopicProgress` table
2. Possibly: Index on `(student_id, topic_id)` for fast lookups
3. Possibly: Index on `(batch_id, status)` if dashboard needs it

---

## AUTHORIZATION RULES (Critical)

Every endpoint MUST enforce:
1. **Authentication:** User must be STUDENT or SELF_SIGNED_STUDENT
2. **Enrollment Check:** Student must be enrolled in the batch
   ```
   Student → TuitionBatchStudentMapping → TuitionBatch
   ```
3. **Resource Ownership:** Cannot access resources from other students' batches
4. **Cascade Validation:** Topic must belong to enrolled batch's lesson plan

---

## PHASE 1 EXCLUSIONS (Payment & Advanced Features)

❌ **NOT IMPLEMENTING:**
- Payment gateway
- Payment orders
- Payment verification
- Discount calculation
- Subscription management
- Teacher earnings
- Platform commission
- Tests/Exams (needs more design)
- Advanced messaging system
- Certificates
- Video recording storage
- Student attendance tracking
- Feedback ratings (for now, can reuse assignment ratings)

---

## Dependency Graph

```
Student Auth
    ↓
Student Profile (Student or SelfSignedStudent)
    ↓
TuitionBatchStudentMapping
    ↓
TuitionBatch
    ├─ TuitionLessonPlan
    │   ├─ TuitionLesson
    │   │   └─ TuitionLessonTopic
    │   │       ├─ TuitionTopicFile
    │   │       ├─ StudentTuitionTopicProgress (NEW)
    │   │       └─ TuitionLessonAssignmentMapping
    │   │           └─ Assignment
    │   │               └─ StudentAssignmentAttempt
    │   └─ TuitionLessonAssignmentMapping
    ├─ TuitionBatchSchedule
    │   └─ TuitionClassDoneRecord
    └─ TuitionBatchStudentMapping
```

---

## Implementation Phases

### Phase 1A (Week 1) — Core Enrollment & Discovery
1. `POST /tuition/student/batches/{id}/join`
2. `GET /tuition/student/my`
3. `GET /tuition/student/teachers`
4. `GET /tuition/student/dashboard`

### Phase 1B (Week 2) — Curriculum & Study
5. `GET /tuition/student/batches/{id}/study-plan`
6. `GET /tuition/student/lessons/{id}`
7. `GET /tuition/student/topics/{id}`
8. `POST /tuition/student/topics/{id}/complete` (+ StudentTuitionTopicProgress model)
9. `GET /tuition/student/batches/{id}/schedule`
10. `GET /tuition/student/classes/{id}/join`

### Phase 1C (Week 3) — Assignments & Interaction
11. `GET /tuition/student/batches/{id}/assignments`
12. `GET /tuition/student/assignments/{id}`
13. Tests/Exams — **TBD** (architecture decision pending)
14. Teacher Questions — **OPTIONAL** (use assignment doubts for now)

---

## Testing Requirements

### Unit Tests Needed
- Authorization checks (student can't access other students' data)
- Enrollment validation
- Topic progress idempotency
- Schedule filtering
- Assignment submission flow

### Integration Tests Needed
- Full enrollment → study → submit flow
- Cross-batch data isolation
- Pagination/filtering

### API Tests Needed
- All new `/tuition/student/` endpoints
- Reused endpoint auth wrapping
- Error cases (404, 403, 400)

---

## API Naming Convention

**All new student tuition endpoints start with:**
```
/tuition/student/
```

**Verb patterns:**
- `GET /resource` - read/list
- `POST /resource` - create/action
- `PUT /resource/{id}` - full update (rarely used)
- `PATCH /resource/{id}` - partial update (rarely used)
- `DELETE /resource/{id}` - delete (rarely used in Phase 1)

---

## Final Checklist

- [ ] StudentTuitionTopicProgress model created
- [ ] 15 new endpoints implemented
- [ ] All existing reused endpoints auth-wrapped
- [ ] Authorization rules enforced on all endpoints
- [ ] Pagination added to list endpoints
- [ ] Error handling for all cases
- [ ] Tests for all new endpoints
- [ ] Integration tests for enrollment → study flow
- [ ] API documentation updated
- [ ] No payment logic added
- [ ] Backward compatibility maintained (existing Teacher APIs unchanged)
