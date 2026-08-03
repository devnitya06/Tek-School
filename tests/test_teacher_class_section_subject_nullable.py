from app.models.teachers import TeacherClassSectionSubject


def test_teacher_class_section_subject_allows_null_teacher_id():
    mapping = TeacherClassSectionSubject(
        class_id=1,
        section_id=1,
        subject_id=1,
        school_id=1,
    )

    assert mapping.teacher_id is None
