# Assignment Activities API - POST Body & Usage Guide

## 📌 Endpoint Overview

**Endpoint:** `POST /assignment-activities/`  
**Base URL:** `http://localhost:8000` (dev) or `https://api.example.com` (prod)  
**Authentication:** Required (Bearer Token)  
**Authorized Roles:** `TEACHER`, `SELF_SIGNED_TEACHER`

---

## 📋 Complete API Body Structure

### Schema Definition

```json
{
  "title": "string (required)",
  "description": "string (optional)",
  "activity_type": "string (required)",
  "due_date": "datetime (optional, ISO 8601 format)",
  "class_id": "integer (optional)",
  "section_id": "integer (optional)",
  "subject_id": "integer (optional)",
  "chapter_id": "integer (optional, single chapter)",
  "chapter_ids": "array of integers (optional, multiple chapters)",
  "student_ids": "array of integers (optional, for regular teachers only)",
  "self_signed_student_ids": "array of integers (optional, for self-signed teachers only)",
  "tasks": [
    {
      "title": "string (required)",
      "description": "string (optional)",
      "file": "string (optional, file URL/path)"
    }
  ]
}
```

---

## ✅ Field Validation Rules

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `title` | string | ✅ Yes | Non-empty assignment title |
| `description` | string | ❌ No | Optional assignment description |
| `activity_type` | string | ✅ Yes | e.g., "homework", "classwork", "test", "project" |
| `due_date` | datetime | ❌ No | ISO 8601 format: "2024-06-18T23:59:59" |
| `class_id` | integer | ❌ No | Valid class ID from system |
| `section_id` | integer | ❌ No | Valid section ID from system |
| `subject_id` | integer | ❌ No | Valid subject ID from system |
| `chapter_id` | integer | ❌ No | Single chapter ID |
| `chapter_ids` | array | ❌ No | Multiple chapter IDs (takes precedence over `chapter_id`) |
| `student_ids` | array | ⚠️ Required for `TEACHER` | Valid student IDs assigned to the teacher's school |
| `self_signed_student_ids` | array | ⚠️ Required for `SELF_SIGNED_TEACHER` | Valid self-signed student IDs under the teacher |
| `tasks` | array | ✅ Yes | Minimum 1 task required, max can be unlimited |

---

## 📝 Example 1: Regular Teacher Creating Assignment

### Request Body

```json
{
  "title": "Chapter 5: Quadratic Equations",
  "description": "Solve 15 quadratic equations using different methods",
  "activity_type": "homework",
  "due_date": "2024-06-25T23:59:59",
  "class_id": 10,
  "section_id": 1,
  "subject_id": 5,
  "chapter_ids": [5, 6],
  "student_ids": [101, 102, 103, 104, 105],
  "tasks": [
    {
      "title": "Question Set A - Basic Quadratic Equations",
      "description": "Solve equations of the form ax² + bx + c = 0",
      "file": "https://s3.amazonaws.com/assignments/chapter5_basic.pdf"
    },
    {
      "title": "Question Set B - Word Problems",
      "description": "Solve real-world problems using quadratic equations",
      "file": "https://s3.amazonaws.com/assignments/chapter5_wordproblems.pdf"
    },
    {
      "title": "Question Set C - Advanced Problems",
      "description": "Challenging problems mixing multiple concepts",
      "file": null
    }
  ]
}
```

### Using cURL

```bash
curl -X POST "http://localhost:8000/assignment-activities/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Chapter 5: Quadratic Equations",
    "description": "Solve 15 quadratic equations using different methods",
    "activity_type": "homework",
    "due_date": "2024-06-25T23:59:59",
    "class_id": 10,
    "section_id": 1,
    "subject_id": 5,
    "chapter_ids": [5, 6],
    "student_ids": [101, 102, 103, 104, 105],
    "tasks": [
      {
        "title": "Question Set A - Basic Quadratic Equations",
        "description": "Solve equations of the form ax² + bx + c = 0",
        "file": "https://s3.amazonaws.com/assignments/chapter5_basic.pdf"
      },
      {
        "title": "Question Set B - Word Problems",
        "description": "Solve real-world problems using quadratic equations",
        "file": "https://s3.amazonaws.com/assignments/chapter5_wordproblems.pdf"
      },
      {
        "title": "Question Set C - Advanced Problems",
        "description": "Challenging problems mixing multiple concepts"
      }
    ]
  }'
```

