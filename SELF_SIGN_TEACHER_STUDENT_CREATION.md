# Self Sign Teacher → Self Sign Student Creation API

## Overview

This implementation enables **Self Sign Teachers** to create and manage **Self Sign Students** following the existing **School → Student Creation** flow and patterns. Teachers can create students, update profiles, manage status, and track student information.

## Key Features

✅ **Full Student Creation** - Teachers can create students with complete profile information  
✅ **Profile Image Support** - Base64 image upload to S3 (same pattern as School Students)  
✅ **Verification Email** - Automated email with verification link (School Student pattern)  
✅ **Status Management** - TRIAL → ACTIVE lifecycle with expiry dates  
✅ **Full CRUD Operations** - Create, Read, Update, Deactivate student profiles  
✅ **Authorization** - Teachers can only manage their own students  
✅ **Action Logging** - All operations logged with ActionType and ResourceType  
✅ **Backward Compatible** - Existing self-registration flows unchanged  

---

## Student Status Lifecycle

### Creation to Active Flow

```
Teacher Creates Student
         ↓
User Account Created (role=SELF_SIGNED_STUDENT)
SelfSignedStudent Created with TRIAL status (1 day expiry)
Verification Email Sent
         ↓
Student Verifies Email
         ↓
Teacher Activates Student (or student self-initiates)
Student Status → ACTIVE (90 days expiry)
         ↓
After 90 days: Can renew or deactivate
```

### Status Values

- **TRIAL**: Initial state after creation (1 day expiry). Student can access limited features.
- **ACTIVE**: Full access granted (90 days expiry). Student can take exams, submit assignments.
- **INACTIVE**: Deactivated. Can be reactivated by teacher.

---

## API Endpoints

### 1. Create Student (Teacher Initiated)

**Endpoint:** `POST /self-signed-teacher/students/create`

**Authentication:** Required (Self Sign Teacher, APPROVED status)

**Request Body:**
```json
{
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  "phone": "9876543210",
  "select_board": "CBSE",
  "select_medium": "English",
  "select_class_id": 5,
  "school_name": "Govt. High School",
  "school_location": "Mumbai",
  "profile_image": "data:image/png;base64,iVBORw0KGgo...",
  "pin": 400001,
  "division": "North",
  "district": "Mumbai",
  "state": "Maharashtra",
  "plot": "123 Main Street",
  "parent_name": "Jane Doe",
  "relation": "Mother",
  "parent_phone": "9876543211",
  "parent_email": "jane.doe@example.com",
  "occupation": "Doctor"
}
```

**Field Descriptions:**
- `first_name` (string, required): Student's first name
- `last_name` (string, required): Student's last name
- `email` (string, required): Unique email address
- `phone` (string, required): 10-digit phone number
- `select_board` (string, optional): Board name (CBSE, ICSE, etc.)
- `select_medium` (string, optional): Medium of instruction (English, Hindi, etc.)
- `select_class_id` (integer, optional): Reference to SchoolClassSubject ID (for exam pool)
- `school_name` (string, optional): Current/previous school name
- `school_location` (string, optional): School location
- `profile_image` (string, optional): Base64 encoded profile image (PNG/JPG)
- `pin` (integer, optional): Postal code
- `division` (string, optional): Administrative division
- `district` (string, optional): District name
- `state` (string, optional): State name
- `plot` (string, optional): Street address
- `parent_name` (string, optional): Guardian/parent name
- `relation` (string, optional): Relation to student (Mother, Father, etc.)
- `parent_phone` (string, optional): Parent phone number
- `parent_email` (string, optional): Parent email
- `occupation` (string, optional): Parent occupation

**Response (201 Created):**
```json
{
  "detail": "Student account created successfully. Verification email sent.",
  "id": 42,
  "user_id": 156,
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  "phone": "9876543210",
  "profile_image": "https://s3.amazonaws.com/...",
  "select_board": "CBSE",
  "select_medium": "English",
  "select_class_id": 5,
  "school_name": "Govt. High School",
  "school_location": "Mumbai",
  "pin": 400001,
  "division": "North",
  "district": "Mumbai",
  "state": "Maharashtra",
  "plot": "123 Main Street",
  "parent_name": "Jane Doe",
  "relation": "Mother",
  "parent_phone": "9876543211",
  "parent_email": "jane.doe@example.com",
  "occupation": "Doctor",
  "status": "TRIAL",
  "status_expiry_date": "2026-06-06T10:30:00Z",
  "created_at": "2026-06-05T10:30:00Z",
  "email_sent": true
}
```

**Error Responses:**
- `400` - Email already exists
- `400` - S3 upload failed
- `403` - Teacher not approved
- `404` - Teacher profile not found

---

### 2. Get Student Details

**Endpoint:** `GET /self-signed-teacher/students/{student_id}`

**Authentication:** Required (Self Sign Teacher, APPROVED status)

**Path Parameters:**
- `student_id` (integer, required): ID of the student to retrieve

