# 📚 ASSIGNMENTS Module - Complete API Guide
## Teacher Creates Topic/Summary/Q&A → Students Attempt → Track Attempts & Doubts

---

## 🎯 System Overview

**Purpose:** Create educational assignments with topics, summaries, Q&A content, and track student attempts.

**Flow:**
```
Teacher Creates Draft → Adds Questions/Content → Publish → Students See Published
  ↓
Students Attempt Assignment → Submit Answers → Get Score
  ↓
Teachers/Admin View Attempts & Reports
```

---

## 🔗 API Endpoints

| Method | Endpoint | Purpose | Auth |
|--------|----------|---------|------|
| POST | `/assignments` | Create draft assignment | Teacher |
| GET | `/assignments/{id}` | View assignment | Teacher/Student |
| PUT | `/assignments/{id}` | Update draft assignment | Teacher |
| POST | `/assignments/{id}/publish` | Publish assignment | Teacher |
| POST | `/assignments/{id}/unpublish` | Unpublish assignment | Teacher |
| GET | `/students/{id}/assignments` | List published assignments for student | Student |
| POST | `/assignments/{id}/attempts` | Submit student attempt | Student |
| GET | `/teachers/{id}/profile` | View teacher profile & stats | Public |
| POST | `/assignments/{id}/feedback` | Submit feedback on assignment | Student |
| POST | `/teachers/{id}/ratings` | Rate teacher | Student |

---

## 📝 1. CREATE DRAFT ASSIGNMENT (Teacher)

### Endpoint
```
POST /assignments
```

### Body Schema

```json
{
  "board": "string (required)",
  "class_name": "string (required)",
  "subject": "string (required)",
  "chapter_number": "integer (required)",
  "sub_chapter": "string (optional)",
  "topic_title": "string (required)",
  "chapter_tagline": "string (optional)",
  "original_content": "string HTML/Rich text (optional)",
  "summarized_content": "string (optional)",
  "key_points": [
    {
      "step_number": integer,
      "text": string
    }
  ],
  "questions": [
    {
      "question_number": integer,
      "question_text": string,
      "option_a": string,
      "option_b": string,
      "option_c": string,
      "option_d": string,
      "correct_option": "A|B|C|D",
      "solution_explanation": "string (optional)"
    }
  ]
}
```

### Example 1: Full Assignment with Q&A

```json
{
  "board": "CBSE",
  "class_name": "10",
  "subject": "Mathematics",
  "chapter_number": 5,
  "sub_chapter": "Quadratic Equations",
  "topic_title": "Solving Quadratic Equations Using Factorization",
  "chapter_tagline": "Master the art of solving using factorization method",
  "original_content": "<h2>Quadratic Equations</h2><p>A quadratic equation is an equation of the form ax² + bx + c = 0...</p>",
  "summarized_content": "A quadratic equation has the form ax² + bx + c = 0. The factorization method involves breaking it into (x-p)(x-q)=0, giving solutions x=p and x=q.",
  "key_points": [
    {
      "step_number": 1,
      "text": "Write the equation in standard form ax² + bx + c = 0"
    },
    {
      "step_number": 2,
      "text": "Factor the left side into (px + q)(rx + s) = 0"
    },
    {
      "step_number": 3,
      "text": "Apply zero product property: px + q = 0 or rx + s = 0"
    },
    {
      "step_number": 4,
      "text": "Solve for x to get both solutions"
    }
  ],
  "questions": [
    {
      "question_number": 1,
      "question_text": "Solve: x² - 5x + 6 = 0",
      "option_a": "x = 2, 3",
      "option_b": "x = 1, 6",
      "option_c": "x = -2, -3",
      "option_d": "x = 0, 5",
      "correct_option": "A",
      "solution_explanation": "Factorize: (x-2)(x-3)=0, so x=2 or x=3"
    },
    {
      "question_number": 2,
      "question_text": "Solve: 2x² - 8x + 6 = 0",
      "option_a": "x = 1, 3",
      "option_b": "x = 2, 2",
      "option_c": "x = 0, 4",
      "option_d": "x = -1, -3",
      "correct_option": "A",
      "solution_explanation": "Divide by 2: x² - 4x + 3 = 0, then (x-1)(x-3)=0"
    },
    {
      "question_number": 3,
      "question_text": "For x² + 2x - 15 = 0, which is the correct factorization?",
      "option_a": "(x+5)(x-3)",
      "option_b": "(x-5)(x+3)",
      "option_c": "(x+3)(x+5)",
      "option_d": "(x-3)(x-5)",
      "correct_option": "A",
      "solution_explanation": "(x+5)(x-3) = x² - 3x + 5x - 15 = x² + 2x - 15 ✓"
    }
  ]
}
```

