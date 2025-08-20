import sys
from app.db.session import SessionLocal
from app.models.users import User
from app.models.admin import Admin
from app.models.school import School
from app.models.teachers import Teacher
from app.models.students import Student
from app.models.users import User
from app.core.security import get_password_hash
from app.schemas.users import UserRole  

def create_superadmin(email: str, password: str, name: str):
    db = SessionLocal()
    try:
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            print(f"❌ User with email '{email}' already exists")
            return

        hashed_password = get_password_hash(password)
        superadmin = User(
            name=name,
            email=email,
            hashed_password=hashed_password,
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True
        )

        db.add(superadmin)
        db.flush()
        admin_profile = Admin(user_id=superadmin.id)
        db.add(admin_profile)
        db.commit()
        print(f"✅ SuperAdmin created successfully: {email}")
    except Exception as e:
        db.rollback()
        print(f"❌ Failed to create SuperAdmin: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python scripts/create_superadmin.py <email> <password> <name>")
        sys.exit(1)
    
    _, email, password, name = sys.argv
    create_superadmin(email=email, password=password, name=name)