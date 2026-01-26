# Tek School - Dual Signup & Account Promotion Postman Collection

## 📋 Overview

This Postman collection tests the dual signup system (Business & Listing) and account promotion features.

## 🚀 Setup Instructions

### 1. Import Collection
1. Open Postman
2. Click **Import** button
3. Select `Tek_School_Dual_Signup_Collection.postman_collection.json`
4. Collection will be imported with all requests organized in folders

### 2. Configure Environment Variables

The collection uses the following variables:
- `base_url` - Default: `http://localhost:8000` (change if your server runs on different port)
- `admin_token` - JWT token for admin user (get from admin login)
- `access_token_listing` - JWT token for listing school (auto-set after login)
- `access_token_business` - JWT token for business school (auto-set after login)

**To set variables:**
1. Click on the collection name
2. Go to **Variables** tab
3. Update `base_url` if needed
4. Set `admin_token` after logging in as admin

### 3. Auto-Set Variables

The collection automatically sets these variables:
- `user_id_business` - After business signup
- `user_id_listing` - After listing signup
- `school_email_business` - After business signup
- `school_email_listing` - After listing signup
- `access_token_listing` - After listing school login
- `access_token_business` - After business school login
- `pending_school_id` - After fetching pending business signups
- `promotion_school_id` - After fetching pending promotions

## 📁 Collection Structure

### 1. School Signup

#### Business School Signup
**POST** `{{base_url}}/users/`

Creates business account (requires admin approval before login).

**Request Body:**
```json
{
  "email": "business.school@example.com",
  "phone": "9876543210",
  "name": "ABC Business School",
  "location": "Mumbai",
  "website": "https://abcbusinessschool.com",
  "signup_type": "business_school_signup"
}
```

**Response (200 OK):**
```json
{
  "detail": "OTP sent to your email. Please verify to complete signup.",
  "user_id": 123
}
```

---

#### Listing School Signup
**POST** `{{base_url}}/users/`

Creates listing account (can login immediately after OTP verification).

**Request Body:**
```json
{
  "email": "listing.school@example.com",
  "phone": "9876543211",
  "name": "XYZ Listing School",
  "location": "Delhi",
  "website": "https://xyzlistschool.com",
  "signup_type": "listing_school_signup"
}
```

**Response (200 OK):**
```json
{
  "detail": "OTP sent to your email. Please verify to complete signup.",
  "user_id": 124
}
```

---

### 2. OTP Verification

#### Verify OTP - Business School
**POST** `{{base_url}}/users/verify-otp`

Verify OTP for business account. Credentials will be sent to email.

**Request Body:**
```json
{
  "email": "business.school@example.com",
  "otp": "123456"
}
```

**Response (200 OK):**
```json
{
  "detail": "OTP verified successfully. Credentials sent to your email."
}
```

---

#### Verify OTP - Listing School
**POST** `{{base_url}}/users/verify-otp`

Verify OTP for listing account. Credentials will be sent to email.

**Request Body:**
```json
{
  "email": "listing.school@example.com",
  "otp": "123456"
}
```

**Response (200 OK):**
```json
{
  "detail": "OTP verified successfully. Credentials sent to your email."
}
```

---

#### Resend OTP
**POST** `{{base_url}}/users/resend-otp`

Resend OTP to email.

**Request Body:**
```json
{
  "email": "business.school@example.com"
}
```

**Response (200 OK):**
```json
{
  "detail": "A new OTP has been sent to your email."
}
```

---

### 3. Login

#### Login - Business School (Business Type)
**POST** `{{base_url}}/auth/login/`

Login with business school as business type. Requires admin approval.

**Request Body:**
```json
{
  "email": "business.school@example.com",
  "password": "your_password_here",
  "login_type": "business"
}
```

**Response (200 OK):**
```json
{
  "detail": "Login successful",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "role": "school",
  "id": 123
}
```

**Response (403 Forbidden) - Not verified by admin:**
```json
{
  "detail": "Your account is not verified yet by admin."
}
```

**Response (403 Forbidden) - OTP not verified:**
```json
{
  "detail": "Please verify your account with OTP first."
}
```

---

#### Login - Business School (Listing Type)
**POST** `{{base_url}}/auth/login/`

