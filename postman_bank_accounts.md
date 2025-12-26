# Bank Account Management API - Postman Collection

Base URL: `http://your-server-url/school`

**Note:** All endpoints require authentication. Include your JWT token in the Authorization header:
```
Authorization: Bearer <your_jwt_token>
```

---

## 1. Create Bank Account (POST)

**Endpoint:** `POST /school/bank-accounts/`

**Headers:**
```
Content-Type: application/json
Authorization: Bearer <your_jwt_token>
```

**Request Body (JSON):**

### Example 1: Create Primary Bank Account
```json
{
  "account_holder_name": "ABC School",
  "account_number": "1234567890123456",
  "ifsc_code": "SBIN0001234",
  "bank_name": "State Bank of India",
  "branch_name": "Main Branch, Mumbai",
  "account_type": "savings",
  "is_primary": true
}
```

### Example 2: Create Secondary Bank Account
```json
{
  "account_holder_name": "ABC School",
  "account_number": "9876543210987654",
  "ifsc_code": "HDFC0005678",
  "bank_name": "HDFC Bank",
  "branch_name": "Andheri Branch",
  "account_type": "current",
  "is_primary": false
}
```

### Example 3: Minimal Required Fields
```json
{
  "account_holder_name": "XYZ School",
  "account_number": "5555555555555555",
  "ifsc_code": "ICIC0009999",
  "bank_name": "ICICI Bank",
  "account_type": "savings"
}
```

**Note:** 
- `branch_name` is optional
- `is_primary` defaults to `false` if not provided
- `ifsc_code` must be exactly 11 characters
- `account_type` must be either "savings" or "current"

**Expected Response (201 Created):**
```json
{
  "id": 1,
  "school_id": "SCH-123456",
  "account_holder_name": "ABC School",
  "account_number": "1234567890123456",
  "ifsc_code": "SBIN0001234",
  "bank_name": "State Bank of India",
  "branch_name": "Main Branch, Mumbai",
  "account_type": "savings",
  "is_primary": true,
  "created_at": "2026-01-15T10:30:00",
  "updated_at": "2026-01-15T10:30:00"
}
```

---

## 2. Get All Bank Accounts (GET)

**Endpoint:** `GET /school/bank-accounts/`

**Headers:**
```
Authorization: Bearer <your_jwt_token>
```

**Request Body:** None (No body required)

**Expected Response (200 OK):**
```json
[
  {
    "id": 1,
    "school_id": "SCH-123456",
    "account_holder_name": "ABC School",
    "account_number": "1234567890123456",
    "ifsc_code": "SBIN0001234",
    "bank_name": "State Bank of India",
    "branch_name": "Main Branch, Mumbai",
    "account_type": "savings",
    "is_primary": true,
    "created_at": "2026-01-15T10:30:00",
    "updated_at": "2026-01-15T10:30:00"
  },
  {
    "id": 2,
    "school_id": "SCH-123456",
    "account_holder_name": "ABC School",
    "account_number": "9876543210987654",
    "ifsc_code": "HDFC0005678",
    "bank_name": "HDFC Bank",
    "branch_name": "Andheri Branch",
    "account_type": "current",
    "is_primary": false,
    "created_at": "2026-01-15T11:00:00",
    "updated_at": "2026-01-15T11:00:00"
  }
]
```

**Note:** Results are ordered by `is_primary` (primary accounts first), then by `created_at` (newest first).

---

## 3. Get Specific Bank Account (GET)

**Endpoint:** `GET /school/bank-accounts/{account_id}/`

**Example:** `GET /school/bank-accounts/1/`

**Headers:**
```
Authorization: Bearer <your_jwt_token>
```

**Request Body:** None (No body required)

**Expected Response (200 OK):**
```json
{
  "id": 1,
  "school_id": "SCH-123456",
  "account_holder_name": "ABC School",
  "account_number": "1234567890123456",
  "ifsc_code": "SBIN0001234",
  "bank_name": "State Bank of India",
  "branch_name": "Main Branch, Mumbai",
  "account_type": "savings",
  "is_primary": true,
  "created_at": "2026-01-15T10:30:00",
  "updated_at": "2026-01-15T10:30:00"
}
```