**Response (200 OK):**
```json
{
  "id": 42,
  "user_id": 156,
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  "phone": "9876543210",
  "profile_image": "https://s3.amazonaws.com/...",
  "select_board": "CBSE",
  "select_medium": "English",
  "select_class_id": 5,
  "school_name": "Govt. High School",
  "school_location": "Mumbai",
  "pin": 400001,
  "division": "North",
  "district": "Mumbai",
  "state": "Maharashtra",
  "plot": "123 Main Street",
  "status": "TRIAL",
  "status_expiry_date": "2026-06-06T10:30:00Z",
  "parent_name": "Jane Doe",
  "relation": "Mother",
  "parent_phone": "9876543211",
  "parent_email": "jane.doe@example.com",
  "occupation": "Doctor",
  "created_at": "2026-06-05T10:30:00Z"
}
```

**Error Responses:**
- `403` - Teacher not approved
- `404` - Teacher profile not found
- `404` - Student not found or not your student

---

### 3. List Teacher's Students

**Endpoint:** `GET /self-signed-teacher/students/`

**Authentication:** Required (Self Sign Teacher, APPROVED status)

**Response (200 OK):**
```json
[
  {
    "id": 42,
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@example.com",
    "phone": "9876543210",
    "status": "TRIAL",
    "created_at": "2026-06-05T10:30:00Z"
  },
  {
    "id": 43,
    "first_name": "Jane",
    "last_name": "Smith",
    "email": "jane.smith@example.com",
    "phone": "9876543211",
    "status": "ACTIVE",
    "created_at": "2026-06-04T14:20:00Z"
  }
]
```

**Error Responses:**
- `403` - Teacher not approved
- `404` - Teacher profile not found

---

### 4. Update Student Profile

**Endpoint:** `PUT /self-signed-teacher/students/{student_id}`

**Authentication:** Required (Self Sign Teacher, APPROVED status)

**Path Parameters:**
- `student_id` (integer, required): ID of the student to update

**Request Body (all fields optional):**
```json
{
  "first_name": "Jonathan",
  "last_name": "Doe",
  "phone": "9876543220",
  "profile_image": "data:image/png;base64,iVBORw0KGgo...",
  "select_board": "IB",
  "select_medium": "French",
  "school_name": "Meru Academy",
  "parent_name": "Michael Doe"
}
```

**Response (200 OK):** Returns updated student object (same as Get Student Details)

**Error Responses:**
- `400` - S3 upload failed
- `403` - Teacher not approved
- `404` - Teacher profile not found
- `404` - Student not found or not your student

**Notes:**
- Only provided fields are updated
- Profile image is uploaded to S3
- Changes to first_name/last_name sync to User.name
- Changes to phone sync to User.phone

---

### 5. Activate Student

**Endpoint:** `POST /self-signed-teacher/students/{student_id}/activate`

**Authentication:** Required (Self Sign Teacher, APPROVED status)

**Path Parameters:**
- `student_id` (integer, required): ID of the student to activate

**Request Body:** Empty

**Response (200 OK):**
```json
{
  "detail": "Student activated successfully. New status: ACTIVE",
  "student_id": 42,
  "status": "ACTIVE",
  "status_expiry_date": "2026-09-03T10:30:00Z"
}
```

**Status Transition Logic:**
- **TRIAL → ACTIVE**: Sets expiry to now + 90 days
- **INACTIVE → ACTIVE**: Sets expiry to now + 90 days (reactivation)
- **ACTIVE → ACTIVE**: Extends expiry by 90 days from current expiry (renewal)

**Error Responses:**
- `403` - Teacher not approved
- `404` - Teacher profile not found
- `404` - Student not found or not your student

---

### 6. Deactivate Student

**Endpoint:** `POST /self-signed-teacher/students/{student_id}/deactivate`

**Authentication:** Required (Self Sign Teacher, APPROVED status)

**Path Parameters:**
- `student_id` (integer, required): ID of the student to deactivate

**Request Body:** Empty

**Response (200 OK):**
```json
{
  "detail": "Student deactivated successfully.",
  "student_id": 42,
  "status": "INACTIVE"
}
```

**Error Responses:**
- `403` - Teacher not approved
- `404` - Teacher profile not found
- `404` - Student not found or not your student

**Notes:**
- Sets student status to INACTIVE
- Can be reactivated by calling activate endpoint
- Student loses access to exams and assignments during INACTIVE period

---

## Existing Endpoints (Unchanged)

The following existing endpoints remain **unchanged** and continue to work as before:

### Self-Registration (Public, No Auth)
- `POST /self-signed-teacher/join/` - Students join with invite code

### Teacher Profile Management (Auth Required)
- `GET /self-signed-teacher/profile/` - Get teacher profile
- `PUT /self-signed-teacher/profile/` - Update teacher profile
- `POST /self-signed-teacher/upload-id-card/` - Upload ID card
- `GET /self-signed-teacher/verification-status/` - Check verification status
- `GET /self-signed-teacher/invite-code/` - Get invite code

---

## Authorization & Security

### Permission Requirements

All teacher-initiated student management endpoints require:

