# Teacher and Staff Payment APIs - Postman Documentation

## Base URL
```
http://localhost:8000
```

## Authentication
All endpoints require authentication. Include the JWT token in the Authorization header:
```
Authorization: Bearer <your_jwt_token>
```

---

## Teacher Payment APIs

### 1. Make Payment to Teacher
**POST** `/teacher/{teacher_id}/payments/`

Record a monthly payment for a teacher. Prevents duplicate payments for the same month.

**Path Parameters:**
- `teacher_id` (string, required): Teacher ID (e.g., "TCH-123456")

**Request Body:**
```json
{
  "payment_month": "2025-01",
  "release_date": "2025-01-15T10:00:00",
  "total_amount": 50000.0,
  "payment_mode": "Online"
}
```

**Payment Mode Options:**
- `"Online"`
- `"Cash in hand"`
- `"Account transfer"`

**Example Request:**
```bash
POST http://localhost:8000/teacher/TCH-123456/payments/
Content-Type: application/json
Authorization: Bearer <your_token>

{
  "payment_month": "2025-01",
  "release_date": "2025-01-15T10:00:00",
  "total_amount": 50000.0,
  "payment_mode": "Online"
}
```

**Success Response (201 Created):**
```json
{
  "id": 1,
  "payment_month": "2025-01",
  "total_amount": 50000.0,
  "payment_mode": "Online",
  "release_date": "2025-01-15T10:00:00",
  "created_at": "2025-01-15T10:05:23.123456"
}
```

**Error Responses:**
- `400 Bad Request`: 
  - Payment for month already exists
  - Invalid payment_month format (must be YYYY-MM)
  - Cannot make payment for future months
  - Payment structure not found
- `403 Forbidden`: Only school users can make payments
- `404 Not Found`: 
  - Teacher not found or doesn't belong to your school
  - School profile not found

---

### 2. Make Bulk Payments to Teachers
**POST** `/teacher/bulk-payments/`

Record monthly payments for multiple teachers at once. Prevents duplicate payments for the same month. Each payment is validated individually, and the response includes both successful and failed payments.

**Request Body:**
```json
{
  "payments": [
    {
      "teacher_id": "TCH-123456",
      "payment_month": "2025-01",
      "release_date": "2025-01-15T10:00:00",
      "total_amount": 50000.0,
      "payment_mode": "Online"
    },
    {
      "teacher_id": "TCH-789012",
      "payment_month": "2025-01",
      "release_date": "2025-01-15T10:00:00",
      "total_amount": 45000.0,
      "payment_mode": "Online"
    },
    {
      "teacher_id": "TCH-345678",
      "payment_month": "2025-01",
      "release_date": "2025-01-15T10:00:00",
      "total_amount": 55000.0,
      "payment_mode": "Online"
    }
  ]
}
```

**Payment Mode Options:**
- `"Online"`
- `"Cash in hand"`
- `"Account transfer"`

**Example Request:**
```bash
POST http://localhost:8000/teacher/bulk-payments/
Content-Type: application/json
Authorization: Bearer <your_token>

{
  "payments": [
    {
      "teacher_id": "TCH-123456",
      "payment_month": "2025-01",
      "release_date": "2025-01-15T10:00:00",
      "total_amount": 50000.0,
      "payment_mode": "Online"
    },
    {
      "teacher_id": "TCH-789012",
      "payment_month": "2025-01",
      "release_date": "2025-01-15T10:00:00",
      "total_amount": 45000.0,
      "payment_mode": "Online"
    }
  ]
}
```

**Success Response (201 Created):**
```json
{
  "success_count": 2,
  "failed_count": 1,
  "successful_payments": [
    {
      "id": 1,
      "payment_month": "2025-01",
      "total_amount": 50000.0,
      "payment_mode": "Online",
      "release_date": "2025-01-15T10:00:00",
      "created_at": "2025-01-15T10:05:23.123456"
    },
    {
      "id": 2,
      "payment_month": "2025-01",
      "total_amount": 45000.0,
      "payment_mode": "Online",
      "release_date": "2025-01-15T10:00:00",
      "created_at": "2025-01-15T10:05:23.123456"
    }
  ],
  "failed_payments": [
    {
      "teacher_id": "TCH-345678",
      "staff_id": null,
      "error": "Payment for month 2025-01 already exists. Each month can only be paid once."
    }
  ]
}
```

**Error Responses:**
- `400 Bad Request`: Invalid payment_month format or future month (per payment item)
- `403 Forbidden`: Only school users can make payments
- `404 Not Found`: School profile not found
- `500 Internal Server Error`: Database error

