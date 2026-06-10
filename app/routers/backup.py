import io
import json
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from app.core.database import get_supabase

router = APIRouter(prefix="/backup", tags=["backup"])

TABLES = [
    "schools", "classes", "teachers", "teacher_class_subjects",
    "students", "subjects", "competencies", "results", "attendance",
    "discipline_records", "fee_balances", "fee_payments",
    "timetable_entries", "cbc_assessments", "class_teacher_remarks",
    "notifications", "report_templates", "admins"
]

@router.get("/export/{school_id}")
async def export_backup(school_id: str):
    db = get_supabase()
    backup = {}
    for table in TABLES:
        try:
            # For tables with school_id, filter by that; others (like subjects, admins) fetch all
            if table in ("subjects", "admins", "competencies", "notifications", "report_templates"):
                data = db.table(table).select("*").execute().data or []
            else:
                data = db.table(table).select("*").eq("school_id", school_id).execute().data or []
            backup[table] = data
        except Exception:
            backup[table] = []
    buffer = io.StringIO()
    json.dump(backup, buffer, default=str, indent=2)
    buffer.seek(0)
    school_name = db.table("schools").select("name").eq("id", school_id).single().execute().data
    filename = f"backup_{school_name['name'].replace(' ', '_')}.json" if school_name else "backup.json"
    return StreamingResponse(
        io.BytesIO(buffer.getvalue().encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.post("/import/{school_id}")
async def import_backup(school_id: str, file: UploadFile = File(...)):
    if not file.filename.endswith(".json"):
        raise HTTPException(400, "Only JSON backup files are accepted")
    contents = await file.read()
    backup = json.loads(contents)
    db = get_supabase()
    imported = {}
    for table in TABLES:
        if table not in backup:
            continue
        rows = backup[table]
        if not rows:
            continue
        # Set school_id if needed, but KEEP id to maintain foreign key relationships
        for row in rows:
            row.pop("created_at", None)
            row.pop("updated_at", None)
            if table not in ("subjects", "admins", "competencies"):
                row["school_id"] = school_id
        try:
            # Use upsert to handle existing IDs gracefully or direct insert if preferred
            # Given it's a restore, insert with IDs is better. 
            # If IDs exist, we might need to delete existing data for that school first to avoid conflicts.
            if table not in ("subjects", "admins", "competencies"):
                db.table(table).delete().eq("school_id", school_id).execute()

            result = db.table(table).insert(rows).execute()
            imported[table] = len(result.data) if result.data else 0
        except Exception as e:
            imported[table] = f"error: {str(e)}"
    return {"message": "Backup imported", "tables": imported}