Login with business school as listing type. Can login immediately after OTP verification (no admin approval needed).

**Request Body:**
```json
{
  "email": "business.school@example.com",
  "password": "your_password_here",
  "login_type": "listing"
}
```

**Response (200 OK):**
```json
{
  "detail": "Login successful",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "role": "school",
  "id": 123
}
```

**Note:** Business accounts can login with `login_type: "listing"` immediately after OTP verification to use listing features. They need admin approval for business features (`login_type: "business"`).

---

#### Login - Listing School
**POST** `{{base_url}}/auth/login/`

Login with listing school. Should succeed immediately after OTP verification.

**Request Body:**
```json
{
  "email": "listing.school@example.com",
  "password": "your_password_here",
  "login_type": "listing"
}
```

**Note:** For listing schools, `login_type` should be "listing". Default is "business" if not provided.

**Response (200 OK):**
```json
{
  "detail": "Login successful",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "role": "school",
  "id": 124
}
```

---


---

### 4. School Profile

#### Get School Profile
**GET** `{{base_url}}/school/school`

View school profile with account type info. Requires authentication.

**Headers:**
```
Authorization: Bearer {{access_token_listing}}
```

**Response (200 OK):**
```json
{
  "id": "SCH-123456",
  "user_id": 124,
  "school_name": "XYZ Listing School",
  "school_type": "private",
  "school_medium": "english",
  "school_board": "cbse",
  "school_logo": "https://s3...",
  "school_banner": "https://s3...",
  "establishment_year": 2000,
  "pin_code": "400001",
  "block_division": "Mumbai",
  "district": "Mumbai",
  "state": "Maharashtra",
  "country": "India",
  "school_email": "listing.school@example.com",
  "school_phone": "9876543211",
  "school_alt_phone": null,
  "school_website": "https://xyzlistschool.com",
  "principal_name": null,
  "principal_designation": null,
  "principal_email": null,
  "principal_phone": null,
  "account_type": "listing",
  "is_business_approved": false,
  "is_promotion_pending": false,
  "created_at": "2025-01-15T10:00:00"
}
```

---

#### Update School Profile
**PATCH** `{{base_url}}/school/school-profile`

Update school information. Requires authentication.

**Headers:**
```
Authorization: Bearer {{access_token_listing}}
Content-Type: multipart/form-data
```

**Request Body (Form Data):**
```
school_name: Updated School Name
school_type: private
school_medium: english
school_board: cbse
establishment_year: 2000
district: Mumbai
state: Maharashtra
pin_code: 400001
principal_name: John Doe
principal_email: principal@example.com
principal_phone: 9876543210
profile_pic: [file] (optional)
banner_pic: [file] (optional)
```

**Response (200 OK):**
```json
{
  "detail": "School profile updated successfully"
}
```

---

### 5. Catalogue Management

#### Add Images to Catalogue
**POST** `{{base_url}}/school/catalogue`

Upload multiple images to school catalogue. Images are automatically uploaded to S3.

**Headers:**
```
Authorization: Bearer {{access_token_business}}
Content-Type: multipart/form-data
```

**Request Body (Form Data):**
- `images` (file, multiple): Image files to upload (max 20 per request)
  - Allowed formats: jpg, jpeg, png, gif
  - Max file size: 5MB per image

**Example:**
```
POST {{base_url}}/school/catalogue
Content-Type: multipart/form-data
Authorization: Bearer {{access_token_business}}

Form-data:
- images: [file1.jpg]
- images: [file2.jpg]
- images: [file3.jpg]
```

**Response (201 Created):**
```json
{
  "detail": "Successfully added 3 image(s) to catalogue",
  "uploaded_urls": [
    "https://bucket.s3.region.amazonaws.com/schools/989/catalogue/uuid1.jpg",
    "https://bucket.s3.region.amazonaws.com/schools/989/catalogue/uuid2.jpg",
    "https://bucket.s3.region.amazonaws.com/schools/989/catalogue/uuid3.jpg"
  ],
  "errors": null,
  "total_catalogue_images": 3
}
```

---

#### Get Catalogue Images (with Pagination)
**GET** `{{base_url}}/school/catalogue?page=1&page_size=20`

Get catalogue images with pagination support.

**Headers:**
```
Authorization: Bearer {{access_token_business}}
```

