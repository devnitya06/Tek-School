from pydantic_settings import BaseSettings
from pydantic import EmailStr
from typing import Optional
class Settings(BaseSettings):
    PROJECT_NAME: str = "Tek School"
    API_V1_STR: str = "/api/v1"
    
    
    SECRET_KEY: str ="cbec31515284f106467476c89fd53f5c71ca0c847f51c07a566695b24e5fede71591340de0c6bf21d5af5280838041d76fe9e78d0614af07de864b395e2db0021e42949b4030e7fe925c5d0c9f666a944696f6133e3e5c15c67d3fa874bb983f13d0031b6d435d33a748e5f31ca2aaed629181252847bb1127422f3274428a35a21acf7528d728893317f51122bd954e03000ccee602d6b16555c1df7c35d781e0917c16b866a192dca0414fcfbb928b60ea92b5c3ebcebc21ae3841faddb37815199ba3e911016f8202f9c617b99f42b83cf11e14c824ac21789d9760166fd5d4595704926db36f4aa3a13fe0369576a4e165309b73bc7a582edc08b0c13465"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 3  # 180 minutes (3 hours)
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 3  # 3 days
    
    #Database
    DATABASE_URL: str
    
    #Email
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: EmailStr
    MAIL_PORT: int
    MAIL_SERVER: str
    MAIL_FROM_NAME: str
    
    # AWS / S3
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str
    S3_BUCKET_NAME: str
    
    #Razorpay
    RAZORPAY_KEY_ID: Optional[str] = None
    RAZORPAY_KEY_SECRET: Optional[str] = None

    #Redis
    REDIS_URL: Optional[str] = None
    celery_broker_url: Optional[str] = None
    celery_result_backend: Optional[str] = None
    # Frontend / verification links
    FRONTEND_BASE_URL: str = "https://testapi.vidyawings.com"
    PRODUCTION_FRONTEND_HOSTS: list[str] = ["school.beingideal.com"]
    
    #model changed
    
    # CORS
    BACKEND_CORS_ORIGINS: list = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "https://tekschool-school.vercel.app",
    "https://tek-school-student.vercel.app",
    "https://tek-school-admin.vercel.app",
    "https://tek-school-teacher.vercel.app",
    "https://vidya-wings.vercel.app",
    "https://student.beingideal.com",
    "*"
   ]
    class Config:
        env_file = ".env"

settings = Settings()


def get_verification_base_url(frontend_url: Optional[str] = None) -> str:
    """Return the API host used for verification links.

    If the frontend URL points to any of the beingideal.com school experiences,
    use the production API host. Otherwise fall back to the test API host.
    """
    if frontend_url:
        normalized_frontend = frontend_url.rstrip("/").lower()
        production_hosts = {
            "https://school.beingideal.com",
            "http://school.beingideal.com",
            "https://teacher.beingideal.com",
            "http://teacher.beingideal.com",
            "https://student.beingideal.com",
            "http://student.beingideal.com",
            "https://edu.beingideal.com",
            "http://edu.beingideal.com",
        }
        if normalized_frontend in production_hosts:
            return "https://api.beingideal.com"
        if normalized_frontend.endswith((".beingideal.com", "beingideal.com")):
            return "https://api.beingideal.com"

    return "https://testapi.vidyawings.com"
