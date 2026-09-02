# Student Tuition API Reference

## Overview

The Student Tuition APIs enable both regular **Student** and **SelfSignedStudent** users to:
- Discover and join tuition batches
- Track study progress through lesson plans, lessons, and topics
- Access class schedules and live class links
- View and submit assignments
- View personalized dashboard

**Base URL:** `/tuition/student`

**Authentication:** Bearer token (JWT) required for all endpoints

**Supported Roles:** `student`, `self_signed_student`

---

## 1. TEACHER DISCOVERY & AVAILABLE BATCHES

### 1.1 List Available Teachers/Batches

**Endpoint:** `GET /tuition/student/teachers`

**Purpose:** Browse all available tuition batches for enrollment (discovery mode)

**Query Parameters:**
```json
{
  "board": "string (optional)",
  "class_id": "integer (optional)",
  "subject_id": "integer (optional)",
  "page": "integer (default: 1, min: 1)",
  "page_size": "integer (default: 20, min: 1, max: 100)"
}
```

**Response (200 OK):**
```json
{
  "total": 150,
  "page": 1,
  "page_size": 20,
  "batches": [
    {
      "batch_id": "b_abc123",
      "batch_name": "Physics Fundamentals - Batch A",
      "teacher": {
        "teacher_id": "t_xyz789",
        "teacher_name": "Dr. John Smith",
        "teacher_type": "teacher"  // "teacher" or "self_signed_teacher"
      },
      "board": "cbse",
      "class_name": "12th Grade",
      "subject_name": "Physics",
      "batch_status": "active",
      "description": "Comprehensive physics course covering mechanics and thermodynamics",
      "start_date": "2026-01-15",
      "end_date": "2026-06-30",
      "batch_capacity": 40,
      "tuition_fee": "15000",
      "study_material_fee": "2500",
      "enrolled_count": 28,
      "language": "English"
    },
    {
      "batch_id": "b_def456",
      "batch_name": "Mathematics Advanced - Batch C",
      "teacher": {
        "teacher_id": 45,
        "teacher_name": "Mrs. Sarah Johnson",
        "teacher_type": "self_signed_teacher"
      },
      "board": "icse",
      "class_name": "10th Grade",
      "subject_name": "Mathematics",
      "batch_status": "active",
      "description": null,
      "start_date": "2026-02-01",
      "end_date": "2026-05-31",
      "batch_capacity": 30,
      "tuition_fee": "12000",
      "study_material_fee": "1500",
      "enrolled_count": 15,
      "language": "Hindi"
    }
  ]
}
```

**Error Responses:**
- `401 Unauthorized` - No valid authentication token
- `403 Forbidden` - User is not a student role

---

## 2. ENROLLMENT MANAGEMENT

### 2.1 Join a Batch

**Endpoint:** `POST /tuition/student/batches/{batch_id}/join`

**Purpose:** Enroll current student in a tuition batch

**Path Parameters:**
```json
{
  "batch_id": "string (required)"
}
```

**Request Body:**
```json
{}  // No body required
```

**Response (200 OK):**
```json
{
  "enrollment_id": "enr_123abc",
  "batch_id": "b_abc123",
  "enrollment_status": "pending",
  "payment_status": "pending",
  "joined_date": "2026-09-01"
}
```

**Error Responses:**
- `400 Bad Request` - "Already enrolled in this batch" or "Batch is not active"
- `403 Forbidden` - User is not a student or batch access denied
- `404 Not Found` - Batch does not exist

---

### 2.2 List My Enrollments

**Endpoint:** `GET /tuition/student/my`

**Purpose:** Get all active tuition enrollments for current student

**Query Parameters:**
```json
{
  "status": "string (optional)",  // Filter by enrollment_status: "pending", "active", "completed", "cancelled"
  "board": "string (optional)",
  "class_id": "integer (optional)",
  "subject_id": "integer (optional)",
  "page": "integer (default: 1, min: 1)",
  "page_size": "integer (default: 20, min: 1, max: 100)"
}
```