**Query Parameters:**
- `page` (optional, default: 1): Page number (starts from 1)
- `page_size` (optional, default: 20, max: 100): Number of images per page

**Example:**
```
GET {{base_url}}/school/catalogue?page=1&page_size=20
Authorization: Bearer {{access_token_business}}
```

**Response (200 OK):**
```json
{
  "catalogue": [
    "https://bucket.s3.region.amazonaws.com/schools/989/catalogue/uuid1.jpg",
    "https://bucket.s3.region.amazonaws.com/schools/989/catalogue/uuid2.jpg"
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_images": 45,
    "total_pages": 3,
    "has_next": true,
    "has_previous": false
  }
}
```

---

#### Remove Specific Catalogue Image
**DELETE** `{{base_url}}/school/catalogue/image?image_url=<URL>`

Remove a specific image from catalogue by URL.

**Headers:**
```
Authorization: Bearer {{access_token_business}}
```

**Query Parameters:**
- `image_url` (required): Full URL of the image to remove

**Example:**
```
DELETE {{base_url}}/school/catalogue/image?image_url=https://bucket.s3.region.amazonaws.com/schools/989/catalogue/uuid1.jpg
Authorization: Bearer {{access_token_business}}
```

**Response (200 OK):**
```json
{
  "detail": "Image removed from catalogue successfully",
  "removed_url": "https://bucket.s3.region.amazonaws.com/schools/989/catalogue/uuid1.jpg",
  "remaining_images": 2
}
```

---

#### Clear All Catalogue Images
**DELETE** `{{base_url}}/school/catalogue`

Remove all images from catalogue.

**Headers:**
```
Authorization: Bearer {{access_token_business}}
```

**Example:**
```
DELETE {{base_url}}/school/catalogue
Authorization: Bearer {{access_token_business}}
```

**Response (200 OK):**
```json
{
  "detail": "Catalogue cleared successfully",
  "catalogue": null
}
```

---

### 6. Photo Gallery Management

#### Add Images to Photo Gallery
**POST** `{{base_url}}/school/photo-gallery`

Upload multiple images to school photo gallery. Images are automatically uploaded to S3.

**Headers:**
```
Authorization: Bearer {{access_token_business}}
Content-Type: multipart/form-data
```

**Request Body (Form Data):**
- `images` (file, multiple): Image files to upload (max 50 per request)
  - Allowed formats: jpg, jpeg, png, gif
  - Max file size: 5MB per image

**Example:**
```
POST {{base_url}}/school/photo-gallery
Content-Type: multipart/form-data
Authorization: Bearer {{access_token_business}}

Form-data:
- images: [photo1.jpg]
- images: [photo2.jpg]
- images: [photo3.jpg]
```

**Response (201 Created):**
```json
{
  "detail": "Successfully added 3 image(s) to photo gallery",
  "uploaded_urls": [
    "https://bucket.s3.region.amazonaws.com/schools/989/photo_gallery/uuid1.jpg",
    "https://bucket.s3.region.amazonaws.com/schools/989/photo_gallery/uuid2.jpg",
    "https://bucket.s3.region.amazonaws.com/schools/989/photo_gallery/uuid3.jpg"
  ],
  "errors": null,
  "total_gallery_images": 3
}
```

---

#### Get Photo Gallery Images (with Pagination)
**GET** `{{base_url}}/school/photo-gallery?page=1&page_size=20`

Get photo gallery images with pagination support.

**Headers:**
```
Authorization: Bearer {{access_token_business}}
```

**Query Parameters:**
- `page` (optional, default: 1): Page number (starts from 1)
- `page_size` (optional, default: 20, max: 100): Number of images per page

**Example:**
```
GET {{base_url}}/school/photo-gallery?page=1&page_size=20
Authorization: Bearer {{access_token_business}}
```

**Response (200 OK):**
```json
{
  "photo_gallery": [
    "https://bucket.s3.region.amazonaws.com/schools/989/photo_gallery/uuid1.jpg",
    "https://bucket.s3.region.amazonaws.com/schools/989/photo_gallery/uuid2.jpg"
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_images": 100,
    "total_pages": 5,
    "has_next": true,
    "has_previous": false
  }
}
```

---

