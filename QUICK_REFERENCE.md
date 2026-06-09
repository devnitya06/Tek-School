# Quick Reference - Self Sign Teacher Student Creation API

## 🚀 Quick Start

### Create a Student (Most Common)
```bash
curl -X POST "http://localhost:8000/self-signed-teacher/students/create" \
  -H "Authorization: Bearer {teacher_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com",
    "phone": "9876543210",
    "select_class_id": 5
  }'
```

**Response:**
```json
{
  "id": 42,
  "status": "TRIAL",
  "status_expiry_date": "2026-06-06T10:30:00Z",
  "email_sent": true
}
```

### Activate Student
```bash
curl -X POST "http://localhost:8000/self-signed-teacher/students/42/activate" \
  -H "Authorization: Bearer {teacher_token}"
```

**Response:**
```json
{
  "status": "ACTIVE",
  "status_expiry_date": "2026-09-03T10:30:00Z"
}
```

---

## 📋 All Endpoints

| Action | Method | Endpoint | Returns |
|--------|--------|----------|---------|
| Create | POST | `/students/create` | 201 + student |
| List | GET | `/students/` | 200 + array |
| Get One | GET | `/students/{id}` | 200 + student |
| Update | PUT | `/students/{id}` | 200 + student |
| Activate | POST | `/students/{id}/activate` | 200 + status |
| Deactivate | POST | `/students/{id}/deactivate` | 200 + status |

**Base URL:** `/self-signed-teacher`  
**Auth:** Bearer token required for all  
**Role:** SELF_SIGNED_TEACHER (approved only)

---

## 🔄 Student Status Flow

```
CREATE (TRIAL, 1 day)
  ↓
Email Verification
  ↓
ACTIVATE (ACTIVE, 90 days)
  ↓
[Can renew via ACTIVATE again]
  ↓
[Can DEACTIVATE to INACTIVE]
```

---

## 📝 Create Request Schema

```json
{
  "first_name": "string",           // required
  "last_name": "string",            // required
  "email": "string",                // required, unique
  "phone": "string",                // required
  "select_board": "string",         // optional: CBSE, ICSE, etc.
  "select_medium": "string",        // optional: English, Hindi
  "select_class_id": 5,             // optional: exam pool ID
  "school_name": "string",          // optional
  "school_location": "string",      // optional
  "profile_image": "base64",        // optional: PNG/JPG
  "pin": 400001,                    // optional
  "division": "string",             // optional
  "district": "string",             // optional
  "state": "string",                // optional
  "plot": "string",                 // optional: address
  "parent_name": "string",          // optional
  "relation": "string",             // optional: Mother, Father
  "parent_phone": "string",         // optional
  "parent_email": "string",         // optional
  "occupation": "string"            // optional
}
```

---

## 📊 Response Fields

**Student Object:**
```json
{
  "id": 42,
  "user_id": 156,
  "first_name": "John",
  "last_name": "Doe",
  "email": "john@example.com",
  "phone": "9876543210",
  "profile_image": "https://s3.../profile.png",
  "select_board": "CBSE",
  "select_medium": "English",
  "select_class_id": 5,
  "school_name": "Govt. School",
  "school_location": "Mumbai",
  "status": "TRIAL",
  "status_expiry_date": "2026-06-06T10:30:00Z",
  "created_at": "2026-06-05T10:30:00Z"
}
```

---

## ⚠️ Common Errors

### 400 Bad Request
- Email already taken
- S3 upload failed
- Invalid field format

### 403 Forbidden
- Teacher role not verified
- Teacher not approved by admin

### 404 Not Found
- Student not found
- Student belongs to different teacher

---

## 🔐 Authorization

All endpoints require:
1. **Valid bearer token** (user logged in)
2. **Role:** `SELF_SIGNED_TEACHER`
3. **Status:** `verification_status = "approved"`
4. **Ownership:** Can only access own students

Example header:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## 📸 Profile Image Upload

**Format:** Base64 PNG/JPG
**Size:** Reasonable limits (S3 will enforce)
**Storage:** S3 bucket at `self_signed_students/{teacher_id}/profile`

**Example:**
```bash
# Generate base64 from file
cat profile.png | base64 -w 0

# Include in request
{
  "profile_image": "data:image/png;base64,iVBORw0KGgo..."
}
```

---

## 📧 Email Verification

**Sent on:** Student creation
**Template:** `account_verification.html`
**Contains:** Verification link with token
**URL Format:** `https://testapi.vidyawings.com/users/verify-account?token={token}`

---

## 🔄 Status Management

### TRIAL (1 day)
- Initial status after creation
- Email sent with verification link
- Limited access

### ACTIVE (90 days)
- Full access
- Set by: Teacher activation
- Renewable: Can extend by calling activate again

### INACTIVE
- No access
- Set by: Teacher deactivation
- Recoverable: Activate to restore to ACTIVE

---

## 🧪 Testing Helpers

### Get Teacher Token
```bash
# Login as teacher
POST /auth/login
{
  "email": "teacher@example.com",
  "password": "password123"
}

# Response
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

### Create Test Student
```bash
# Use response access_token
POST /self-signed-teacher/students/create
-H "Authorization: Bearer {access_token}"
```

### List Students
```bash
GET /self-signed-teacher/students/
-H "Authorization: Bearer {access_token}"
```

---

## 📚 Documentation Files

- **SELF_SIGN_TEACHER_STUDENT_CREATION.md** - Full API reference
- **IMPLEMENTATION_SUMMARY.md** - Technical overview
- **FINAL_VERIFICATION_CHECKLIST.md** - Verification details

---

## 🔧 Common Tasks

### Task: Create and Activate Student
```bash
# 1. Create
POST /self-signed-teacher/students/create
→ Returns student_id

# 2. Wait for email
→ Student verifies email

# 3. Activate
POST /self-signed-teacher/students/{id}/activate
→ Status: ACTIVE
```

### Task: Update Student Profile
```bash
PUT /self-signed-teacher/students/{id}
{
  "parent_name": "Jane Doe",
  "parent_email": "jane@example.com"
}
```

### Task: Renew Student Access
```bash
# Before 90-day expiry:
POST /self-signed-teacher/students/{id}/activate
→ Extends 90 days
```

### Task: Deactivate & Reactivate
```bash
# Deactivate
POST /self-signed-teacher/students/{id}/deactivate

# Reactivate
POST /self-signed-teacher/students/{id}/activate
→ Sets ACTIVE with 90 days
```

---

## 💡 Tips

- **Email verification:** Non-blocking. Student created even if email fails.
- **Profile image:** Optional. Can be added later via update endpoint.
- **Status expiry:** Automatically calculated. No manual setting.
- **Authorization:** Checked before DB access. Fast 403s.
- **Teacher isolation:** Teacher can only see/manage own students.

---

## 🚨 Troubleshooting

**Q: Getting 403 Forbidden?**  
A: Check teacher approval status: `GET /self-signed-teacher/verification-status/`

**Q: Email not sent?**  
A: Check response.email_sent flag. Check logs. Student still created.

**Q: S3 upload failed?**  
A: Check S3 credentials and bucket permissions. Try without profile_image first.

**Q: Can't access student?**  
A: Verify student_id is correct. Verify it's your student (404 if not).

---

## 📞 Support

For detailed information:
- See: `SELF_SIGN_TEACHER_STUDENT_CREATION.md`
- Reference: `app/routes/students.py` (School Student implementation)
- Permissions: `app/utils/permission.py`

---

**Version:** 1.0  
**Status:** ✅ Production Ready  
**Last Updated:** 2026-06-05