**Notes:**
- All successful payments are committed in a single database transaction
- Failed payments are tracked with detailed error messages
- Each payment is validated independently (teacher exists, payment structure exists, no duplicate payments, valid month format, not future month)
- Partial success is possible - some payments may succeed while others fail
- Each payment item can have different `payment_month`, `release_date`, and `payment_mode` values

---

### 3. Get Teacher Payment History
**GET** `/teacher/{teacher_id}/payments/`

Get all payment transactions for a teacher, ordered by payment month (newest first).

**Path Parameters:**
- `teacher_id` (string, required): Teacher ID (e.g., "TCH-123456")

**Example Request:**
```bash
GET http://localhost:8000/teacher/TCH-123456/payments/
Authorization: Bearer <your_token>
```

**Success Response (200 OK):**
```json
[
  {
    "id": 3,
    "payment_month": "2025-02",
    "total_amount": 52000.0,
    "payment_mode": "Account transfer",
    "release_date": "2025-02-15T10:00:00",
    "created_at": "2025-02-15T10:05:23.123456"
  },
  {
    "id": 1,
    "payment_month": "2025-01",
    "total_amount": 50000.0,
    "payment_mode": "Online",
    "release_date": "2025-01-15T10:00:00",
    "created_at": "2025-01-15T10:05:23.123456"
  }
]
```

**Error Responses:**
- `403 Forbidden`: Only school and staff users can view payment history
- `404 Not Found`: Teacher not found or doesn't belong to your school

---

### 4. Get Teacher Pending Payment Months
**GET** `/teacher/{teacher_id}/payments/pending-months/`

Get list of months that need payment, calculated from teacher's created_at date to current month.

**Path Parameters:**
- `teacher_id` (string, required): Teacher ID (e.g., "TCH-123456")

**Example Request:**
```bash
GET http://localhost:8000/teacher/TCH-123456/payments/pending-months/
Authorization: Bearer <your_token>
```

**Success Response (200 OK):**
```json
[
  {
    "month": "2025-03",
    "month_name": "March 2025",
    "is_paid": false,
    "payment_date": null
  },
  {
    "month": "2025-02",
    "month_name": "February 2025",
    "is_paid": true,
    "payment_date": "2025-02-15T10:00:00"
  },
  {
    "month": "2025-01",
    "month_name": "January 2025",
    "is_paid": true,
    "payment_date": "2025-01-15T10:00:00"
  }
]
```

**Error Responses:**
- `403 Forbidden`: Only school and staff users can view pending months
- `404 Not Found`: Teacher not found or doesn't belong to your school

---

## Staff Payment APIs

### 5. Make Payment to Staff
**POST** `/staff/{staff_id}/payments/`

Record a monthly payment for a staff member. Prevents duplicate payments for the same month.

**Path Parameters:**
- `staff_id` (string, required): Staff ID (e.g., "STF-123456")

**Request Body:**
```json
{
  "payment_month": "2025-01",
  "release_date": "2025-01-15T10:00:00",
  "total_amount": 45000.0,
  "payment_mode": "Cash in hand"
}
```

**Payment Mode Options:**
- `"Online"`
- `"Cash in hand"`
- `"Account transfer"`

**Example Request:**
```bash
POST http://localhost:8000/staff/STF-123456/payments/
Content-Type: application/json
Authorization: Bearer <your_token>

{
  "payment_month": "2025-01",
  "release_date": "2025-01-15T10:00:00",
  "total_amount": 45000.0,
  "payment_mode": "Cash in hand"
}
```

**Success Response (201 Created):**
```json
{
  "id": 1,
  "payment_month": "2025-01",
  "total_amount": 45000.0,
  "payment_mode": "Cash in hand",
  "release_date": "2025-01-15T10:00:00",
  "created_at": "2025-01-15T10:05:23.123456"
}
```

**Error Responses:**
- `400 Bad Request`: 
  - Payment for month already exists
  - Invalid payment_month format (must be YYYY-MM)
  - Cannot make payment for future months
  - Payment structure not found
- `403 Forbidden`: Only school users can make payments
- `404 Not Found`: 
  - Staff not found or doesn't belong to your school
  - School profile not found

---

### 6. Make Bulk Payments to Staff
**POST** `/staff/bulk-payments/`

Record monthly payments for multiple staff members at once. Prevents duplicate payments for the same month. Each payment is validated individually, and the response includes both successful and failed payments.