#### Remove Specific Photo Gallery Image
**DELETE** `{{base_url}}/school/photo-gallery/image?image_url=<URL>`

Remove a specific image from photo gallery by URL.

**Headers:**
```
Authorization: Bearer {{access_token_business}}
```

**Query Parameters:**
- `image_url` (required): Full URL of the image to remove

**Example:**
```
DELETE {{base_url}}/school/photo-gallery/image?image_url=https://bucket.s3.region.amazonaws.com/schools/989/photo_gallery/uuid1.jpg
Authorization: Bearer {{access_token_business}}
```

**Response (200 OK):**
```json
{
  "detail": "Image removed from photo gallery successfully",
  "removed_url": "https://bucket.s3.region.amazonaws.com/schools/989/photo_gallery/uuid1.jpg",
  "remaining_images": 2
}
```

---

#### Clear All Photo Gallery Images
**DELETE** `{{base_url}}/school/photo-gallery`

Remove all images from photo gallery.

**Headers:**
```
Authorization: Bearer {{access_token_business}}
```

**Example:**
```
DELETE {{base_url}}/school/photo-gallery
Authorization: Bearer {{access_token_business}}
```

**Response (200 OK):**
```json
{
  "detail": "Photo gallery cleared successfully",
  "photo_gallery": null
}
```

---

### 7. Account Promotion

#### Request Account Promotion
**POST** `{{base_url}}/school/promote-account`

Listing school requests promotion to business account. Sets `is_promotion_pending = True`.

**Headers:**
```
Authorization: Bearer {{access_token_listing}}
Content-Type: application/json
```

**Request Body:**
```json
{}
```

**Response (200 OK):**
```json
{
  "detail": "Promotion request sent to admin. You will be notified once approved.",
  "status": "pending"
}
```

**Error Response (400 Bad Request):**
```json
{
  "detail": "Account is already a business account"
}
```
or
```json
{
  "detail": "Promotion request already pending. Please wait for admin approval."
}
```

---

#### Check Promotion Status
**GET** `{{base_url}}/school/school`

View promotion status in school profile. Check `is_promotion_pending` field.

**Headers:**
```
Authorization: Bearer {{access_token_listing}}
```

**Response:** Same as Get School Profile, check `is_promotion_pending` field.

---

### 6. Admin - Pending Approvals (Combined)

#### Get Pending Approvals (Unified)
**GET** `{{base_url}}/admin/schools/pending-approvals/`

Get all pending school approvals (business signups and promotions) in one endpoint with advanced filtering. Requires admin role.

**Headers:**
```
Authorization: Bearer {{admin_token}}
```

**Query Parameters:**
- `page` (optional): Page number (default: 1)
- `per_page` (optional): Items per page (default: 10)
- `request_type` (optional): Filter by request type - `"business_signup"` or `"promotion"`. Leave empty for all.
- `school_name` (optional): Filter by school name (case-insensitive search)
- `school_email` (optional): Filter by school email
- `account_type` (optional): Filter by account type - `"business"` or `"listing"`
- `from_date` (optional): Filter by created date from (format: `YYYY-MM-DD`)
- `to_date` (optional): Filter by created date to (format: `YYYY-MM-DD`)

**Example Requests:**
```
# Get all pending approvals
GET {{base_url}}/admin/schools/pending-approvals/?page=1&per_page=10

# Get only business signups
GET {{base_url}}/admin/schools/pending-approvals/?request_type=business_signup

# Get only promotions
GET {{base_url}}/admin/schools/pending-approvals/?request_type=promotion

# Filter by school name
GET {{base_url}}/admin/schools/pending-approvals/?school_name=ABC

# Filter by date range
GET {{base_url}}/admin/schools/pending-approvals/?from_date=2026-01-01&to_date=2026-01-31

# Combine filters
GET {{base_url}}/admin/schools/pending-approvals/?request_type=business_signup&school_name=ABC&from_date=2026-01-01
```

