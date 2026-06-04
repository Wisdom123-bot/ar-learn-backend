import io
import zipfile
import tempfile
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Optional
from app.core.database import get_supabase
from app.services.report_service import generate_student_report_pdf

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/student/{student_id}")
async def get_student_report(
    student_id: str,
    term: str = Query(..., description="e.g. 'Term 1 2025'"),
    template_id: Optional[str] = Query(None),
):
    try:
        pdf_bytes = generate_student_report_pdf(student_id, term, template_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{student_id}.pdf"},
    )


@router.get("/class/{class_id}")
async def get_class_reports(
    class_id: str,
    term: str = Query(..., description="e.g. 'Term 1 2025'"),
    template_id: Optional[str] = Query(None),
):
    db = get_supabase()
    cls = db.table("classes").select("id, name").eq("id", class_id).execute()
    if not cls.data:
        raise HTTPException(status_code=404, detail="Class not found")

    students = db.table("students").select("id, name").eq("class_id", class_id).execute().data or []
    if not students:
        raise HTTPException(status_code=404, detail="No students found in this class")

    # Use a temporary file that will spill to disk if it grows too large
    tmp = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)  # 10 MB in memory, then disk
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for student in students:
            try:
                pdf_bytes = generate_student_report_pdf(student["id"], term, template_id)
                filename = f"{student['name'].replace(' ', '_')}_{student['id'][:8]}.pdf"
                zf.writestr(filename, pdf_bytes)
            except Exception as e:
                zf.writestr(f"{student['name']}_error.txt", f"Could not generate report: {e}")

    tmp.seek(0)
    class_name = cls.data[0]["name"]
    return StreamingResponse(
        tmp,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=reports_{class_name}_{term}.zip"},
    )


@router.get("/school/{school_id}")
async def get_school_reports(
    school_id: str,
    term: str = Query(..., description="e.g. 'Term 1 2025'"),
    template_id: Optional[str] = Query(None),
):
    db = get_supabase()
    school = db.table("schools").select("id, name").eq("id", school_id).execute()
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")

    students = db.table("students").select("id, name, class_id").eq("school_id", school_id).execute().data or []
    if not students:
        raise HTTPException(status_code=404, detail="No students found in this school")

    # Use a temporary file that will spill to disk if it grows too large
    tmp = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)  # 10 MB in memory, then disk
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for student in students:
            try:
                pdf_bytes = generate_student_report_pdf(student["id"], term, template_id)
                filename = f"{student['name'].replace(' ', '_')}_{student['id'][:8]}.pdf"
                zf.writestr(filename, pdf_bytes)
            except Exception as e:
                zf.writestr(f"{student['name']}_error.txt", f"Could not generate report: {e}")

    tmp.seek(0)
    school_name = school.data[0]["name"]
    return StreamingResponse(
        tmp,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=reports_{school_name}_{term}.zip"},
    )