---

## 4. Update Bank Account (PUT)

**Endpoint:** `PUT /school/bank-accounts/{account_id}/`

**Example:** `PUT /school/bank-accounts/1/`

**Headers:**
```
Content-Type: application/json
Authorization: Bearer <your_jwt_token>
```

**Request Body (JSON):**

### Example 1: Update All Fields
```json
{
  "account_holder_name": "ABC School Updated",
  "account_number": "1111222233334444",
  "ifsc_code": "SBIN0009999",
  "bank_name": "State Bank of India - Updated Branch",
  "branch_name": "New Branch, Delhi",
  "account_type": "current",
  "is_primary": true
}
```

### Example 2: Update Only Specific Fields (Partial Update)
```json
{
  "branch_name": "Updated Branch Name",
  "is_primary": false
}
```

### Example 3: Change Primary Account
```json
{
  "is_primary": true
}
```

**Note:** 
- All fields are optional in the update request
- Only provided fields will be updated
- If `is_primary` is set to `true`, all other accounts for the school will be set to `is_primary=false`

**Expected Response (200 OK):**
```json
{
  "id": 1,
  "school_id": "SCH-123456",
  "account_holder_name": "ABC School Updated",
  "account_number": "1111222233334444",
  "ifsc_code": "SBIN0009999",
  "bank_name": "State Bank of India - Updated Branch",
  "branch_name": "New Branch, Delhi",
  "account_type": "current",
  "is_primary": true,
  "created_at": "2026-01-15T10:30:00",
  "updated_at": "2026-01-15T12:45:00"
}
```

---

## 5. Delete Bank Account (DELETE)

**Endpoint:** `DELETE /school/bank-accounts/{account_id}/`

**Example:** `DELETE /school/bank-accounts/2/`

**Headers:**
```
Authorization: Bearer <your_jwt_token>
```

**Request Body:** None (No body required)

**Expected Response (204 No Content):**
- No response body, just status code 204

---

## Error Responses

### 400 Bad Request - Validation Error
```json
{
  "detail": [
    {
      "loc": ["body", "ifsc_code"],
      "msg": "ensure this value has at least 11 characters",
      "type": "value_error.any_str.min_length"
    }
  ]
}
```

### 403 Forbidden - Unauthorized Access
```json
{
  "detail": "Only school and staff users can manage bank accounts"
}
```

### 404 Not Found - Bank Account Not Found
```json
{
  "detail": "Bank account not found or you don't have access to it"
}
```

### 404 Not Found - School Not Found
```json
{
  "detail": "School not found"
}
```

---

## Testing Workflow

1. **Create Primary Account:**
   - Use Example 1 from "Create Bank Account" with `is_primary: true`
   - Note the `id` from the response

2. **Create Secondary Account:**
   - Use Example 2 from "Create Bank Account" with `is_primary: false`
   - Note the `id` from the response

3. **List All Accounts:**
   - Use "Get All Bank Accounts" endpoint
   - Verify primary account appears first

4. **Get Specific Account:**
   - Use "Get Specific Bank Account" with one of the account IDs

5. **Update Account:**
   - Use "Update Bank Account" to change the secondary account to primary
   - Verify the previous primary account is now `is_primary: false`

6. **Delete Account:**
   - Use "Delete Bank Account" to remove one account
   - Verify it's removed by listing all accounts again

---

## Quick Copy-Paste Examples

### Create Primary Account
```json
{"account_holder_name":"ABC School","account_number":"1234567890123456","ifsc_code":"SBIN0001234","bank_name":"State Bank of India","branch_name":"Main Branch","account_type":"savings","is_primary":true}
```

### Create Secondary Account
```json
{"account_holder_name":"ABC School","account_number":"9876543210987654","ifsc_code":"HDFC0005678","bank_name":"HDFC Bank","branch_name":"Andheri","account_type":"current","is_primary":false}
```

### Update to Primary
```json
{"is_primary":true}
```

### Update Branch Name
```json
{"branch_name":"New Branch Location"}
```