**Response (200 OK):**
```json
{
  "items": [
    {
      "school_id": "SCH-132126",
      "school_name": "ABC Business School",
      "school_email": "business.school@mailinator.com",
      "school_phone": "9876543210",
      "school_website": "https://abcbusinessschool.com",
      "account_type": "business",
      "request_type": "business_signup",
      "is_business_approved": false,
      "is_promotion_pending": false,
      "created_at": "2026-01-26T12:07:38.110702",
      "user_id": 989,
      "user_name": "School Admin",
      "user_email": "admin@school.com"
    },
    {
      "school_id": "SCH-789012",
      "school_name": "XYZ Listing School",
      "school_email": "listing.school@example.com",
      "school_phone": "9876543211",
      "school_website": "https://xyzlistschool.com",
      "account_type": "listing",
      "request_type": "promotion",
      "is_business_approved": false,
      "is_promotion_pending": true,
      "created_at": "2025-01-15T10:00:00",
      "user_id": 124,
      "user_name": "XYZ Listing School",
      "user_email": "listing.school@example.com"
    }
  ],
  "total": 2,
  "page": 1,
  "per_page": 10,
  "pages": 1
}
```

---

#### Approve School Request (Unified)
**PUT** `{{base_url}}/admin/schools/{school_id}/approve/`

Unified approval endpoint that automatically detects and approves both business signups and promotions. Requires admin role.

**Headers:**
```
Authorization: Bearer {{admin_token}}
```

**Path Parameters:**
- `school_id` (required): School ID (e.g., "SCH-132126")

**Description:**
- Automatically detects request type (business_signup or promotion)
- For business signups: Sets `is_business_approved = True`
- For promotions: Upgrades `account_type` to BUSINESS and sets `is_business_approved = True`

**Response (200 OK) - Business Signup:**
```json
{
  "detail": "Business school approved successfully. School can now login.",
  "request_type": "business_signup",
  "school_id": "SCH-132126",
  "school_name": "ABC Business School",
  "account_type": "business",
  "is_business_approved": true
}
```

**Response (200 OK) - Promotion:**
```json
{
  "detail": "Promotion approved. Account upgraded to business (has both listing and business access).",
  "request_type": "promotion",
  "school_id": "SCH-789012",
  "school_name": "XYZ Listing School",
  "account_type": "business",
  "is_business_approved": true
}
```

**Error Responses:**
- `400 Bad Request`: "School is already approved" or "No pending approval request found for this school"
- `403 Forbidden`: "Only admin account is allowed to approve school requests."
- `404 Not Found`: "School not found."

---

### 7. Admin - Business Signup Approvals (Legacy)

#### Get Pending Business Signups
**GET** `{{base_url}}/admin/schools/pending-business-signups/?page=1&per_page=10`

List all schools with business signup waiting for admin approval. Requires admin role.

**Headers:**
```
Authorization: Bearer {{admin_token}}
```

**Query Parameters:**
- `page` (optional): Page number (default: 1)
- `per_page` (optional): Items per page (default: 10)

**Response (200 OK):**
```json
{
  "items": [
    {
      "school_id": "SCH-123456",
      "school_name": "ABC Business School",
      "school_email": "business.school@example.com",
      "school_phone": "9876543210",
      "school_website": "https://abcbusinessschool.com",
      "account_type": "business",
      "created_at": "2025-01-15T10:00:00",
      "user_name": "ABC Business School",
      "user_email": "business.school@example.com"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 10,
  "pages": 1
}
```

---

#### Approve Business Signup (Legacy - Use Unified Endpoint)
**PUT** `{{base_url}}/admin/schools/{school_id}/approve-business/`

**⚠️ DEPRECATED:** Use `/admin/schools/{school_id}/approve/` instead.

Approve business school signup. School can now login. Requires admin role.

**Headers:**
```
Authorization: Bearer {{admin_token}}
```

**Path Parameters:**
- `school_id` (required): School ID (e.g., "SCH-123456")

**Response (200 OK):**
```json
{
  "detail": "Business school approved successfully. School can now login."
}
```

**Error Responses:**
- `400 Bad Request`: "This school is not a business signup" or "School is already approved"
- `404 Not Found`: "School not found."

---

### 7. Admin - Promotion Approvals

#### Get Pending Promotions (Legacy - Use Combined Endpoint)
**GET** `{{base_url}}/admin/schools/pending-promotions/?page=1&per_page=10`

**⚠️ DEPRECATED:** Use `/admin/schools/pending-approvals/?request_type=promotion` instead.

List all listing schools requesting promotion to business account. Requires admin role.

