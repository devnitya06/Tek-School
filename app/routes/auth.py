from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta,datetime,timezone
from jose import JWTError
from app.db.session import get_db
from app.models.users import User,Token,Otp
from app.schemas.users import TokenResponse,LoginRequest
from app.utils.email_utility import generate_otp,send_dynamic_email
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    oauth2_scheme,
)
from app.core.config import settings

router = APIRouter(tags=["auth"])

@router.post("/login/", response_model=TokenResponse)
async def login(
    form_data: LoginRequest,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == form_data.email).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role},
        expires_delta=access_token_expires
    )
    
    refresh_token_expires = timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    refresh_token = create_refresh_token(
        data={"sub": str(user.id)},
        expires_delta=refresh_token_expires
    )
    
    # Store refresh token in database
    db_refresh_token = Token(
        user_id=user.id,
        token=refresh_token,
        expires_at=datetime.now(timezone.utc) + refresh_token_expires
    )
    db.add(db_refresh_token)
    db.commit()
    db.refresh(db_refresh_token)
    
    return {
        "message": "Login successful",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "role": user.role
    }

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_token: str,
    db: Session = Depends(get_db)
):
    """Generate new access token using refresh token"""
    try:
        payload = verify_token(refresh_token, is_refresh=True)
        user_id = int(payload.get("sub"))
        
        # Verify refresh token exists in DB and is valid
        db_token = db.query(Token).filter(
            Token.token == refresh_token,
            Token.user_id == user_id,
            Token.expires_at > datetime.now(timezone.utc)
        ).first()
        
        if not db_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token"
            )
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        # Generate new tokens
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        new_access_token = create_access_token(
            data={"sub": str(user.id), "role": user.role},
            expires_delta=access_token_expires
        )
        
        # Optionally rotate refresh token (recommended for security)
        refresh_token_expires = timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
        new_refresh_token = create_refresh_token(
            data={"sub": str(user.id)},
            expires_delta=refresh_token_expires
        )
        
        # Update tokens in database
        db.delete(db_token)
        new_db_token = Token(
            user_id=user.id,
            token=new_refresh_token,
            expires_at=datetime.now(timezone.utc) + refresh_token_expires
        )
        db.add(new_db_token)
        db.commit()
        
        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "role": user.role
        }
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

@router.post("/logout")
async def logout(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        # Verify the access token to get user info
        payload = verify_token(token)
        user_id = int(payload.get("sub"))
        
        # Invalidate all refresh tokens for this user
        db.query(Token).filter(Token.user_id == user_id).delete()
        db.commit()
        
        return {"message": "Successfully logged out"}
    
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/forgot-password/")
async def forgot_password(
    email: str,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    otp = generate_otp()

    # Either update or create new OTP
    existing_otp = db.query(Otp).filter(Otp.user_id == user.id).order_by(Otp.created_at.desc()).first()

    if existing_otp and not existing_otp.is_verified:
        raise HTTPException(status_code=400, detail="OTP already sent and pending verification")

    if existing_otp:
        # Reuse entry
        existing_otp.otp = otp
        existing_otp.is_verified = False
        existing_otp.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        existing_otp.created_at = datetime.now(timezone.utc)
    else:
        # Create new OTP
        new_otp = Otp(
            user_id=user.id,
            otp=otp,
            is_verified=False,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            created_at=datetime.now(timezone.utc),
        )
        db.add(new_otp)

    db.commit()

    try:
        send_dynamic_email(
            context_key="otp_verify.html",
            subject="Your OTP for Password Reset",
            recipient_email=user.email,
            context_data={
                "email": user.email,
                "OTP": otp,
            },
            db=db
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send email: {str(e)}"
        ) from e

    return {"message": "OTP has been sent to your email."} 
     