**Response (200 OK):**
```json
{
  "total": 3,
  "page": 1,
  "page_size": 20,
  "enrollments": [
    {
      "enrollment_id": "enr_123abc",
      "batch_id": "b_abc123",
      "batch_name": "Physics Fundamentals - Batch A",
      "teacher_name": "Dr. John Smith",
      "teacher_id": "t_xyz789",
      "teacher_type": "teacher",
      "board": "cbse",
      "class_name": "12th Grade",
      "subject_name": "Physics",
      "enrollment_status": "active",
      "payment_status": "pending",
      "batch_status": "active",
      "joined_date": "2026-09-01",
      "schedule": {
        "start_date": "2026-01-15",
        "end_date": "2026-06-30",
        "days": ["monday", "wednesday", "friday"],
        "time_slot": "18:00 - 19:30"
      },
      "progress": {
        "lessons_completed": 5,
        "lessons_total": 20,
        "topics_completed": 15,
        "topics_total": 80,
        "completion_percentage": 19
      }
    }
  ]
}
```

**Error Responses:**
- `401 Unauthorized` - No valid authentication token
- `403 Forbidden` - User is not a student role

---

## 3. STUDY PLAN & CURRICULUM

### 3.1 Get Batch Study Plan

**Endpoint:** `GET /tuition/student/batches/{batch_id}/study-plan`

**Purpose:** Get the complete lesson plan and study curriculum for an enrolled batch

**Path Parameters:**
```json
{
  "batch_id": "string (required)"
}
```

**Response (200 OK):**
```json
{
  "batch_id": "b_abc123",
  "batch_name": "Physics Fundamentals - Batch A",
  "lesson_plan_id": "lp_111",
  "subject": "Physics",
  "board": "cbse",
  "class_name": "12th Grade",
  "total_lessons": 20,
  "total_topics": 80,
  "lessons_completed": 5,
  "topics_completed": 15,
  "overall_completion_percentage": 19,
  "lessons": [
    {
      "lesson_id": "l_001",
      "lesson_number": 1,
      "lesson_title": "Introduction to Motion",
      "lesson_objective": "Understand basic concepts of motion and velocity",
      "topics_count": 4,
      "topics_completed": 4,
      "completion_percentage": 100
    },
    {
      "lesson_id": "l_002",
      "lesson_number": 2,
      "lesson_title": "Forces and Newton's Laws",
      "lesson_objective": "Learn about forces and three laws of motion",
      "topics_count": 5,
      "topics_completed": 2,
      "completion_percentage": 40
    }
  ]
}
```

**Error Responses:**
- `403 Forbidden` - Not enrolled in this batch
- `404 Not Found` - Batch or lesson plan not found

---

### 3.2 Get Lesson Details

**Endpoint:** `GET /tuition/student/lessons/{lesson_id}`

**Purpose:** Get detailed view of a lesson with all its topics

**Path Parameters:**
```json
{
  "lesson_id": "string (required)"
}
```

**Response (200 OK):**
```json
{
  "lesson_id": "l_001",
  "lesson_number": 1,
  "lesson_title": "Introduction to Motion",
  "lesson_objective": "Understand basic concepts of motion and velocity",
  "topics_completed": 3,
  "topics": [
    {
      "topic_id": "t_001",
      "topic_title": "What is Motion?",
      "display_order": 1,
      "status": "completed",  // "not_started", "in_progress", "completed"
      "has_files": true
    },
    {
      "topic_id": "t_002",
      "topic_title": "Velocity and Speed",
      "display_order": 2,
      "status": "in_progress",
      "has_files": true
    },
    {
      "topic_id": "t_003",
      "topic_title": "Acceleration",
      "display_order": 3,
      "status": "not_started",
      "has_files": false
    },
    {
      "topic_id": "t_004",
      "topic_title": "Practice Problems",
      "display_order": 4,
      "status": "not_started",
      "has_files": true
    }
  ]
}
```

**Error Responses:**
- `403 Forbidden` - Not enrolled in lesson's batch
- `404 Not Found` - Lesson not found

---

### 3.3 Get Topic Details

**Endpoint:** `GET /tuition/student/topics/{topic_id}`

**Purpose:** Get full topic content, files, and current progress

**Path Parameters:**
```json
{
  "topic_id": "string (required)"
}
```