### Using Python (requests library)

```python
import requests
from datetime import datetime, timedelta

url = "http://localhost:8000/assignment-activities/"
headers = {
    "Authorization": "Bearer YOUR_JWT_TOKEN",
    "Content-Type": "application/json"
}

payload = {
    "title": "Chapter 5: Quadratic Equations",
    "description": "Solve 15 quadratic equations using different methods",
    "activity_type": "homework",
    "due_date": (datetime.now() + timedelta(days=7)).isoformat(),
    "class_id": 10,
    "section_id": 1,
    "subject_id": 5,
    "chapter_ids": [5, 6],
    "student_ids": [101, 102, 103, 104, 105],
    "tasks": [
        {
            "title": "Question Set A - Basic Quadratic Equations",
            "description": "Solve equations of the form ax² + bx + c = 0",
            "file": "https://s3.amazonaws.com/assignments/chapter5_basic.pdf"
        },
        {
            "title": "Question Set B - Word Problems",
            "description": "Solve real-world problems using quadratic equations",
            "file": "https://s3.amazonaws.com/assignments/chapter5_wordproblems.pdf"
        },
        {
            "title": "Question Set C - Advanced Problems",
            "description": "Challenging problems mixing multiple concepts"
        }
    ]
}

response = requests.post(url, json=payload, headers=headers)
print(response.status_code)
print(response.json())
```

### Expected Response (Success: 201)

```json
{
  "id": 42,
  "detail": "Assignment activity created successfully."
}
```

---

## 📝 Example 2: Self-Signed Teacher Creating Assignment

### Request Body

```json
{
  "title": "English Grammar - Tenses",
  "description": "Practice different English tenses",
  "activity_type": "classwork",
  "due_date": "2024-06-20T18:00:00",
  "self_signed_student_ids": [501, 502, 503],
  "tasks": [
    {
      "title": "Task 1: Simple Present Tense",
      "description": "Fill in the blanks with correct simple present forms"
    },
    {
      "title": "Task 2: Past Continuous Tense",
      "description": "Complete sentences using past continuous tense"
    }
  ]
}
```

### Using Python

```python
import requests

url = "http://localhost:8000/assignment-activities/"
headers = {
    "Authorization": "Bearer SELF_SIGNED_TEACHER_TOKEN",
    "Content-Type": "application/json"
}

payload = {
    "title": "English Grammar - Tenses",
    "description": "Practice different English tenses",
    "activity_type": "classwork",
    "due_date": "2024-06-20T18:00:00",
    "self_signed_student_ids": [501, 502, 503],
    "tasks": [
        {
            "title": "Task 1: Simple Present Tense",
            "description": "Fill in the blanks with correct simple present forms"
        },
        {
            "title": "Task 2: Past Continuous Tense",
            "description": "Complete sentences using past continuous tense"
        }
    ]
}

response = requests.post(url, json=payload, headers=headers)
if response.status_code == 201:
    print("✅ Assignment created successfully!")
    print(f"Assignment ID: {response.json()['id']}")
else:
    print(f"❌ Error: {response.status_code}")
    print(response.json())
```

---

## 📝 Example 3: Minimal Assignment (Only Required Fields)

### Request Body

```json
{
  "title": "Quick Quiz",
  "activity_type": "test",
  "student_ids": [101, 102],
  "tasks": [
    {
      "title": "10 Multiple Choice Questions"
    }
  ]
}
```

### Using cURL