1. **Authentication**: User must be logged in
2. **Role**: User must have `SELF_SIGNED_TEACHER` role
3. **Verification Status**: Teacher's `verification_status` must be `"approved"`
4. **Ownership**: Teacher can only access/modify their own students

### Teacher Approval Status

Teachers transition through verification states:
- **pending**: Account awaiting admin review (cannot create students)
- **approved**: Admin approved (can create students) ✅
- **blocked**: Admin blocked (cannot access APIs)
- **rejected**: Application rejected

### Student Ownership

The filter `self_signed_teacher_id == teacher.id` ensures teachers can only:
- View their own students
- Update their own students' profiles
- Activate/deactivate their own students

### Authorization Errors

- `403 Forbidden` - Teacher role check fails
- `403 Forbidden` - Teacher not approved by admin
- `404 Not Found` - Student not found (or belongs to different teacher)

---

## Important Notes

### Status Expiry Dates

- **TRIAL**: Automatically set to now + 1 day on creation
- **ACTIVE**: Automatically set to now + 90 days on first activation
- **Renewal**: Extends from existing expiry date or now (whichever is later)

### Email Verification

- Verification email is sent on student creation with `account_verification.html` template
- Uses same token generation as School Students
- Link format: `https://testapi.vidyawings.com/users/verify-account?token={token}`
- Non-blocking: Failure doesn't prevent student creation

### Profile Image Upload

- Supports base64-encoded PNG/JPG images
- Uploaded to S3: `self_signed_students/{teacher_id}/profile`
- URL returned in response
- Optional field - can be added later via update endpoint

### Action Logging

All operations are logged with:
- **ActionType**: CREATE, UPDATE, etc.
- **ResourceType**: STUDENT
- **Metadata**: student_id, teacher_id, additional context

---

## Backward Compatibility

✅ **Existing flows unchanged:**
- School Student creation (`POST /students/create`)
- School Student management
- Self Sign Student self-registration (`POST /users/` signup)
- Self Sign Student invite-based join (`POST /self-signed-teacher/join/`)
- Teacher profile management
- Teacher verification/approval flow

✅ **No database migrations needed:**
- SelfSignedStudent model already supports all fields
- No schema changes required
- Existing data unaffected

---

## Example Workflows

### Workflow 1: Complete Student Creation

```bash
# 1. Teacher creates student
curl -X POST "https://api.example.com/self-signed-teacher/students/create" \
  -H "Authorization: Bearer {teacher_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com",
    "phone": "9876543210",
    "select_board": "CBSE",
    "select_class_id": 5
  }'

# Response: student created with TRIAL status, email sent

# 2. Student verifies email (via link in email)
# Status remains TRIAL until teacher activates

# 3. Teacher activates student
curl -X POST "https://api.example.com/self-signed-teacher/students/42/activate" \
  -H "Authorization: Bearer {teacher_token}"

# Response: student.status = ACTIVE, expiry = now + 90 days

# 4. Teacher views student
curl -X GET "https://api.example.com/self-signed-teacher/students/42" \
  -H "Authorization: Bearer {teacher_token}"

# Response: Full student details with ACTIVE status
```

### Workflow 2: Update Student Profile

```bash
# Teacher updates student profile picture
curl -X PUT "https://api.example.com/self-signed-teacher/students/42" \
  -H "Authorization: Bearer {teacher_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "profile_image": "data:image/png;base64,iVBORw0KGgo...",
    "parent_name": "Jane Doe",
    "parent_email": "jane@example.com"
  }'

# Response: Updated student object with new profile_image URL
```

### Workflow 3: Renew Student Access

```bash
# 1. Check student status before 90-day expiry
curl -X GET "https://api.example.com/self-signed-teacher/students/42" \
  -H "Authorization: Bearer {teacher_token}"

# If status_expiry_date approaching:

# 2. Extend student access by 90 days
curl -X POST "https://api.example.com/self-signed-teacher/students/42/activate" \
  -H "Authorization: Bearer {teacher_token}"

# Response: status_expiry_date extended by 90 days
```

---

## Status Codes Reference

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 200 | Success (GET, PUT, POST actions) | Operation succeeded |
| 201 | Resource Created | Student successfully created |
| 400 | Bad Request | Email exists, invalid S3 upload |
| 403 | Forbidden | Teacher not approved, wrong role |
| 404 | Not Found | Student/teacher not found, wrong student |
| 500 | Server Error | Database error, unexpected exception |

---

## Testing Checklist

- [ ] Create student as approved teacher
- [ ] Verify email sent on creation
- [ ] Get student details as teacher
- [ ] List teacher's students
- [ ] Update student profile with new image
- [ ] Activate student (TRIAL → ACTIVE)
- [ ] Renew student (extend ACTIVE by 90 days)
- [ ] Deactivate student (ACTIVE → INACTIVE)
- [ ] Reactivate deactivated student
- [ ] Verify teacher can't access other teacher's students
- [ ] Verify unapproved teacher gets 403 error
- [ ] Verify self-registration endpoint still works
- [ ] Verify School Student creation still works