**Response (200 OK):**
```json
{
  "topic_id": "t_001",
  "topic_title": "What is Motion?",
  "topic_content": "<p>Motion is the change in position of an object over time...</p>",
  "display_order": 1,
  "reference_video_link": "https://youtube.com/watch?v=abc123",
  "files": [
    {
      "file_id": "f_001",
      "file_name": "Motion_Notes.pdf",
      "file_url": "https://s3.amazonaws.com/tek-school/files/motion_notes.pdf",
      "file_type": "pdf",
      "file_size": 2048576,
      "uploaded_at": "2026-08-15T10:30:00Z"
    },
    {
      "file_id": "f_002",
      "file_name": "Motion_Diagrams.pptx",
      "file_url": "https://s3.amazonaws.com/tek-school/files/motion_diagrams.pptx",
      "file_type": "pptx",
      "file_size": 5242880,
      "uploaded_at": "2026-08-16T14:20:00Z"
    }
  ],
  "student_progress": {
    "topic_id": "t_001",
    "status": "completed",
    "started_at": "2026-09-01T08:00:00Z",
    "completed_at": "2026-09-02T10:15:00Z"
  }
}
```

**Error Responses:**
- `403 Forbidden` - Not enrolled in topic's batch
- `404 Not Found` - Topic not found

---

### 3.4 Mark Topic Complete

**Endpoint:** `POST /tuition/student/topics/{topic_id}/complete`

**Purpose:** Mark a topic as completed by student (idempotent)

**Path Parameters:**
```json
{
  "topic_id": "string (required)"
}
```

**Request Body:**
```json
{}  // No body required
```

**Response (200 OK):**
```json
{
  "topic_id": "t_001",
  "status": "completed",
  "completed_at": "2026-09-02T10:15:00Z"
}
```

**Error Responses:**
- `403 Forbidden` - Not enrolled in topic's batch
- `404 Not Found` - Topic not found

---

## 4. SCHEDULES & LIVE CLASSES

### 4.1 Get Batch Schedule

**Endpoint:** `GET /tuition/student/batches/{batch_id}/schedule`

**Purpose:** Get all class schedule sessions for a batch with optional filtering

**Path Parameters:**
```json
{
  "batch_id": "string (required)"
}
```

**Query Parameters:**
```json
{
  "from_date": "date (optional, format: YYYY-MM-DD)",
  "to_date": "date (optional, format: YYYY-MM-DD)",
  "status": "string (optional)",  // "scheduled", "completed", "cancelled"
  "page": "integer (default: 1, min: 1)",
  "page_size": "integer (default: 20, min: 1, max: 100)"
}
```

**Response (200 OK):**
```json
{
  "total": 45,
  "page": 1,
  "page_size": 20,
  "schedules": [
    {
      "schedule_id": "s_001",
      "class_date": "2026-09-03",
      "start_time": "18:00:00",
      "end_time": "19:30:00",
      "topic": "Introduction to Motion",
      "meeting_link": null,  // Use /classes/{schedule_id}/join to get the actual link
      "meeting_link_override": null,
      "status": "scheduled",
      "class_summary": null  // Populated only if class is completed
    },
    {
      "schedule_id": "s_002",
      "class_date": "2026-09-05",
      "start_time": "18:00:00",
      "end_time": "19:30:00",
      "topic": "Velocity and Speed",
      "meeting_link": null,
      "meeting_link_override": "https://meet.google.com/xyz-abc-def",
      "status": "scheduled",
      "class_summary": null
    },
    {
      "schedule_id": "s_001_completed",
      "class_date": "2026-09-01",
      "start_time": "18:00:00",
      "end_time": "19:30:00",
      "topic": "Course Overview",
      "meeting_link": null,
      "meeting_link_override": null,
      "status": "completed",
      "class_summary": "Discussed course structure and expectations. Covered first 2 topics."
    }
  ]
}
```

**Error Responses:**
- `403 Forbidden` - Not enrolled in this batch
- `404 Not Found` - Batch not found

---

### 4.2 Join Live Class

**Endpoint:** `GET /tuition/student/classes/{schedule_id}/join`

**Purpose:** Get the meeting link to join a live class session

**Path Parameters:**
```json
{
  "schedule_id": "string (required)"
}
```