```bash
curl -X POST "http://localhost:8000/assignment-activities/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Quick Quiz",
    "activity_type": "test",
    "student_ids": [101, 102],
    "tasks": [{"title": "10 Multiple Choice Questions"}]
  }'
```

---

## ⚠️ Error Cases & Validation

### Error 1: Missing Tasks

**Request:**
```json
{
  "title": "Assignment Title",
  "activity_type": "homework",
  "student_ids": [101],
  "tasks": []
}
```

**Response (400):**
```json
{
  "detail": "At least one task is required."
}
```

---

### Error 2: Teacher Mixing Student Types

**Request:**
```json
{
  "title": "Assignment",
  "activity_type": "homework",
  "student_ids": [101, 102],
  "self_signed_student_ids": [501, 502],
  "tasks": [{"title": "Task 1"}]
}
```

**Response (400):**
```json
{
  "detail": "Teacher cannot assign activities to self-signed students."
}
```

---

### Error 3: Missing Student IDs (Regular Teacher)

**Request:**
```json
{
  "title": "Assignment",
  "activity_type": "homework",
  "tasks": [{"title": "Task 1"}]
}
```

**Response (400):**
```json
{
  "detail": "Teacher must provide student_ids for assignment creation."
}
```

---

### Error 4: Missing Student IDs (Self-Signed Teacher)

**Request:**
```json
{
  "title": "Assignment",
  "activity_type": "homework",
  "student_ids": [101],
  "tasks": [{"title": "Task 1"}]
}
```

**Response (400):**
```json
{
  "detail": "Self-signed teacher cannot assign activities to internal students."
}
```

---

### Error 5: Invalid Chapter IDs

**Request:**
```json
{
  "title": "Assignment",
  "activity_type": "homework",
  "chapter_ids": [999, 1000],
  "student_ids": [101],
  "tasks": [{"title": "Task 1"}]
}
```

**Response (404):**
```json
{
  "detail": "One or more chapters/topics not found."
}
```

---

### Error 6: Invalid Student IDs

**Request:**
```json
{
  "title": "Assignment",
  "activity_type": "homework",
  "student_ids": [9999, 10000],
  "tasks": [{"title": "Task 1"}]
}
```

**Response (404):**
```json
{
  "detail": "One or more internal students not found."
}
```

---

### Error 7: Unauthorized (Invalid Token)

**Response (403):**
```json
{
  "detail": "Not authenticated"
}
```

---

### Error 8: Blocked/Rejected Self-Signed Teacher

**Response (403):**
```json
{
  "detail": "Self-signed teacher account is not active."
}
```

---

## 🔄 Request-Response Flow

```
1. CLIENT sends POST request with JWT token
   ↓
2. SERVER validates authentication
   ↓
3. SERVER retrieves teacher/self-signed teacher profile
   ↓
4. SERVER validates request body:
   - Check if tasks array is not empty
   - Validate chapter IDs if provided
   - Validate student IDs based on teacher type
   ↓
5. SERVER creates:
   - AssignmentActivity record
   - AssignmentActivityTask records (for each task)
   - AssignmentActivityStudent records (for each student)
   - AssignmentActivityTaskStatus records (for each task × student combination)
   ↓
6. SERVER commits transaction
   ↓
7. SERVER returns 201 Created with assignment ID
```

---

## 🛠️ Advanced Features

### Multiple Chapters Assignment

```json
{
  "title": "Complex Topics",
  "activity_type": "project",
  "chapter_ids": [5, 6, 7, 8],
  "student_ids": [101, 102],
  "tasks": [
    {
      "title": "Phase 1: Research",
      "description": "Research topics from chapters 5-8"
    },
    {
      "title": "Phase 2: Analysis",
      "description": "Analyze findings"
    },
    {
      "title": "Phase 3: Presentation",
      "description": "Create presentation"
    }
  ]
}
```

### Assignment with File References

