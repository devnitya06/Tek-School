from app.db.session import SessionLocal
from app.schemas.tuition.teaching_setup import TeachingSetupCreate
from app.services.tuition.teaching_setup import create_teaching_setup_service
from app.schemas.users import UserRole

class DummyUser:
    id = 1359
    role = UserRole.SELF_SIGNED_TEACHER
    self_signed_teacher_profile = type('P', (), {'id': 1})()

payload = TeachingSetupCreate(
    teaching_mode='ONLINE_CLASS_AND_STUDY_MATERIALS',
    lesson_plan_id='LPNTKVBPBK',
    batch_id='IDGHRKIQ82',
    batch_title='Evening Mathematics Batch',
    batch_start_date='2026-08-01',
    batch_end_date='2026-12-31',
    tuition_from_time='18:00',
    tuition_to_time='19:00',
    tuition_days=['MONDAY', 'WEDNESDAY', 'FRIDAY'],
    languages=['English', 'Hindi'],
    monthly_tuition_fee=1500,
    monthly_tuition_discount=200,
    premium_study_material_fee=100,
    premium_study_material_discount=50,
    meeting_provider='GOOGLE_MEET',
    meeting_link='https://meet.google.com/abc-defg-hij',
    online_teaching_ability=True,
    stable_internet_connection=True,
    camera_available=True,
    silent_place_without_background_noise=True,
    laptop_desktop_pc=True,
    headphone_whiteboard=True,
    maximum_students=30,
    status='ACTIVE',
)

db = SessionLocal()
try:
    result = create_teaching_setup_service(db, current_user=DummyUser(), payload=payload, self_signed_teacher_id=1)
    print('created', result.id)
except Exception as exc:
    import traceback
    traceback.print_exc()
    db.rollback()
