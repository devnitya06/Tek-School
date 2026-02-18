# Postman – School Info API

## Import

1. Open Postman.
2. **Import** → **File** → choose `School_Info_API.postman_collection.json`.

## Setup

1. **Collection variables** (optional):  
   Open the collection → **Variables** and set:
   - `base_url`: e.g. `http://localhost:8000` (default).
   - `school_id`: target school id (for Admin; School user uses own).
   - `school_info_id`: filled automatically after **Create School Info** (or set manually for Get/Update/Delete).

2. **Get token**  
   Run **Auth → Login (School / Admin)** with your email/password.  
   The script saves `access_token` into the collection; all **School Info** requests use it as Bearer token.

## Requests

| Request | Method | Description |
|--------|--------|-------------|
| **Login (School / Admin)** | POST | Login; saves `access_token`. |
| **Create School Info** | POST | Create one record per school. Admin: send `school_id` (query or body). |
| **List School Info** | GET | List (School: own only; Admin: all or filter by `school_id`). |
| **Get School Info by School ID** | GET | Get by `school_id`. |
| **Get School Info by ID** | GET | Get by primary key `id`. |
| **Update School Info** | PUT | Update by `id` (partial body). |
| **Delete School Info** | DELETE | Delete by `id`. |

## Quick test

1. Run **Login** with school or admin credentials.
2. Run **Create School Info** (leave `school_id` empty if you are a School user).
3. Run **List School Info** or **Get School Info by ID** to read.
4. Run **Update School Info** then **Get** to verify.
5. Run **Delete School Info** to remove the record.
