from app.repositories.base_repository import BaseRepository

class StudentRepository(BaseRepository):
    def __init__(self):
        super().__init__("students")

    def get_full_profile(self, student_id: str, term: str):
        # The complex nested select we developed earlier
        # Removed class_teacher_remarks from main select for robustness (PGRST108 prevention)
        return self.db.table(self.table_name).select("""
            *,
            classes(name, school_id),
            schools(name),
            results(*, subjects(name)),
            attendance(status),
            discipline_records(*),
            fee_balances(*),
            fee_payments(*),
            student_badges(id, term, badges(name, icon_url, description), teachers(name))
        """)\
        .eq("id", student_id)\
        .eq("results.term", term)\
        .eq("results.approval_status", "approved")\
        .eq("fee_balances.term", term)\
        .eq("fee_payments.term", term)\
        .limit(1)\
        .execute()
