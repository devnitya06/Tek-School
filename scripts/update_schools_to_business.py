import sys
from app.db.session import SessionLocal
from app.models.school import School, SchoolAccountType

def update_all_schools_to_business():
    """
    Update all existing school accounts to business accounts.
    Sets account_type to BUSINESS, is_business_approved to True, and is_promotion_pending to False.
    """
    db = SessionLocal()
    try:
        # Get all schools
        schools = db.query(School).all()
        
        if not schools:
            print("ℹ️  No schools found in the database")
            return
        
        print(f"📊 Found {len(schools)} school(s) to update")
        
        updated_count = 0
        skipped_count = 0
        
        for school in schools:
            # Check if already business
            if school.account_type == SchoolAccountType.BUSINESS:
                print(f"⏭️  Skipping {school.school_name} (ID: {school.id}) - Already business account")
                skipped_count += 1
                continue
            
            # Update to business account
            school.account_type = SchoolAccountType.BUSINESS
            school.is_business_approved = True  # Approve immediately so they can login
            school.is_promotion_pending = False
            if not school.is_verified:
                school.is_verified = True  # Also set general verification if not already set
            
            updated_count += 1
            print(f"✅ Updated {school.school_name} (ID: {school.id}) to BUSINESS account")
        
        # Commit all changes
        db.commit()
        
        print("\n" + "="*50)
        print(f"✅ Successfully updated {updated_count} school(s) to BUSINESS account")
        if skipped_count > 0:
            print(f"⏭️  Skipped {skipped_count} school(s) (already business accounts)")
        print("="*50)
        
    except Exception as e:
        db.rollback()
        print(f"❌ Failed to update schools: {str(e)}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Starting school account update process...")
    print("="*50)
    update_all_schools_to_business()
    print("\n✨ Process completed!")
