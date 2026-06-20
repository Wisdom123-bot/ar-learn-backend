from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
import base64
from app.services.cbc_vision_service import analyze_cbc_project
from app.dependencies import get_current_user

router = APIRouter(prefix="/cbc", tags=["cbc"])

@router.post("/analyze-project")
async def analyze_project(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint for teachers to upload and analyze CBC projects.
    """
    # 1. Read and encode image
    try:
        contents = await file.read()
        image_b64 = base64.b64encode(contents).decode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid image file.")

    # 2. Vision Analysis
    analysis = await analyze_cbc_project(image_b64)
    
    return {
        "status": "success",
        "analysis": analysis
    }
