from . import (
    auth, schools, teachers, students, classes, 
    results, analytics, enhanced_analytics, risk, ml_risk,
    attendance, discipline, cbc,
    fees, report_builder, reports,
    ai_assistant, messages, notifications,
    admin, subscription, bulk_import, admissions,
    timetable, timetable_auto,
    public, exports, backup, badges,
    headteacher, dean, subjects, class_teacher,
    print as print_router, teacher_analytics, forecasts
)

# Note: Some routers were renamed in imports for clarity/uniqueness

def register_routers(app):
    """
    Modular router registration to keep main.py clean.
    """
    routers = [
        auth.router, schools.router, teachers.router, students.router, classes.router,
        results.router, analytics.router, enhanced_analytics.router, risk.router, ml_risk.router,
        attendance.router, discipline.router, cbc.router,
        fees.router, report_builder.router, reports.router,
        ai_assistant.router, messages.router, notifications.router,
        admin.router, subscription.router, bulk_import.router, admissions.router,
        timetable.router, timetable_auto.router,
        public.router, exports.router, backup.router, badges.router,
        headteacher.router, dean.router, subjects.router, class_teacher.router,
        print_router.router, teacher_analytics.router, forecasts.router
    ]
    
    for r in routers:
        app.include_router(r)
