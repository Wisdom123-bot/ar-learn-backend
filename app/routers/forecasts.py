from fastapi import APIRouter, HTTPException, Depends, Query
from app.core.database import get_supabase
from app.services.forecast_service import generate_student_forecast
from app.dependencies import get_current_user

router = APIRouter(prefix="/analytics/forecast", tags=["forecasting"])

@router.get("/{student_id}")
async def get_grade_forecast(
    student_id: str,
    current_user: dict = Depends(get_current_user)
):
    db = get_supabase()
    
    # 1. Verification
    student = db.table("students").select("school_id").eq("id", student_id).single().execute()
    if not student.data or student.data["school_id"] != current_user["school_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    # 2. Fetch results history
    results = db.table("results")\
        .select("score, term, academic_year")\
        .eq("student_id", student_id)\
        .eq("approval_status", "approved")\
        .order("academic_year")\
        .order("term")\
        .execute()
    
    if not results.data:
        raise HTTPException(status_code=404, detail="Insufficient data for forecasting.")

    # 3. Generate ML Forecast
    forecast = generate_student_forecast(results.data)
    
    return forecast