```json
{
  "title": "Video Analysis Assignment",
  "activity_type": "homework",
  "student_ids": [101, 102],
  "tasks": [
    {
      "title": "Watch Videos",
      "file": "https://s3.amazonaws.com/videos/intro.mp4"
    },
    {
      "title": "Read Study Material",
      "file": "https://s3.amazonaws.com/docs/study-guide.pdf"
    },
    {
      "title": "Submit Analysis",
      "description": "Write your analysis (no file needed)"
    }
  ]
}
```

---

## 📊 Activity Types (Recommended)

- `homework` - Home assignments
- `classwork` - In-class work
- `test` - Quizzes/tests
- `project` - Project work
- `assessment` - Formal assessments
- `practice` - Practice exercises
- `lab` - Laboratory work
- `assignment` - General assignment

---

## 🔐 Authentication

All requests require a valid JWT token in the Authorization header:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Obtain token via login endpoint:
```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"teacher@example.com", "password":"password123"}'
```

---

## 📱 Sample Integration (Node.js)

```javascript
const axios = require('axios');

async function createAssignment() {
  try {
    const response = await axios.post(
      'http://localhost:8000/assignment-activities/',
      {
        title: "Mathematics Assignment",
        description: "Algebra Practice",
        activity_type: "homework",
        due_date: new Date(Date.now() + 7*24*60*60*1000).toISOString(),
        class_id: 10,
        student_ids: [101, 102, 103],
        tasks: [
          {
            title: "Problem Set 1",
            description: "Basic algebra problems",
            file: "https://example.com/problems.pdf"
          },
          {
            title: "Problem Set 2",
            description: "Advanced problems"
          }
        ]
      },
      {
        headers: {
          'Authorization': `Bearer ${process.env.JWT_TOKEN}`,
          'Content-Type': 'application/json'
        }
      }
    );
    
    console.log('✅ Assignment created:', response.data);
  } catch (error) {
    console.error('❌ Error:', error.response?.data || error.message);
  }
}

createAssignment();
```

---

## 📞 Related Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/assignment-activities/` | GET | List teacher's assignments |
| `/assignment-activities/{id}/details/` | GET | Get assignment details |
| `/assignment-activities/student/` | GET | List student assignments |
| `/assignment-activities/student/{id}/` | GET | Get student assignment details |
| `/assignment-activities/student/task-status/` | PATCH | Mark task complete |
| `/assignment-activities/{id}/doubt` | POST | Create doubt |
| `/assignment-activities/{id}/report` | POST | Report assignment |

---

## 💡 Best Practices

1. **Always validate student IDs** - Ensure students belong to your school/teaching group
2. **Use chapter_ids for grouping** - Better organization than single chapter_id
3. **Provide clear descriptions** - Help students understand expectations
4. **Set reasonable due dates** - Consider student workload
5. **Include file URLs** - Link to study materials when available
6. **Minimum 1 task** - Always include at least one task
7. **Test with sample data** - Verify functionality before production use
8. **Handle errors gracefully** - Check response status codes

---

## ✨ Success Checklist

- [ ] Authentication token obtained and valid
- [ ] Teacher/self-signed teacher role verified
- [ ] Assignment title provided (non-empty)
- [ ] Activity type specified
- [ ] At least one task created
- [ ] Correct student IDs provided (matching teacher type)
- [ ] All chapters, sections, subjects exist in system
- [ ] Due date in proper ISO 8601 format
- [ ] File URLs are accessible
- [ ] Request sent with Content-Type: application/json

---

## 🚀 Next Steps After Creation

After successfully creating an assignment:

1. **View Assignment** - GET `/assignment-activities/{id}/details/`
2. **Track Progress** - GET `/assignment-activities/dashboard/summary`
3. **Monitor Completion** - GET `/assignment-activities/search/filtered`
4. **Manage Doubts** - POST `/assignment-activities/{id}/doubt`
5. **View Reports** - GET `/assignment-activities/admin/reports`