**Response (200 OK):**
```json
{
  "schedule_id": "s_002",
  "class_date": "2026-09-05",
  "start_time": "18:00:00",
  "end_time": "19:30:00",
  "topic": "Velocity and Speed",
  "meeting_provider": "google_meet",  // "google_meet", "zoom", "teams", etc.
  "meeting_link": "https://meet.google.com/xyz-abc-def"
}
```

**Error Responses:**
- `400 Bad Request` - "No meeting link configured"
- `403 Forbidden` - Not enrolled in class's batch
- `404 Not Found` - Schedule not found

---

## 5. ASSIGNMENTS

### 5.1 List Batch Assignments

**Endpoint:** `GET /tuition/student/batches/{batch_id}/assignments`

**Purpose:** Get all assignments for a batch with student attempt status

**Path Parameters:**
```json
{
  "batch_id": "string (required)"
}
```

**Query Parameters:**
```json
{
  "page": "integer (default: 1, min: 1)",
  "page_size": "integer (default: 20, min: 1, max: 100)"
}
```

**Response (200 OK):**
```json
{
  "total": 12,
  "page": 1,
  "page_size": 20,
  "assignments": [
    {
      "assignment_id": 101,
      "title": "Motion Concepts Quiz",
      "chapter": "Chapter 1: Motion",
      "topic_ids": ["t_001", "t_002", "t_003"],
      "question_count": 10,
      "due_date": "2026-09-10",
      "status": "published",
      "student_attempt_status": "submitted"  // "not_attempted", "in_progress", "submitted", "graded"
    },
    {
      "assignment_id": 102,
      "title": "Velocity Problems",
      "chapter": "Chapter 1: Motion",
      "topic_ids": ["t_002"],
      "question_count": 15,
      "due_date": "2026-09-15",
      "status": "published",
      "student_attempt_status": "not_attempted"
    }
  ]
}
```

**Error Responses:**
- `403 Forbidden` - Not enrolled in this batch
- `404 Not Found` - Batch not found

---

### 5.2 Submit Assignment Attempt (REUSED API)

**Endpoint:** `POST /assignments/{assignment_id}/attempts`

**Purpose:** Submit answers for an assignment (max 3 attempts per student)

**Reuse Note:** This is an **existing assignment API** that handles both Student and SelfSignedStudent

**Path Parameters:**
```json
{
  "assignment_id": "integer (required)"
}
```

**Request Body:**
```json
{
  "submitted_answers": {
    "q_1": "option_a",
    "q_2": "option_c",
    "q_3": "This is my answer text",
    "q_4": true
  },
  "score": 7.5,
  "time_taken_seconds": 1200
}
```

**Response (200 OK):**
```json
{
  "id": 5001,
  "student_user_id": 123,
  "assignment_id": 101,
  "attempt_number": 1,
  "submitted_answers": "{\"q_1\": \"option_a\", \"q_2\": \"option_c\", ...}",
  "score": 7.5,
  "time_taken_seconds": 1200,
  "submission_date": "2026-09-05T14:30:00Z"
}
```

**Error Responses:**
- `400 Bad Request` - "Maximum 3 attempts allowed"
- `403 Forbidden` - Only students may submit attempts
- `404 Not Found` - Assignment not found or not published

**Location:** `/assignments/{assignment_id}/attempts`

---

### 5.3 Rate Teacher (REUSED API)

**Endpoint:** `POST /teachers/{teacher_id}/ratings`

**Purpose:** Rate a teacher on a scale of 1-5 (idempotent - last rating wins)

**Reuse Note:** This is an **existing teacher rating API** available to Student and SelfSignedStudent

**Path Parameters:**
```json
{
  "teacher_id": "integer or string (required)"
  // Accepts: User.id (school teacher), Teacher.id (string), or SelfSignedTeacher.id (int)
}
```

**Request Body:**
```json
{
  "rating": 5
}
```

**Response (200 OK):**
```json
{
  "detail": "Rating submitted successfully."
}
```

**Error Responses:**
- `403 Forbidden` - Only students may rate teachers
- `404 Not Found` - Teacher not found

**Location:** `/teachers/{teacher_id}/ratings`

---

### 5.4 Get Assignment Attempts (REUSED API)

**Endpoint:** `GET /assignments/{assignment_id}/attempts`

**Purpose:** Get all attempts for an assignment by current student

**Reuse Note:** This is an **existing assignment attempt history API**