**Headers:**
```
Authorization: Bearer {{admin_token}}
```

**Query Parameters:**
- `page` (optional): Page number (default: 1)
- `per_page` (optional): Items per page (default: 10)

**Response (200 OK):**
```json
{
  "items": [
    {
      "school_id": "SCH-789012",
      "school_name": "XYZ Listing School",
      "school_email": "listing.school@example.com",
      "school_phone": "9876543211",
      "school_website": "https://xyzlistschool.com",
      "account_type": "listing",
      "created_at": "2025-01-15T11:00:00",
      "user_name": "XYZ Listing School",
      "user_email": "listing.school@example.com"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 10,
  "pages": 1
}
```

---

#### Approve Promotion (Legacy - Use Unified Endpoint)
**PUT** `{{base_url}}/admin/schools/{school_id}/approve-promotion/`

**⚠️ DEPRECATED:** Use `/admin/schools/{school_id}/approve/` instead.

Approve promotion request. Changes `account_type` to `BUSINESS` (which has both listing + business permissions). Requires admin role.

**Headers:**
```
Authorization: Bearer {{admin_token}}
```

**Path Parameters:**
- `school_id` (required): School ID (e.g., "SCH-789012")

**Response (200 OK):**
```json
{
  "detail": "Promotion approved. Account upgraded to business (has both listing and business access)."
}
```

**Error Responses:**
- `400 Bad Request`: "This school is not a listing account" or "No promotion request pending for this school"
- `404 Not Found`: "School not found."

---

### 8. Admin - All Schools

#### Get All Schools
**GET** `{{base_url}}/admin/all-school/?page=1&per_page=10&school_name=&status=&start_date=&end_date=`

View all schools with filters. Requires admin role.

**Headers:**
```
Authorization: Bearer {{admin_token}}
```

**Query Parameters:**
- `page` (optional): Page number (default: 1)
- `per_page` (optional): Items per page (default: 10)
- `school_name` (optional): Filter by school name
- `school_id` (optional): Filter by school ID
- `status` (optional): Filter by active status (true/false)
- `start_date` (optional): Filter by creation date (start)
- `end_date` (optional): Filter by creation date (end)

**Response (200 OK):**
```json
{
  "items": [
    {
      "school_id": "SCH-123456",
      "school_name": "ABC Business School",
      "school_email": "business.school@example.com",
      "account_type": "business",
      "is_active": true,
      "is_verified": true,
      "created_at": "2025-01-15T10:00:00",
      "teacher_count": 10,
      "student_count": 200
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 10,
  "pages": 1
}
```

---

#### Get School Details
**GET** `{{base_url}}/admin/school/{school_id}/`

Get detailed information about a specific school. Requires admin role.

**Headers:**
```
Authorization: Bearer {{admin_token}}
```

**Path Parameters:**
- `school_id` (required): School ID (e.g., "SCH-123456")

**Response (200 OK):**
```json
{
  "school_id": "SCH-123456",
  "school_name": "ABC Business School",
  "profile_image": "https://s3...",
  "school_email": "business.school@example.com",
  "school_phone": "9876543210",
  "account_type": "business",
  "is_active": true,
  "is_verified": true,
  "available_credit": 100,
  "earned_credit": 0,
  "teacher_count": 10,
  "student_count": 200,
  "created_at": "2025-01-15T10:00:00"
}
```

## 🧪 Testing Flow

### Test Business School Signup Flow:
1. **Business School Signup** → Creates account
2. **Verify OTP - Business School** → Enter OTP from email
3. **Login - Business School (Listing Type)** → Can login immediately ✅ (use `login_type: "listing"`)
4. **Login - Business School (Business Type)** → Should fail ❌ (use `login_type: "business"`, shows "not verified yet by admin")
5. **Get Pending Approvals** (as admin) → See the new signup (use `request_type=business_signup` or leave empty for all)
6. **Approve School Request** (as admin) → Approve the school using unified endpoint
7. **Login - Business School (Business Type)** → Now can login ✅ (use `login_type: "business"`)

### Test Listing School Signup Flow:
1. **Listing School Signup** → Creates account
2. **Verify OTP - Listing School** → Enter OTP from email
3. **Login - Listing School** → Should succeed immediately ✅
4. **Get School Profile** → Check account_type = "listing"