### Using cURL

```bash
curl -X POST "http://localhost:8000/assignments" \
  -H "Authorization: Bearer YOUR_TEACHER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "board": "CBSE",
    "class_name": "10",
    "subject": "Mathematics",
    "chapter_number": 5,
    "topic_title": "Solving Quadratic Equations Using Factorization",
    "summarized_content": "A quadratic equation has the form ax² + bx + c = 0...",
    "key_points": [
      {"step_number": 1, "text": "Write in standard form"},
      {"step_number": 2, "text": "Factor the left side"}
    ],
    "questions": [
      {
        "question_number": 1,
        "question_text": "Solve: x² - 5x + 6 = 0",
        "option_a": "x = 2, 3",
        "option_b": "x = 1, 6",
        "option_c": "x = -2, -3",
        "option_d": "x = 0, 5",
        "correct_option": "A",
        "solution_explanation": "(x-2)(x-3)=0"
      }
    ]
  }'
```

### Using Python

```python
import requests
import json

url = "http://localhost:8000/assignments"
headers = {
    "Authorization": "Bearer YOUR_TEACHER_TOKEN",
    "Content-Type": "application/json"
}

payload = {
    "board": "CBSE",
    "class_name": "10",
    "subject": "Mathematics",
    "chapter_number": 5,
    "sub_chapter": "Quadratic Equations",
    "topic_title": "Solving Quadratic Equations",
    "chapter_tagline": "Master factorization method",
    "summarized_content": "Learn to solve quadratic equations using factorization",
    "key_points": [
        {"step_number": 1, "text": "Write in standard form ax² + bx + c = 0"},
        {"step_number": 2, "text": "Factor into (px+q)(rx+s)=0"},
        {"step_number": 3, "text": "Apply zero product property"}
    ],
    "questions": [
        {
            "question_number": 1,
            "question_text": "Solve: x² - 5x + 6 = 0",
            "option_a": "x = 2, 3",
            "option_b": "x = 1, 6",
            "option_c": "x = -2, -3",
            "option_d": "x = 0, 5",
            "correct_option": "A",
            "solution_explanation": "Factorize: (x-2)(x-3)=0"
        },
        {
            "question_number": 2,
            "question_text": "Solve: 2x² - 8x + 6 = 0",
            "option_a": "x = 1, 3",
            "option_b": "x = 2, 2",
            "option_c": "x = 0, 4",
            "option_d": "x = -1, -3",
            "correct_option": "A",
            "solution_explanation": "Divide by 2 first"
        }
    ]
}

response = requests.post(url, json=payload, headers=headers)
if response.status_code == 200:
    assignment = response.json()
    print(f"✅ Assignment created! ID: {assignment['id']}")
    print(f"Status: {assignment['status']} (DRAFT)")
else:
    print(f"❌ Error: {response.json()}")
```

### Response (200 OK)

```json
{
  "id": 42,
  "created_by_user_id": 5,
  "status": "Draft",
  "board": "CBSE",
  "class_name": "10",
  "subject": "Mathematics",
  "chapter_number": 5,
  "topic_title": "Solving Quadratic Equations Using Factorization",
  "summarized_content": "A quadratic equation...",
  "teacher_name": "Dr. Raj Kumar",
  "school_name": "Delhi Public School",
  "school_address": "New Delhi, Delhi",
  "created_at": "2024-06-19T10:30:00",
  "published_at": null,
  "updated_at": "2024-06-19T10:30:00",
  "key_points": [
    {"id": 1, "assignment_id": 42, "step_number": 1, "text": "Write in standard form"},
    {"id": 2, "assignment_id": 42, "step_number": 2, "text": "Factor the left side"}
  ],
  "questions": [
    {
      "id": 101,
      "assignment_id": 42,
      "question_number": 1,
      "question_text": "Solve: x² - 5x + 6 = 0",
      "option_a": "x = 2, 3",
      "option_b": "x = 1, 6",
      "option_c": "x = -2, -3",
      "option_d": "x = 0, 5",
      "correct_option": "A",
      "solution_explanation": "Factorize: (x-2)(x-3)=0"
    }
  ],
  "images": [],
  "pdfs": [],
  "video_links": [],
  "media_banners": [],
  "publish_config": null
}
```

