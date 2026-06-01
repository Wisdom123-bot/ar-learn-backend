from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import schools
from app.routers import auth
from app.routers import schools, auth, teachers, results, analytics, attendance, risk, approval,  reports, fees, parents, ai_assistant
from app.routers import bulk_import
from app.routers import timetable
from app.routers import teacher_analytics
from app.routers import headteacher
from app.routers import admin
from app.routers import discipline
from app.routers import class_teacher
from app.routers import enhanced_analytics
from app.routers import dean
from app.routers import subjects
from app.routers import print as print_router
from app.routers import students
from app.routers import notifications
from app.routers import report_builder
from app.routers import exports
from app.routers import ml_risk

app = FastAPI(
    title="Ar-Learn API",
    description="School Management & Analytics System for Kenyan Schools",
    version="0.1.0",
)


# Allow all origins for development (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(schools.router)
app.include_router(auth.router)
app.include_router(teachers.router)
app.include_router(results.router)
app.include_router(analytics.router)
app.include_router(attendance.router)
app.include_router(risk.router)
app.include_router(approval.router)
app.include_router(reports.router)
app.include_router(fees.router)
app.include_router(parents.router)
app.include_router(ai_assistant.router)
app.include_router(bulk_import.router)
app.include_router(timetable.router)
app.include_router(teacher_analytics.router)
app.include_router(headteacher.router)
app.include_router(admin.router)
app.include_router(discipline.router)
app.include_router(class_teacher.router)
app.include_router(enhanced_analytics.router)
app.include_router(dean.router)
app.include_router(subjects.router)
app.include_router(print_router.router)
app.include_router(students.router)
app.include_router(notifications.router)
app.include_router(report_builder.router)
app.include_router(exports.router)
app.include_router(ml_risk.router)

@app.get("/")
async def root():
    return {"message": "Ar-Learn API is running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}