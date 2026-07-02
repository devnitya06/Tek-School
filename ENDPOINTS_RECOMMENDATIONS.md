# Assignment API Endpoints - Recommendations

## Current Endpoints vs. Recommended

### 1. User's Assignment Summary
**Current:** `GET /assignments/my-assignments`
**Recommended:** `GET /me/assignments`
**Reason:** 
- More RESTful and aligned with standard `/me` convention (used by GitHub, Stripe, etc.)
- Clearer intent - user's personal assignments
- Shorter, more concise

**Response:** Board → Class → Subjects summary with counts
```json
{
  "data": [
    {
      "board_name": "cbse",
      "class_name": "standard-2",
      "subjects": [
        {
          "subject_name": "Eng",
          "total_assignments": 1,
          "created_by_me": 1
        }
      ]
    }
  ]
}
```

---

### 2. Browse Assignments by Subject
**Current:** `GET /assignments/subjects?board_name=X&class_name=Y&subject_name=Z`
**Recommended Option A:** `GET /assignments/catalog?board=X&class=Y&subject=Z`
**Recommended Option B:** `GET /assignments/search?board=X&class=Y&subject=Z`
**Recommended Option C:** `GET /catalog/board/{board}/class/{class}/subject/{subject}`
**Reason:**
- `/catalog` or `/search` clarifies this is browsing/discovering assignments
- Shorter param names (board vs board_name)
- Path params make hierarchy explicit

**Response:** List of detailed assignments with counts (participants, doubts, made_ideal)

---

### 3. General Assignment Listing
**Current:** `GET /assignments?board=X&medium=Y&class_id=Z&subject=W&skip=0&limit=20`
**Recommended:** `GET /assignments` (keep as-is)
**Reason:**
- Standard REST convention for "list all with filters"
- Already supports pagination and role-based filtering
- Good naming

---

### 4. Additional Improvements

#### a) Standardize Parameter Names
- Use shorter, consistent names across endpoints:
  - `board_name` → `board`
  - `class_name` → `class`
  - `subject_name` → `subject`

#### b) Add Descriptive Docstrings
- Include response examples in API docs
- Clearly state what each endpoint returns
- Document access control rules

#### c) Consider New Convenience Endpoints
- `GET /me/assignments/created` - Only assignments created by user
- `GET /me/assignments/stats` - Summary stats (total, by status, etc.)
- `DELETE /assignments/{id}` - Soft delete (unpublish) or hard delete
- `GET /assignments/{id}/details` - Single assignment with all nested data

#### d) Standardize Error Responses
- 400: Missing/invalid parameters
- 403: Access denied (user doesn't have permission)
- 404: Resource not found

---

## Recommended Final Structure

### User-Centric
- `GET /me/assignments` - User's assignment summary
- `GET /me/assignments/stats` - User's assignment statistics
- `GET /me/assignments/created` - Assignments created by user

### Content Discovery  
- `GET /assignments` - General listing with filters and pagination
- `GET /assignments/catalog` - Search assignments by board/class/subject (detailed)
- `GET /assignments/{id}` - Single assignment details

### Content Management
- `POST /assignments` - Create assignment
- `PUT /assignments/{id}` - Update assignment
- `DELETE /assignments/{id}` - Delete assignment
- `POST /assignments/{id}/publish` - Publish
- `POST /assignments/{id}/unpublish` - Unpublish

### Engagement
- `POST /assignments/{id}/attempts` - Submit assignment
- `POST /assignments/{id}/feedback` - Submit feedback
- `POST /assignments/{id}/doubts` - Create doubt
- `POST /assignments/{id}/report` - Report inappropriate content

---

## Implementation Priority

1. **High Priority (Breaking Changes):**
   - `GET /assignments/my-assignments` → `GET /me/assignments`
   - Standardize query param names

2. **Medium Priority (Convenience):**
   - `GET /assignments/subjects` → `GET /assignments/catalog`
   - Add new stats endpoints

3. **Low Priority (Nice-to-have):**
   - Additional filtering options
   - Advanced search capabilities