---

## 🔄 2. PUBLISH ASSIGNMENT (Teacher)

### Endpoint
```
POST /assignments/{assignment_id}/publish
```

### Body
```json
{
  "assignment_type": "Academic|General Knowledge",
  "improvement_categories": [
    "Moral Development",
    "Enhance Thinking",
    "Knowledge Enhancement"
  ],
  "reward_amount_override": 100.00
}
```

### Example: Publish Assignment

```bash
curl -X POST "http://localhost:8000/assignments/42/publish" \
  -H "Authorization: Bearer YOUR_TEACHER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "assignment_type": "Academic",
    "improvement_categories": ["Enhance Thinking", "Knowledge Enhancement"],
    "reward_amount_override": 50.00
  }'
```

### Response (200 OK)

```json
{
  "id": 1,
  "assignment_id": 42,
  "assignment_type": "Academic",
  "improvement_categories": ["Enhance Thinking", "Knowledge Enhancement"],
  "reward_amount_override": 50.00
}
```

**Now students can see this assignment!**

---

## 👨‍🎓 3. STUDENT LIST ASSIGNMENTS (Published Only)

### Endpoint
```
GET /students/{student_id}/assignments?board=CBSE&subject=Mathematics
```

### Query Parameters

| Parameter | Type | Optional | Purpose |
|-----------|------|----------|---------|
| `board` | string | ✅ | Filter by board (CBSE, ICSE, etc.) |
| `class_name` | string | ✅ | Filter by class |
| `subject` | string | ✅ | Filter by subject |
| `teacher_id` | integer | ✅ | Filter by specific teacher |
| `school_name` | string | ✅ | Filter by school |
| `chapter_number` | integer | ✅ | Filter by chapter |

### Example: Get All Math Assignments

```bash
curl -X GET "http://localhost:8000/students/10/assignments?board=CBSE&subject=Mathematics" \
  -H "Authorization: Bearer STUDENT_TOKEN"
```

### Response (200 OK)

```json
[
  {
    "id": 42,
    "created_by_user_id": 5,
    "status": "Published",
    "board": "CBSE",
    "class_name": "10",
    "subject": "Mathematics",
    "chapter_number": 5,
    "topic_title": "Solving Quadratic Equations",
    "chapter_tagline": "Master factorization",
    "teacher_name": "Dr. Raj Kumar",
    "school_name": "Delhi Public School",
    "school_address": "New Delhi, Delhi",
    "published_at": "2024-06-19T10:45:00",
    "questions": [
      {
        "id": 101,
        "question_number": 1,
        "question_text": "Solve: x² - 5x + 6 = 0",
        "option_a": "x = 2, 3",
        "option_b": "x = 1, 6",
        "option_c": "x = -2, -3",
        "option_d": "x = 0, 5",
        "correct_option": "A",
        "solution_explanation": "Factorize: (x-2)(x-3)=0"
      }
    ]
  }
]
```

---

## ✍️ 4. STUDENT SUBMIT ATTEMPT

### Endpoint
```
POST /assignments/{assignment_id}/attempts
```

### Body
```json
{
  "submitted_answers": {
    "1": "A",
    "2": "A",
    "3": "C"
  },
  "score": 66.67,
  "time_taken_seconds": 1800
}
```

### Example: Submit Answers

```bash
curl -X POST "http://localhost:8000/assignments/42/attempts" \
  -H "Authorization: Bearer STUDENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "submitted_answers": {"1": "A", "2": "A", "3": "B"},
    "score": 66.67,
    "time_taken_seconds": 1800
  }'
```

### Using Python

```python
import requests
import json

url = "http://localhost:8000/assignments/42/attempts"
headers = {
    "Authorization": "Bearer STUDENT_TOKEN",
    "Content-Type": "application/json"
}

payload = {
    "submitted_answers": {
        "1": "A",  # Question 1 answered A
        "2": "A",  # Question 2 answered A
        "3": "B"   # Question 3 answered B
    },
    "score": 66.67,
    "time_taken_seconds": 1800  # 30 minutes
}

response = requests.post(url, json=payload, headers=headers)
if response.status_code == 200:
    attempt = response.json()
    print(f"✅ Attempt submitted!")
    print(f"Score: {attempt['score']}")
    print(f"Attempt #{attempt['attempt_number']}")
else:
    print(f"❌ Error: {response.json()}")
```

