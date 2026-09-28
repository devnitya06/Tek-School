# Digital Profile Wallet & Billing — Architecture Documentation

## Overview

This document describes the Digital Profile Price Configuration, School Wallet, and Business Inquiry Billing system implemented in the Tek-School FastAPI backend.

---

## Database Tables

### `digital_profile_price_config`
Stores pricing tiers per education associate. Admin/SuperAdmin manage it; Schools read it.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| education_associate | VARCHAR(64) | Enum: `SCHOOL_EDUCATIONS`, `HIGHER_EDUCATION`, `PROFESSIONAL_EDUCATION`, `MEDICAL_PHARMA`, `UNIVERSITY`, `TRAINING_COACHING`, `CREATIVE_TRAINING` |
| education_offered | VARCHAR[] | e.g. `["CBSE","ICSE","JEE"]` |
| first_two_viewer_price | NUMERIC(12,2) | Price for viewers 1–2 (default ₹50) |
| next_five_viewer_price | NUMERIC(12,2) | Price for viewers 3–7 (default ₹20) |
| all_other_viewer_price | NUMERIC(12,2) | Price for viewers 8+ (default ₹10) |
| created_at | TIMESTAMPTZ | Auto-set |
| updated_at | TIMESTAMPTZ | Auto-updated |
| created_by | INTEGER FK→users | Admin who created |
| updated_by | INTEGER FK→users | Admin who last updated |

### `wallet_recharge_config`
Platform-level min/max recharge limits. One active row.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| min_recharge_amount | NUMERIC(12,2) | Default ₹500 |
| max_recharge_amount | NUMERIC(12,2) | Default ₹20,000 |
| created_at / updated_at | TIMESTAMPTZ | |
| created_by / updated_by | FK→users | |

### `wallet_recharge_bonus`
Bonus percentage slabs (belongs to `wallet_recharge_config`).

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| recharge_config_id | FK→wallet_recharge_config | CASCADE delete |
| recharge_amount | NUMERIC(12,2) | Exact amount for bonus (e.g. 5000) |
| bonus_percentage | NUMERIC(5,2) | e.g. 20 = 20% |

**Default seed data:**
```
₹5,000  → 20% bonus
₹10,000 → 15% bonus
₹20,000 → 20% bonus
```

### `school_wallet`
One wallet per school (UNIQUE on school_id).

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| school_id | VARCHAR FK→schools | UNIQUE |
| balance | NUMERIC(12,2) | Never negative; default 0 |
| currency | VARCHAR(8) | Default "INR" |
| created_at / updated_at | TIMESTAMPTZ | |

### `wallet_transactions`
Full audit ledger. Never deleted.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| school_id | FK→schools | |
| transaction_type | VARCHAR(32) | `RECHARGE`, `INQUIRY_DEDUCTION`, `BONUS`, `REFUND`, `ADJUSTMENT` |
| transaction_status | VARCHAR(32) | `PENDING`, `SUCCESS`, `FAILED`, `CANCELLED`, `REFUNDED` |
| amount | NUMERIC(12,2) | + = credit, − = debit |
| bonus_amount | NUMERIC(12,2) | Bonus credited (for RECHARGE) |
| total_credit | NUMERIC(12,2) | amount + bonus_amount |
| balance_before / balance_after | NUMERIC(12,2) | Set on SUCCESS |
| currency | VARCHAR(8) | Default "INR" |
| reference_type | VARCHAR(64) | e.g. "BUSINESS_INQUIRY" |
| reference_id | VARCHAR(128) | e.g. "245" |
| payment_provider | VARCHAR(32) | NULL until Razorpay integrated |
| payment_order_id | VARCHAR(128) | NULL until Razorpay integrated |
| payment_payment_id | VARCHAR(128) | NULL until Razorpay integrated |
| payment_signature | VARCHAR(256) | NULL until Razorpay integrated |
| description | TEXT | |
| created_at / updated_at | TIMESTAMPTZ | |

### `business_inquiry_school`
Per-school seen-state and billing junction.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| business_inquiry_id | FK→business_inquiry | CASCADE delete |
| school_id | FK→schools | CASCADE delete |
| is_seen | BOOLEAN | Default FALSE |
| seen_at | TIMESTAMPTZ | When first viewed |
| viewer_number | INTEGER | School's nth view overall |
| price_per_view | NUMERIC(12,2) | Historical snapshot — never changes |
| amount_deducted | NUMERIC(12,2) | Default 0 |
| wallet_transaction_id | FK→wallet_transactions | SET NULL on delete |
| remark | TEXT | Per-school remark |
| remark_status | VARCHAR(50) | Per-school remark status |
| created_at / updated_at | TIMESTAMPTZ | |

**Unique constraint:** `(business_inquiry_id, school_id)`

---

## Pricing Calculation

```
Viewer 1–2   → first_two_viewer_price  (default ₹50)
Viewer 3–7   → next_five_viewer_price  (default ₹20)
Viewer 8+    → all_other_viewer_price  (default ₹10)
```

Viewer count is **per school** — not global. Only successful (`is_seen=True`) views count.

**Example** (School A, config: ₹50/₹20/₹10):
```
Inquiry #1 → viewer 1 → ₹50  (balance: ₹500→₹450)
Inquiry #2 → viewer 2 → ₹50  (balance: ₹450→₹400)
Inquiry #3 → viewer 3 → ₹20  (balance: ₹400→₹380)
Inquiry #7 → viewer 7 → ₹20
Inquiry #8 → viewer 8 → ₹10
```

