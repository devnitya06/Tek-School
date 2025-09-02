from fastapi import APIRouter, Depends, HTTPException,BackgroundTasks,Query
from sqlalchemy.orm import Session
from app.core.security import get_password_hash
from app.schemas.users import UserCreate,UserRole,OtpVerify,SignupResponse,ResendOtpRequest
from app.db.session import get_db
from app.models.users import User,Otp
from app.models.school import School
from app.utils.email_utility import generate_otp,send_dynamic_email,generate_password
from datetime import datetime,timezone,timedelta
from app.core.security import verify_verification_token
from app.core.config import settings

router = APIRouter()

@router.post("/", response_model=SignupResponse)
def signup(user_data: UserCreate, db: Session = Depends(get_db)):
    try:
        # Check for duplicate email
        if db.query(User).filter(User.email == user_data.email).first():
            raise HTTPException(status_code=400, detail="Email already registered.")

        # Determine role based on presence of school info
        is_school_signup = all([
            user_data.name,
            user_data.location,
            user_data.phone,
            user_data.website
        ])
        role = UserRole.SCHOOL if is_school_signup else UserRole.ADMIN

        # Check for existing school
        if role == UserRole.SCHOOL:
            existing_school = db.query(User).filter(
                User.name == user_data.name,
                User.location == user_data.location,
                User.role == UserRole.SCHOOL
            ).first()
            if existing_school:
                raise HTTPException(
                    status_code=400,
                    detail="A school with the same name and location already exists."
                )

        # Create user
        user = User(
            email=user_data.email,
            name=user_data.name,
            location=user_data.location,
            phone=user_data.phone,
            website=user_data.website,
            role=role,
        )
        db.add(user)
        db.flush()  # Ensures user.id is available without committing

        # Create school profile
        if role == UserRole.SCHOOL:
            school_profile = School(
                user_id=user.id,
                school_name=user_data.name,
                school_email=user_data.email,
                school_phone=user_data.phone,
                school_website=user_data.website,
            )
            db.add(school_profile)

        # Generate OTP and store
        otp = generate_otp()
        otp_entry = Otp(
            user_id=user.id,
            otp=otp
        )
        db.add(otp_entry)

        # Send email (before final commit)
        send_dynamic_email(
            context_key="otp_verify.html",
            subject="Your OTP Code",
            recipient_email=user.email,
            context_data={
                "email": user.email,
                "OTP": otp,
            },
            db=db
        )

        # Final commit after all steps succeed
        db.commit()
        return {
            "detail": "OTP sent to your email. Please verify to complete signup.",
            "user_id": user.id
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Signup failed: {str(e)}")
    
@router.post("/verify-otp")
def verify_otp(data: OtpVerify, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User with this email not found")
    otp_entry = db.query(Otp).filter(Otp.user_id == user.id, Otp.otp == data.otp).first()
    if not otp_entry:
        raise HTTPException(status_code=400, detail="Invalid OTP for this email")
    if otp_entry.is_verified:
        raise HTTPException(status_code=400, detail="OTP already verified")
    current_time = datetime.now(timezone.utc)
    if otp_entry.expires_at.replace(tzinfo=None) < current_time.replace(tzinfo=None):
        db.delete(otp_entry)
        db.commit()
        raise HTTPException(status_code=400, detail="OTP has expired")
    raw_password = generate_password()
    user.hashed_password = get_password_hash(raw_password)
    otp_entry.is_verified = True
    db.add(user)
    db.commit()
    send_dynamic_email(
            context_key="credential.html",
            subject="Your Credentials",
            recipient_email=user.email,
            context_data={
                "email": user.email,
                "password": raw_password,
            },
            db=db
        )
    return {
        "detail": "OTP verified successfully. Get your credentials from your email."
    }

@router.get("/verify-account")
def verify_account(token: str = Query(...), db: Session = Depends(get_db)):
    user_id = verify_verification_token(token,settings.SECRET_KEY,settings.ALGORITHM)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token.")

    if user.is_verified:
        return {"detail": "Account is already verified."}
    raw_password = generate_password()
    user.hashed_password = get_password_hash(raw_password)
    user.is_verified = True
    db.commit()
    send_dynamic_email(
        context_key="credential.html",
        subject="Your Credentials",
        recipient_email=user.email,
        context_data={
                "email": user.email,
                "password": raw_password,
            },
            db=db
    )

    return {"detail": "Account verified. Password sent to registered email."}    
@router.post("/resend-otp")
def resend_otp(data:ResendOtpRequest, db: Session = Depends(get_db)):
    # Step 1: Get user by email
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User with this email not found")

    # Step 2: Delete existing OTPs for the user
    db.query(Otp).filter(Otp.user_id == user.id).delete()

    # Step 3: Generate new OTP and expiration
    otp = generate_otp()
    otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=10)

    # Step 4: Save new OTP
    new_otp = Otp(user_id=user.id, otp=otp, expires_at=otp_expiry)
    db.add(new_otp)
    db.commit()

    # Step 5: Send OTP via email
    send_dynamic_email(
            context_key="otp_verify.html",
            subject="Your OTP Code",
            recipient_email=user.email,
            context_data={
                "email": user.email,
                "OTP": otp,
            },
            db=db
        )

    return {"detail": "A new OTP has been sent to your email."}
    