**Request Body:**
```json
{
  "payments": [
    {
      "staff_id": "STF-123456",
      "payment_month": "2025-01",
      "release_date": "2025-01-15T10:00:00",
      "total_amount": 45000.0,
      "payment_mode": "Cash in hand"
    },
    {
      "staff_id": "STF-789012",
      "payment_month": "2025-01",
      "release_date": "2025-01-15T10:00:00",
      "total_amount": 40000.0,
      "payment_mode": "Cash in hand"
    },
    {
      "staff_id": "STF-345678",
      "payment_month": "2025-01",
      "release_date": "2025-01-15T10:00:00",
      "total_amount": 42000.0,
      "payment_mode": "Cash in hand"
    }
  ]
}
```

**Payment Mode Options:**
- `"Online"`
- `"Cash in hand"`
- `"Account transfer"`

**Example Request:**
```bash
POST http://localhost:8000/staff/bulk-payments/
Content-Type: application/json
Authorization: Bearer <your_token>

{
  "payments": [
    {
      "staff_id": "STF-123456",
      "payment_month": "2025-01",
      "release_date": "2025-01-15T10:00:00",
      "total_amount": 45000.0,
      "payment_mode": "Cash in hand"
    },
    {
      "staff_id": "STF-789012",
      "payment_month": "2025-01",
      "release_date": "2025-01-15T10:00:00",
      "total_amount": 40000.0,
      "payment_mode": "Cash in hand"
    }
  ]
}
```

**Success Response (201 Created):**
```json
{
  "success_count": 2,
  "failed_count": 1,
  "successful_payments": [
    {
      "id": 1,
      "payment_month": "2025-01",
      "total_amount": 45000.0,
      "payment_mode": "Cash in hand",
      "release_date": "2025-01-15T10:00:00",
      "created_at": "2025-01-15T10:05:23.123456"
    },
    {
      "id": 2,
      "payment_month": "2025-01",
      "total_amount": 40000.0,
      "payment_mode": "Cash in hand",
      "release_date": "2025-01-15T10:00:00",
      "created_at": "2025-01-15T10:05:23.123456"
    }
  ],
  "failed_payments": [
    {
      "teacher_id": null,
      "staff_id": "STF-345678",
      "error": "Payment structure not found. Please set up payment structure for this staff member first."
    }
  ]
}
```

**Error Responses:**
- `400 Bad Request`: Invalid payment_month format or future month (per payment item)
- `403 Forbidden`: Only school users can make payments
- `404 Not Found`: School profile not found
- `500 Internal Server Error`: Database error

**Notes:**
- All successful payments are committed in a single database transaction
- Failed payments are tracked with detailed error messages
- Each payment is validated independently (staff exists, payment structure exists, no duplicate payments, valid month format, not future month)
- Partial success is possible - some payments may succeed while others fail
- Each payment item can have different `payment_month`, `release_date`, and `payment_mode` values

---

### 7. Get Staff Payment History
**GET** `/staff/{staff_id}/payments/`

Get all payment transactions for a staff member, ordered by payment month (newest first).

**Path Parameters:**
- `staff_id` (string, required): Staff ID (e.g., "STF-123456")

**Note:** Staff members can only view their own payment history.

**Example Request:**
```bash
GET http://localhost:8000/staff/STF-123456/payments/
Authorization: Bearer <your_token>
```

**Success Response (200 OK):**
```json
[
  {
    "id": 3,
    "payment_month": "2025-02",
    "total_amount": 47000.0,
    "payment_mode": "Account transfer",
    "release_date": "2025-02-15T10:00:00",
    "created_at": "2025-02-15T10:05:23.123456"
  },
  {
    "id": 1,
    "payment_month": "2025-01",
    "total_amount": 45000.0,
    "payment_mode": "Cash in hand",
    "release_date": "2025-01-15T10:00:00",
    "created_at": "2025-01-15T10:05:23.123456"
  }
]
```

**Error Responses:**
- `403 Forbidden`: Only school and staff users can view payment history (staff can only view their own)
- `404 Not Found`: Staff not found or doesn't belong to your school

---

### 8. Get Staff Pending Payment Months
**GET** `/staff/{staff_id}/payments/pending-months/`

Get list of months that need payment, calculated from staff's created_at date to current month.

**Path Parameters:**
- `staff_id` (string, required): Staff ID (e.g., "STF-123456")

**Note:** Staff members can only view their own pending months.

**Example Request:**
```bash
GET http://localhost:8000/staff/STF-123456/payments/pending-months/
Authorization: Bearer <your_token>
```