---

## Wallet Lifecycle

```
1. School created → wallet auto-created at first use (balance=0)
2. School initiates recharge → PENDING transaction (wallet NOT credited)
3. Future: Razorpay payment confirmed → PENDING→SUCCESS, wallet credited
4. School views inquiry → atomic deduction (INQUIRY_DEDUCTION, SUCCESS)
```

### State Machine
```
PENDING → SUCCESS
PENDING → FAILED
PENDING → CANCELLED
```
`SUCCESS → SUCCESS` is blocked (double-credit prevention).

---

## Business Inquiry Billing Flow

When `GET /school/business-inquiry/{id}` is called by a SCHOOL:

```
1. Find BusinessInquiry, verify school_id in school_ids
2. Find/create BusinessInquirySchool junction row
3. If already seen (is_seen=True):
       → return inquiry + historical price, NO deduction
4. Lock wallet row (FOR UPDATE)
5. Count existing seen views for this school
6. Calculate next_viewer_number and price
7. Check wallet.balance >= price
   → If not: raise HTTP 402 INSUFFICIENT_WALLET_BALANCE
8. Deduct wallet: balance -= price
9. Create WalletTransaction (INQUIRY_DEDUCTION, SUCCESS)
10. Update junction: is_seen=True, seen_at, viewer_number, price_per_view, amount_deducted
11. Commit all at once (atomic)
12. Return inquiry details
```

### Historical Price Preservation
Price is stored in `business_inquiry_school.price_per_view` at view time. Even if admin later changes the pricing config, historical views always show the original price.

---

## API Reference

### Digital Profile Price Config

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `/digital-profile/price-config` | ADMIN, SUPERADMIN, SCHOOL | List configs |
| POST | `/digital-profile/price-config` | ADMIN, SUPERADMIN | Create config |
| PATCH | `/digital-profile/price-config/{id}` | ADMIN, SUPERADMIN | Update config |

### Wallet Recharge Config

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `/wallet/recharge-config` | ADMIN, SUPERADMIN, SCHOOL | Get config |
| PATCH | `/wallet/recharge-config` | ADMIN, SUPERADMIN | Update config |

### School Wallet

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `/wallet/school/wallet` | SCHOOL | Own wallet balance |
| POST | `/wallet/school/wallet/recharge` | SCHOOL | Initiate recharge (PENDING) |
| GET | `/wallet/school/wallet/transactions` | SCHOOL | Transaction history |

### Business Inquiry

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `/school/business-inquiry` | SCHOOL | List (with view_price per item) |
| GET | `/school/business-inquiry/{id}/view-price` | SCHOOL | Price check (no deduction) |
| GET | `/school/business-inquiry/{id}` | SCHOOL | View detail (atomic billing) |
| PATCH | `/school/business-inquiry/{id}/remark` | SCHOOL, ADMIN | Add remark (per-school) |

### Admin Wallet Audit

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `/wallet/admin/wallet/transactions` | ADMIN, SUPERADMIN | All transactions |
| GET | `/wallet/admin/schools/{school_id}/wallet` | ADMIN, SUPERADMIN | School wallet summary |
| GET | `/admin/business-inquiry` | ADMIN, SUPERADMIN | All inquiries |

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| INSUFFICIENT_WALLET_BALANCE | 402 | Wallet balance < view price |
| CONFIGURATION_NOT_FOUND | 404 | No price config exists |
| WALLET_NOT_FOUND | 404 | No wallet for school |
| INVALID_RECHARGE_AMOUNT | 400 | Amount outside min/max range |
| INVALID_TRANSACTION_STATE | 409 | Cannot re-confirm SUCCESS transaction |
| BUSINESS_INQUIRY_NOT_FOUND | 404 | Inquiry not found or school not in school_ids |

---

## Future Razorpay Integration

The wallet is designed to support Razorpay without redesigning the wallet system:

### Step 1: Update `initiate_wallet_recharge` in `services/billing.py`
```python
# After creating txn (PENDING):
razorpay_order = razorpay_client.order.create({
    "amount": int(amount * 100),  # paise
    "currency": "INR",
    "receipt": f"txn_{txn.id}",
})
txn.payment_provider = "RAZORPAY"
txn.payment_order_id = razorpay_order["id"]
```

### Step 2: Add verify endpoint
```
POST /school/wallet/recharge/verify
  → Verify Razorpay signature
  → Call confirm_wallet_recharge(transaction_id, db, ...)
  → Wallet credited
```

### Step 3: Add webhook
```
POST /webhooks/payment/razorpay
  → Parse event
  → If payment.captured: call confirm_wallet_recharge()
```

All wallet logic (`confirm_wallet_recharge`) is already implemented and Razorpay-agnostic.

---

## Concurrency

- Wallet deduction uses `SELECT ... FOR UPDATE` on the `school_wallet` row.
- Viewer count uses `SELECT ... FOR UPDATE` on `business_inquiry_school` aggregate.
- This prevents double-deduction and duplicate viewer numbers under concurrent requests.
- All deduction steps happen in one DB transaction (atomic commit/rollback).

---

## Money Handling

All amounts use `NUMERIC(12,2)` in PostgreSQL and Python `Decimal` — **never float**. This prevents floating-point precision errors in financial calculations.