### Response (200 OK)

```json
{
  "id": 501,
  "student_user_id": 10,
  "assignment_id": 42,
  "attempt_number": 1,
  "submitted_answers": {"1": "A", "2": "A", "3": "B"},
  "score": 66.67,
  "time_taken_seconds": 1800,
  "submission_date": "2024-06-19T11:15:00"
}
```

---

## 📊 5. VIEW STUDENT ATTEMPTS (Admin/Teacher)

**TODO:** Implement endpoint to list all attempts for an assignment
```
GET /assignments/{assignment_id}/attempts
```

Should return:
- How many students attempted
- Individual attempt scores
- Time taken by each student
- Answers submitted

### Expected Response (Not Yet Implemented)

```json
{
  "assignment_id": 42,
  "total_attempts": 45,
  "average_score": 72.5,
  "attempts": [
    {
      "attempt_id": 501,
      "student_name": "Arjun Singh",
      "student_id": 10,
      "attempt_number": 1,
      "score": 66.67,
      "time_taken_seconds": 1800,
      "submission_date": "2024-06-19T11:15:00"
    },
    {
      "attempt_id": 502,
      "student_name": "Priya Sharma",
      "student_id": 11,
      "attempt_number": 1,
      "score": 100.0,
      "time_taken_seconds": 900,
      "submission_date": "2024-06-19T11:30:00"
    }
  ]
}
```

---

## 🤔 6. STUDENT RAISE DOUBT (To Implement)

**TODO:** Implement endpoints for doubts
```
POST /assignments/{assignment_id}/doubts
GET /assignments/{assignment_id}/doubts
POST /assignments/{assignment_id}/doubts/{doubt_id}/reply
```

### Proposed Body for Creating Doubt

```json
{
  "question_id": 101,
  "doubt_text": "Why is the factorization (x-2)(x-3) and not (x+2)(x+3)?",
  "doubt_summary": "Confusion about sign in factorization"
}
```

### Proposed Response

```json
{
  "id": 501,
  "assignment_id": 42,
  "student_id": 10,
  "question_id": 101,
  "doubt_text": "Why is the factorization (x-2)(x-3) and not (x+2)(x+3)?",
  "status": "Open",
  "created_at": "2024-06-19T11:45:00",
  "replies": [
    {
      "id": 601,
      "teacher_id": 5,
      "reply_text": "Because the equation is x² - 5x + 6 = 0, the constant term is +6 (positive) and the middle term is -5 (negative). This means both roots are negative...",
      "step_solutions": "Step 1: ...",
      "created_at": "2024-06-19T12:00:00"
    }
  ]
}
```

---

## ⭐ 7. VIEW TEACHER PROFILE & STATS

### Endpoint
```
GET /teachers/{teacher_id}/profile
```

### Response

```json
{
  "teacher_id": 5,
  "teacher_name": "Dr. Raj Kumar",
  "school_name": "Delhi Public School",
  "school_address": "New Delhi, Delhi",
  "average_rating": 4.8,
  "total_exams_count": 0,
  "total_assignments_count": 15,
  "total_participants_count": 248
}
```

---

## 📝 ERROR HANDLING

### Error 1: Missing Questions

```json
{
  "detail": "Assignment must contain at least one question before publishing."
}
```

### Error 2: Unauthorized Publish

```json
{
  "detail": "Only the owner can publish this assignment."
}
```

### Error 3: Assignment Not Found

```json
{
  "detail": "Assignment not found."
}
```

### Error 4: Unauthorized Student

```json
{
  "detail": "Only students may view student assignments."
}
```

---

## 🔄 Complete Workflow Example

### Step 1: Teacher Creates Draft
```bash
curl -X POST "http://localhost:8000/assignments" \
  -H "Authorization: Bearer TEACHER_TOKEN" \
  -d '{"board":"CBSE", "class_name":"10", ...}'
```
Response: `{"id": 42, "status": "Draft"}`

### Step 2: Teacher Publishes
```bash
curl -X POST "http://localhost:8000/assignments/42/publish" \
  -H "Authorization: Bearer TEACHER_TOKEN" \
  -d '{"assignment_type":"Academic", "improvement_categories":[...]}'
```

