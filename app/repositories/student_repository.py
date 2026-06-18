from app.repositories.base_repository import BaseRepository

class StudentRepository(BaseRepository):
    def __init__(self):
        super().__init__("students")

    def get_full_profile(self, student_id: str, term: str):
        # The complex nested select we developed earlier
        return self.db.table(self.table_name).select("""
            *,
            classes(name, school_id),
            schools(name),
            results(*, subjects(name)),
            attendance(status),
            discipline_records(*),
            fee_balances(*),
            fee_payments(*),
            class_teacher_remarks(remark),
            student_badges(id, term, badges(name, icon_url, description), teachers(name))
        """)\
        .eq("id", student_id)\
        .eq("results.term", term)\
        .eq("results.approval_status", "approved")\
        .eq("fee_balances.term", term)\
        .eq("fee_payments.term", term)\
        .eq("class_teacher_remarks.term", term)\
        .limit(1)\
        .execute()