**Path Parameters:**
```json
{
  "assignment_id": "integer (required)"
}
```

**Response (200 OK):**
```json
[
  {
    "id": 5001,
    "student_user_id": 123,
    "assignment_id": 101,
    "attempt_number": 1,
    "submitted_answers": "{\"q_1\": \"option_a\", ...}",
    "score": 7.5,
    "time_taken_seconds": 1200,
    "submission_date": "2026-09-05T14:30:00Z"
  },
  {
    "id": 5002,
    "student_user_id": 123,
    "assignment_id": 101,
    "attempt_number": 2,
    "submitted_answers": "{\"q_1\": \"option_b\", ...}",
    "score": 8.2,
    "time_taken_seconds": 1050,
    "submission_date": "2026-09-06T10:15:00Z"
  }
]
```

**Location:** `/assignments/{assignment_id}/attempts`

---

## 6. DASHBOARD

### 6.1 Get Student Dashboard

**Endpoint:** `GET /tuition/student/dashboard`

**Purpose:** Get personalized dashboard with active tuitions, upcoming classes, recent assignments, and overall progress

**Response (200 OK):**
```json
{
  "active_tuitions_count": 3,
  "tuitions": [
    {
      "batch_id": "b_abc123",
      "batch_name": "Physics Fundamentals - Batch A",
      "teacher_name": "Dr. John Smith",
      "subject_name": "Physics",
      "progress_percentage": 35,
      "enrollment_status": "active"
    },
    {
      "batch_id": "b_def456",
      "batch_name": "Mathematics Advanced - Batch C",
      "teacher_name": "Mrs. Sarah Johnson",
      "subject_name": "Mathematics",
      "progress_percentage": 52,
      "enrollment_status": "active"
    }
  ],
  "upcoming_classes": [
    {
      "schedule_id": "s_003",
      "class_date": "2026-09-03",
      "start_time": "18:00:00",
      "subject_name": "Physics",
      "batch_name": "Physics Fundamentals - Batch A"
    },
    {
      "schedule_id": "s_004",
      "class_date": "2026-09-04",
      "start_time": "19:00:00",
      "subject_name": "Mathematics",
      "batch_name": "Mathematics Advanced - Batch C"
    },
    {
      "schedule_id": "s_005",
      "class_date": "2026-09-05",
      "start_time": "18:00:00",
      "subject_name": "Physics",
      "batch_name": "Physics Fundamentals - Batch A"
    }
  ],
  "recent_assignments": [
    {
      "assignment_id": 101,
      "title": "Motion Concepts Quiz",
      "batch_name": "Physics Fundamentals - Batch A",
      "due_date": "2026-09-10",
      "status": "published"
    },
    {
      "assignment_id": 103,
      "title": "Algebra Fundamentals",
      "batch_name": "Mathematics Advanced - Batch C",
      "due_date": "2026-09-12",
      "status": "published"
    }
  ],
  "study_progress": {
    "total_topics": 145,
    "topics_completed": 42,
    "total_lessons": 35,
    "lessons_completed": 8,
    "overall_percentage": 29
  }
}
```

**Error Responses:**
- `401 Unauthorized` - No valid authentication token
- `403 Forbidden` - User is not a student role

---

## REUSED EXISTING APIs Summary

The student tuition module intentionally **reuses** these existing teacher-facing APIs instead of creating duplicates:

| API | Endpoint | Purpose | Who Can Use |
|-----|----------|---------|------------|
| **Submit Assignment Attempt** | `POST /assignments/{assignment_id}/attempts` | Submit assignment answers | Student, SelfSignedStudent |
| **Rate Teacher** | `POST /teachers/{teacher_id}/ratings` | Rate teacher 1-5 stars | Student, SelfSignedStudent |
| **Get Assignment Attempts** | `GET /assignments/{assignment_id}/attempts` | View attempt history | Student, SelfSignedStudent |
| **Get Attempt History** | `GET /assignments/attempts/history` | Get all attempts across assignments | Student, SelfSignedStudent |
| **Submit Assignment Feedback** | `POST /assignments/{assignment_id}/feedback` | Provide chapter feedback | Student, SelfSignedStudent |
| **Ask Assignment Doubt** | `POST /assignments/{assignment_id}/doubts` | Post questions about assignment | Student, SelfSignedStudent |
| **Reply to Doubt** | `POST /assignments/doubts/{doubt_id}/reply` | Reply in doubt thread | Student, SelfSignedStudent |
| **Report Assignment Issue** | `POST /assignments/{assignment_id}/report` | Flag plagiarism/issues | Student, SelfSignedStudent |