### Test Promotion Flow:
1. **Login - Listing School** → Login as listing school
2. **Request Account Promotion** → Request promotion to business
3. **Get Pending Approvals** (as admin) → See the promotion request (use `request_type=promotion` or leave empty for all)
4. **Approve School Request** (as admin) → Approve the promotion using unified endpoint
5. **Get School Profile** → Check account_type = "business" (has both listing + business permissions)

## 📝 Important Notes

### Signup Types:
- `business_school_signup` - Requires admin approval before login
- `listing_school_signup` - Can login immediately after OTP

### Account Types:
- `listing` - Only listing account (limited permissions, can login immediately)
- `business` - Business account (has both listing + business permissions)
  - Can login immediately for listing features (no approval needed)
  - Requires admin approval for business features
  - After approval: Full access to both listing and business features

### Authentication:
- Most endpoints require JWT token in Authorization header
- Format: `Authorization: Bearer <token>`
- Tokens are auto-saved after login requests

### Login Type (for School users):
- `login_type` field in login request body (optional, default: "business")
- Options: `"listing"` or `"business"`
- **Business accounts:**
  - `login_type: "listing"` → Can login immediately after OTP (no admin approval needed)
  - `login_type: "business"` → Requires admin approval, shows error if not verified
- **Listing accounts:**
  - `login_type: "listing"` → Can login immediately after OTP
  - `login_type: "business"` → Will show "not verified yet by admin" error

### OTP:
- OTP is sent to email after signup
- Check your email inbox for the OTP code
- OTP expires after a certain time (check code for exact duration)

### Admin Endpoints:
- All admin endpoints require admin role
- Make sure to set `admin_token` variable after logging in as admin

## 🔧 Customization

### Change Base URL:
1. Click collection → Variables tab
2. Update `base_url` value
3. Or create a Postman Environment with different URLs

### Add More Tests:
- Duplicate existing requests
- Modify request body/headers
- Add test scripts in "Tests" tab

## 📊 Quick Reference - All Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/users/` | School signup (business/listing) | No |
| POST | `/users/verify-otp` | Verify OTP | No |
| POST | `/users/resend-otp` | Resend OTP | No |
| POST | `/auth/login/` | Login | No |
| GET | `/school/school` | Get school profile | Yes |
| PATCH | `/school/school-profile` | Update school profile | Yes |
| POST | `/school/catalogue` | Add images to catalogue | Yes |
| GET | `/school/catalogue` | Get catalogue images (paginated) | Yes |
| DELETE | `/school/catalogue/image` | Remove specific catalogue image | Yes |
| DELETE | `/school/catalogue` | Clear all catalogue images | Yes |
| POST | `/school/photo-gallery` | Add images to photo gallery | Yes |
| GET | `/school/photo-gallery` | Get photo gallery images (paginated) | Yes |
| DELETE | `/school/photo-gallery/image` | Remove specific photo gallery image | Yes |
| DELETE | `/school/photo-gallery` | Clear all photo gallery images | Yes |
| POST | `/school/promote-account` | Request account promotion | Yes |
| GET | `/admin/schools/pending-approvals/` | Get all pending approvals (unified) | Admin |
| PUT | `/admin/schools/{school_id}/approve/` | Approve school request (unified) | Admin |
| GET | `/admin/schools/pending-business-signups/` | Get pending business signups (legacy) | Admin |
| PUT | `/admin/schools/{school_id}/approve-business/` | Approve business signup (legacy) | Admin |
| GET | `/admin/schools/pending-promotions/` | Get pending promotions (legacy) | Admin |
| PUT | `/admin/schools/{school_id}/approve-promotion/` | Approve promotion (legacy) | Admin |
| GET | `/admin/all-school/` | Get all schools | Admin |
| GET | `/admin/school/{school_id}/` | Get school details | Admin |

---

## 📊 Expected Responses Summary

### Business Signup Response (200 OK):
```json
{
  "detail": "OTP sent to your email. Please verify to complete signup.",
  "user_id": 123
}
```

### Listing Signup Response (200 OK):
```json
{
  "detail": "OTP sent to your email. Please verify to complete signup.",
  "user_id": 124
}
```

### OTP Verification Response (200 OK):
```json
{
  "detail": "OTP verified successfully. Credentials sent to your email."
}
```

