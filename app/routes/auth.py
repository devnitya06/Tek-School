from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta,datetime,timezone
from jose import JWTError
from app.db.session import get_db
from app.models.users import User,Token
from app.schemas.users import TokenResponse
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    oauth2_scheme,
)
from app.core.config import settings

router = APIRouter(tags=["auth"])

@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
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