---

## Authentication & Authorization

All endpoints require:
1. **Bearer Token** in Authorization header: `Authorization: Bearer <jwt_token>`
2. **User Role** must be `student` or `self_signed_student`
3. **Enrollment Verification** for batch-specific endpoints (study plan, schedule, assignments)

### Example Request Headers
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json
```

---

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (invalid input, already enrolled, etc.) |
| 401 | Unauthorized (missing or invalid token) |
| 403 | Forbidden (insufficient role, not enrolled in batch) |
| 404 | Not found (resource doesn't exist) |
| 422 | Validation error (invalid schema) |
| 500 | Server error |

---

## Common Filters & Query Parameters

### Pagination
All list endpoints support:
- `page`: Page number (default: 1, min: 1)
- `page_size`: Items per page (default: 20, min: 1, max: 100)

### Date Range
Some endpoints accept:
- `from_date`: Start date (format: YYYY-MM-DD)
- `to_date`: End date (format: YYYY-MM-DD)

### Status Filters
Different endpoints use different status values:
- **Enrollment Status:** `pending`, `active`, `completed`, `cancelled`
- **Batch Status:** `active`, `inactive`, `draft`, `completed`
- **Assignment Status:** `published`, `draft`, `archived`
- **Topic Status:** `not_started`, `in_progress`, `completed`

---

## Implementation Notes

### Thin Client Layer
The student APIs are **intentionally thin** — they:
- Verify enrollment before returning batch-specific data
- Reuse existing CRUD and models
- Don't duplicate teacher/admin logic
- Share the same database tables for progress tracking

### Data Consistency
- Topic completion is tracked in `StudentTuitionTopicProgress` table
- Enrollment is tracked in `TuitionBatchStudentMapping` table
- Both support `student_id` (regular students) and `self_signed_student_id` (self-signed students)

### Live Class Meeting Links
- Base link stored in `TuitionBatch.meeting_link`
- Override link (per session) stored in `TuitionBatchSchedule.meeting_link_override`
- Call `/classes/{schedule_id}/join` to get the actual link (prefers override → batch link)

---

## Example Client Workflow

```
1. [Discovery]
   GET /tuition/student/teachers?board=cbse&class_id=12
   → Browse available batches

2. [Enrollment]
   POST /tuition/student/batches/{batch_id}/join
   → Join a batch

3. [Learning]
   GET /tuition/student/my
   → List my enrollments
   
   GET /tuition/student/batches/{batch_id}/study-plan
   → View lesson plan
   
   GET /tuition/student/lessons/{lesson_id}
   → View lesson topics
   
   GET /tuition/student/topics/{topic_id}
   → View topic content and files
   
   POST /tuition/student/topics/{topic_id}/complete
   → Mark topic complete

4. [Classes]
   GET /tuition/student/batches/{batch_id}/schedule
   → View class schedule
   
   GET /tuition/student/classes/{schedule_id}/join
   → Get meeting link for live class

5. [Assignments]
   GET /tuition/student/batches/{batch_id}/assignments
   → View assignments
   
   POST /assignments/{assignment_id}/attempts
   → Submit assignment (REUSED API)

6. [Rating]
   POST /teachers/{teacher_id}/ratings
   → Rate teacher (REUSED API)

7. [Dashboard]
   GET /tuition/student/dashboard
   → View personalized dashboard
```

---

## File Locations

- **Routes:** [app/routes/tuition/student.py](app/routes/tuition/student.py)
- **CRUD Logic:** [app/crud/tuition/student.py](app/crud/tuition/student.py)
- **Schemas:** [app/schemas/tuition/student.py](app/schemas/tuition/student.py)
- **Models:** [app/models/tuition_models.py](app/models/tuition_models.py)

---

## Version History

- **v1.0** (2026-09-01): Initial student tuition API layer for both Student and SelfSignedStudent