### Login Success Response (200 OK):
```json
{
  "detail": "Login successful",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "role": "school",
  "id": 123
}
```

### Login Request Body (for School users):
```json
{
  "email": "school@example.com",
  "password": "your_password",
  "login_type": "business"  // or "listing", default is "business"
}
```

### Login Error Responses:

**Not verified by admin (403 Forbidden):**
```json
{
  "detail": "Your account is not verified yet by admin."
}
```

**OTP not verified (403 Forbidden):**
```json
{
  "detail": "Please verify your account with OTP first."
}
```

**Invalid login_type (400 Bad Request):**
```json
{
  "detail": "login_type must be either 'listing' or 'business'"
}
```

### School Profile Response (200 OK):
```json
{
  "id": "SCH-123456",
  "user_id": 124,
  "school_name": "XYZ Listing School",
  "account_type": "listing",
  "is_business_approved": false,
  "is_promotion_pending": false,
  "school_email": "listing.school@example.com",
  "school_phone": "9876543211",
  "created_at": "2025-01-15T10:00:00"
}
```

### Promotion Request Response (200 OK):
```json
{
  "detail": "Promotion request sent to admin. You will be notified once approved.",
  "status": "pending"
}
```

### Promotion Request Error (400 Bad Request):
```json
{
  "detail": "Account is already a business account"
}
```
or
```json
{
  "detail": "Promotion request already pending. Please wait for admin approval."
}
```

### Approve School Request Response (200 OK) - Unified Endpoint:

**For Business Signup:**
```json
{
  "detail": "Business school approved successfully. School can now login.",
  "request_type": "business_signup",
  "school_id": "SCH-132126",
  "school_name": "ABC Business School",
  "account_type": "business",
  "is_business_approved": true
}
```

**For Promotion:**
```json
{
  "detail": "Promotion approved. Account upgraded to business (has both listing and business access).",
  "request_type": "promotion",
  "school_id": "SCH-789012",
  "school_name": "XYZ Listing School",
  "account_type": "business",
  "is_business_approved": true
}
```

### Approve Business Signup Response (200 OK) - Legacy:
```json
{
  "detail": "Business school approved successfully. School can now login."
}
```

### Approve Promotion Response (200 OK) - Legacy:
```json
{
  "detail": "Promotion approved. Account upgraded to business (has both listing and business access)."
}
```

### Pending Approvals Response (200 OK) - Unified Endpoint:

```json
{
  "items": [
    {
      "school_id": "SCH-132126",
      "school_name": "ABC Business School",
      "school_email": "business.school@mailinator.com",
      "school_phone": "9876543210",
      "school_website": "https://abcbusinessschool.com",
      "account_type": "business",
      "request_type": "business_signup",
      "is_business_approved": false,
      "is_promotion_pending": false,
      "created_at": "2026-01-26T12:07:38.110702",
      "user_id": 989,
      "user_name": "School Admin",
      "user_email": "admin@school.com"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 10,
  "pages": 1
}
```

### Pending Business Signups Response (200 OK) - Legacy:
```json
{
  "items": [
    {
      "school_id": "SCH-123456",
      "school_name": "ABC Business School",
      "school_email": "business.school@example.com",
      "account_type": "business",
      "created_at": "2025-01-15T10:00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 10,
  "pages": 1
}
```

### Pending Promotions Response (200 OK) - Legacy:
```json
{
  "items": [
    {
      "school_id": "SCH-789012",
      "school_name": "XYZ Listing School",
      "school_email": "listing.school@example.com",
      "account_type": "listing",
      "created_at": "2025-01-15T11:00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 10,
  "pages": 1
}
```

## 🐛 Troubleshooting

### 401 Unauthorized:
- Check if token is set correctly
- Token might be expired, login again

### 403 Forbidden:
- Check user role (admin endpoints need admin role)
- Business school trying to login before approval (expected)

### 404 Not Found:
- Check if school_id is correct
- Check if base_url is correct

### 400 Bad Request:
- Check request body format
- Check if required fields are provided
- Check if OTP is correct/not expired

## 📚 Additional Resources

- Check server logs for detailed error messages
- Verify database for account_type values
- Check email for OTP codes

---

**Happy Testing! 🚀**
