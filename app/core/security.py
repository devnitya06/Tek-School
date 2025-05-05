from datetime import datetime, timedelta,timezone
from typing import Optional,Dict,Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from fastapi.security import OAuth2PasswordBearer

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt

def create_refresh_token(
    data: Dict[str, Any],  # Changed to accept data dict like create_access_token
    expires_delta: Optional[timedelta] = None
) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "token_type": "refresh"})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,  # Use refresh secret key
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt

def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str):
    return pwd_context.hash(password)

def decode_token(token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None
    
def verify_token(token: str, is_refresh: bool = False) -> dict:
    secret = settings.SECRET_KEY if is_refresh else settings.SECRET_KEY
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[settings.ALGORITHM]
        )
        # Check token expiration
        if datetime.fromtimestamp(payload["exp"]) < datetime.now():
            raise JWTError("Token expired")
        return payload
    except JWTError as e:
        raise JWTError(f"Token verification failed: {str(e)}")    