**Success Response (200 OK):**
```json
[
  {
    "month": "2025-03",
    "month_name": "March 2025",
    "is_paid": false,
    "payment_date": null
  },
  {
    "month": "2025-02",
    "month_name": "February 2025",
    "is_paid": true,
    "payment_date": "2025-02-15T10:00:00"
  },
  {
    "month": "2025-01",
    "month_name": "January 2025",
    "is_paid": true,
    "payment_date": "2025-01-15T10:00:00"
  }
]
```

**Error Responses:**
- `403 Forbidden`: Only school and staff users can view pending months (staff can only view their own)
- `404 Not Found`: Staff not found or doesn't belong to your school

---

## Important Notes

### Payment Month Format
- Must be in `YYYY-MM` format (e.g., "2025-01" for January 2025)
- Cannot be a future month (must be current month or past month)
- Each month can only be paid once per teacher/staff
- Validation is performed per payment item in bulk payments

### Payment Mode
- Must be one of: `"Online"`, `"Cash in hand"`, or `"Account transfer"`
- Case-sensitive

### Release Date
- ISO 8601 datetime format (e.g., "2025-01-15T10:00:00")
- Represents when the payment was actually released

### Permissions
- **Make Payment**: Only `SCHOOL` role users
- **View Payment History**: `SCHOOL` and `STAFF` role users
- **View Pending Months**: `SCHOOL` and `STAFF` role users
- Staff members can only view their own payment history and pending months

### Prerequisites
- Teacher/Staff must have a payment structure set up before making payments
- Payment structure is created when teacher/staff is created or updated
- If payment structure is missing, you'll receive a 400 error with details

### Validation Rules
- **Payment Month**: Must be in YYYY-MM format and cannot be a future month
- **Total Amount**: Must be >= 0
- **Duplicate Prevention**: Each teacher/staff can only receive one payment per month
- **Payment Structure**: Must exist before making any payments

---

## Example Workflows

### Single Payment Workflow

1. **Get Pending Months** to see which months need payment
   ```
   GET /teacher/{teacher_id}/payments/pending-months/
   ```

2. **Make Payment** for a specific month
   ```
   POST /teacher/{teacher_id}/payments/
   {
     "payment_month": "2025-01",
     "release_date": "2025-01-15T10:00:00",
     "total_amount": 50000.0,
     "payment_mode": "Online"
   }
   ```

3. **View Payment History** to see all payments made
   ```
   GET /teacher/{teacher_id}/payments/
   ```

### Bulk Payment Workflow

1. **Make Bulk Payments** to multiple teachers/staff at once
   ```
   POST /teacher/bulk-payments/
   {
     "payments": [
       {
         "teacher_id": "TCH-123456",
         "payment_month": "2025-01",
         "release_date": "2025-01-15T10:00:00",
         "total_amount": 50000.0,
         "payment_mode": "Online"
       },
       {
         "teacher_id": "TCH-789012",
         "payment_month": "2025-01",
         "release_date": "2025-01-15T10:00:00",
         "total_amount": 45000.0,
         "payment_mode": "Online"
       }
     ]
   }
   ```

2. **Check Response** for success/failure counts and details
   - Review `successful_payments` array for completed payments
   - Review `failed_payments` array for any errors
   - Each failed payment includes an error message explaining why it failed

---

## Error Scenarios

### Duplicate Payment
```json
{
  "detail": "Payment for month 2025-01 already exists. Each month can only be paid once."
}
```

### Future Month Payment
```json
{
  "detail": "Cannot make payment for future months."
}
```

### Missing Payment Structure
```json
{
  "detail": "Payment structure not found. Please set up payment structure for this teacher first."
}
```

### Invalid Payment Month Format
```json
{
  "detail": "Invalid payment_month format. Use YYYY-MM format (e.g., '2025-01')."
}
```

**Note:** The payment_month must be in YYYY-MM format (e.g., "2025-01" for January 2025). This validation applies to both single and bulk payment requests.

**Note:** The payment_month must be in YYYY-MM format (e.g., "2025-01" for January 2025). This validation applies to both single and bulk payment requests.

### Bulk Payment Partial Failure
When making bulk payments, some payments may succeed while others fail. The response will include both:
```json
{
  "success_count": 2,
  "failed_count": 1,
  "successful_payments": [...],
  "failed_payments": [
    {
      "teacher_id": "TCH-123456",
      "staff_id": null,
      "error": "Payment for month 2025-01 already exists. Each month can only be paid once."
    }
  ]
}
```

### Teacher/Staff Not Found in Bulk Payment
```json
{
  "teacher_id": "TCH-INVALID",
  "staff_id": null,
  "error": "Teacher not found or doesn't belong to your school"
}
```