### Step 3: Student Views
```bash
curl -X GET "http://localhost:8000/students/10/assignments?subject=Mathematics" \
  -H "Authorization: Bearer STUDENT_TOKEN"
```
Response: List of published assignments

### Step 4: Student Attempts
```bash
curl -X POST "http://localhost:8000/assignments/42/attempts" \
  -H "Authorization: Bearer STUDENT_TOKEN" \
  -d '{"submitted_answers":{"1":"A","2":"B","3":"C"}, "score":75, "time_taken_seconds":1800}'
```

### Step 5: Check Attempts (Admin)
```bash
curl -X GET "http://localhost:8000/assignments/42/attempts" \
  -H "Authorization: Bearer ADMIN_TOKEN"
```
Response: All student attempts with scores

---

## 🗂️ Database Tables

| Table | Purpose |
|-------|---------|
| `assignments` | Main assignment with topic, summary, content |
| `assignment_questions` | Q&A (multiple choice) for each assignment |
| `assignment_key_points` | Learning steps/points |
| `assignment_images` | Supporting images |
| `assignment_pdfs` | Supporting PDFs |
| `assignment_video_links` | Supporting videos |
| `publish_configurations` | Publishing settings (type, categories, rewards) |
| `student_assignment_attempts` | Track each student's attempt with score |
| `assignment_doubts` | Student doubts on assignments |
| `doubt_replies` | Teacher replies to doubts |
| `assignment_reports` | Student reports on inappropriate content |

---

## 🔐 Authentication

All endpoints require JWT token in Authorization header:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Token obtained from login:**
```bash
curl -X POST "http://localhost:8000/auth/login" \
  -d '{"email":"teacher@example.com", "password":"password123"}'
```

---

## 👥 Role-Based Access

| Action | Teacher | Student | Admin |
|--------|---------|---------|-------|
| Create Assignment | ✅ Own | ❌ | ✅ |
| Publish Assignment | ✅ Own | ❌ | ✅ |
| View Published | ✅ All | ✅ All | ✅ All |
| Submit Attempt | ❌ | ✅ | ❌ |
| View Attempts | ✅ Own | ✅ Own | ✅ All |
| Raise Doubt | ❌ | ✅ | ❌ |
| Reply to Doubt | ✅ Own | ❌ | ✅ |

---

## 🎯 Key Differences: Assignment vs Assignment Activities

| Feature | Assignments | Assignment Activities |
|---------|-------------|----------------------|
| **Model** | Topic/Summary/Q&A | Tasks/Subtasks |
| **Creation** | Teacher creates content | Teacher creates activities |
| **Publishing** | Draft → Published state | Immediate activation |
| **Questions** | Multiple choice Q&A | No questions |
| **Attempts** | Students submit answers with scores | Task completion tracking |
| **Student View** | Individual attempt records | Task completion status |
| **Doubts** | Question-specific doubts | General activity doubts |
| **Use Case** | Online assessments, self-learning | Classroom activity tracking |

---

## ✅ Implementation Checklist

- [x] Create draft assignment (POST)
- [x] Update draft assignment (PUT)
- [x] View assignment (GET)
- [x] Publish assignment (POST)
- [x] Unpublish assignment (POST)
- [x] List published assignments (GET)
- [x] Submit student attempt (POST)
- [x] View teacher profile (GET)
- [ ] List all attempts for assignment (GET)
- [ ] Student raise doubt (POST) - Model exists, endpoint needed
- [ ] Teacher reply to doubt (POST) - Model exists, endpoint needed
- [ ] List doubts (GET) - Model exists, endpoint needed
- [ ] Report assignment (POST) - Model exists, endpoint needed

---

## 🚀 Next Steps

1. **Implement Doubts Endpoints** - Allow students to ask questions on specific Q&A items
2. **Implement Attempts List** - Allow admin/teacher to see all student attempts
3. **Add Filtering** - Filter assignments by difficulty level, topic, etc.
4. **Add Feedback** - Collect student feedback on assignments
5. **Analytics** - Show performance trends across students
6. **Notifications** - Notify students when new assignments published

---

## 📞 Support

For API support or questions about:
- Assignment creation with Q&A
- Student attempt tracking
- Doubt management
- Report handling

Check with your backend team or review the assignment routes implementation.

