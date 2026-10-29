# School Profile Institution Details and Facilities

## Endpoints

- Read a profile: `GET /school/school?school_id=SCH-123459`
- Update a profile: `PATCH /school/school-profile`

The update endpoint uses the authenticated user's school profile. Admin and agent callers may supply `school_id` as a query parameter where permitted by the existing role and ownership checks. School users retain the existing OTP confirmation for sensitive profile fields.

## Allowed values

| Field | Type | Allowed values |
|---|---|---|
| `city` | Nullable string | Free-form city name; set through school profile update, not institution creation |
| `accreditation` | Multi-select string array | `naac`, `nba`, `nirf`, `other` |
| `recognition_approval` | Multi-select string array | `ugc`, `aicte`, `nmc`, `pci`, `bci`, `ncte`, `other` |
| `institution_type` | Single-select string | `school`, `college`, `university`, `coaching_centre`, `training_center`, `creative_training_center` |
| `accommodation_type` | Multi-select string array | `day_general`, `day_boarding`, `boarding_residential`, `day_cum_boarding`, `online`, `hybrid` |
| `have_digital_board` | Single-select string | `yes`, `no`, `under_development` |
| `computer_lab` | Single-select string | `yes`, `no`, `under_development` |
| `library` | Single-select string | `yes`, `no`, `under_development` |
| `transportation_facility` | Single-select string | `available`, `not_available`, `temporarily_unavailable` |
| `playground_facility` | Single-select string | `none`, `indoor`, `outdoor`, `both` |
| `have_cctv_in_campus` | Single-select string | `available`, `not_available`, `partial_coverage` |
| `admission_process` | Multi-select string array | `direct`, `entrance_exam`, `merit_mark_based`, `interview`, `other` |
| `medical_faculties` | Single-select string | `first_aid`, `medical_room`, `on_campus_medical_staff`, `not_available` |
| `have_scholarship_opportunities` | Single-select string | `available`, `not_available`, `contact_institution` |
| `have_extra_curricular_activities` | Single-select string | `available`, `not_available` |
| `lms_facility` | Single-select string | `integrated`, `not_integrated`, `under_implementation` |
| `hostel` | Multi-select string array | `boys`, `girls`, `both`, `not_available` |

Add recognized regulatory authorities to `RecognitionApprovalEnum` in `app/models/school.py` when the set needs to expand.

API values use lowercase snake_case. `both` in `hostel` is normalized to `["boys", "girls"]` before saving and in the response. `not_available` cannot be combined with any other hostel selection. Empty arrays clear multi-select values; omitted fields are left unchanged.

## Example update

```json
{
  "accreditation": ["naac", "nirf"],
  "recognition_approval": ["ugc", "aicte"],
  "institution_type": "school",
  "accommodation_type": ["day_general", "day_boarding"],
  "have_digital_board": "yes",
  "computer_lab": "yes",
  "library": "under_development",
  "transportation_facility": "available",
  "playground_facility": "outdoor",
  "have_cctv_in_campus": "available",
  "admission_process": ["direct", "merit_mark_based"],
  "medical_faculties": "first_aid",
  "have_scholarship_opportunities": "available",
  "have_extra_curricular_activities": "available",
  "lms_facility": "integrated",
  "hostel": ["boys", "girls"]
}
```

The response is `{ "detail": "...", "profile": { ... } }`. `profile` contains the same school fields, verification/account properties, and rating properties returned by the GET endpoint. Multi-select values are read from the database.

Example GET response fields (other existing school, account, verification, and rating properties are also returned):

```json
{
  "id": "SCH-123459",
  "city": "Pune",
  "accreditation": ["naac", "nirf"],
  "recognition_approval": ["ugc", "aicte"],
  "institution_type": "school",
  "accommodation_type": ["day_general", "day_boarding"],
  "have_digital_board": "yes",
  "computer_lab": "yes",
  "library": "under_development",
  "transportation_facility": "available",
  "playground_facility": "outdoor",
  "have_cctv_in_campus": "available",
  "admission_process": ["direct", "merit_mark_based"],
  "medical_faculties": "first_aid",
  "have_scholarship_opportunities": "available",
  "have_extra_curricular_activities": "available",
  "lms_facility": "integrated",
  "hostel": ["boys", "girls"]
}
```

## Migration and compatibility

Apply the migration before deploying the new application code:

```powershell
.\venv\Scripts\alembic.exe upgrade head
```

Revision `d8f3a1c9b742` adds nullable institution columns and `city`, converts admission processing to `VARCHAR[]`, and changes boolean facilities to nullable text. The old `false` database defaults on scholarship and extracurricular booleans are removed so new records remain unset until entered. Existing values are mapped only when their meaning is known. A legacy playground `yes` becomes `NULL` because it does not identify an indoor/outdoor type; legacy transportation `not_applicable` becomes `NULL`; unsupported legacy values are nulled. Existing hostel selections are normalized to lowercase canonical values. Downgrade maps representable values back; converting multiple admission choices back to a single legacy value and dropping the new institution columns is lossy.

Frontend clients must use lowercase snake_case facility values, and send/receive `admission_process` as an array. `hostel` continues to use an array but now returns canonical lowercase values.
