import io
import csv
import openpyxl
import random
import string
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, status
from PyPDF2 import PdfReader
from app.core.database import get_supabase

router = APIRouter(prefix="/import", tags=["bulk-import"])

BATCH_SIZE = 50   # Insert 50 students at a time


def extract_names_from_pdf(file_bytes: bytes) -> List[dict]:
    """Extract student names from PDF. Returns list of dicts with 'name' key."""
    reader = PdfReader(io.BytesIO(file_bytes))
    names = []
    for page in reader.pages:
        text = page.extract_text()
        if not text:
            continue
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if not line or line.isdigit():
                continue
            # If line contains a colon, treat as label: value and take the value
            if ":" in line:
                # Use only the part after the first colon, trimmed
                name = line.split(":", 1)[1].strip()
                if name:
                    names.append({"name": name, "admission_number": None, "year": None})
            else:
                # Entire line is a name
                names.append({"name": line, "admission_number": None, "year": None})
    # If nothing found, try splitting all words as names (last resort)
    if not names:
        for page in reader.pages:
            text = page.extract_text()
            if text:
                words = text.split()
                for w in words:
                    if w.isalpha() and len(w) > 1:
                        names.append({"name": w, "admission_number": None, "year": None})
    return names


def extract_names_from_excel(file_bytes: bytes) -> List[str]:
    """Read first column of Excel file (names)."""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
    sheet = wb.active
    names = []
    for row in sheet.iter_rows(min_row=1, max_col=1, values_only=True):
        if row and row[0] and isinstance(row[0], str):
            name = row[0].strip()
            if name.lower() not in ("name", "student name", "names", ""):
                names.append(name)
    return names


def extract_names_from_csv(file_bytes: bytes) -> List[str]:
    """Read first column of CSV (names)."""
    text = file_bytes.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    names = []
    for row in reader:
        if row and row[0].strip():
            name = row[0].strip()
            if name.lower() not in ("name", "student name", "names", ""):
                names.append(name)
    return names


@router.post("/students")
async def import_students(
    school_id: str = Form(...),
    class_id: str = Form(...),
    file: UploadFile = File(...),
):
    db = get_supabase()

    # Validate school and class
    school = db.table("schools").select("id").eq("id", school_id).execute()
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")
    cls = db.table("classes").select("id").eq("id", class_id).eq("school_id", school_id).execute()
    if not cls.data:
        raise HTTPException(status_code=404, detail="Class not found or not in this school")

    file_bytes = await file.read()
    filename = file.filename.lower() if file.filename else ""

    # Extract raw names (list of dicts with at least "name")
    raw_students = []
    if filename.endswith(".pdf"):
        raw_students = extract_names_from_pdf(file_bytes)
    elif filename.endswith(".xlsx") or filename.endswith(".xls"):
        names = extract_names_from_excel(file_bytes)
        raw_students = [{"name": n} for n in names]
    elif filename.endswith(".csv"):
        names = extract_names_from_csv(file_bytes)
        raw_students = [{"name": n} for n in names]
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use PDF, Excel (.xlsx) or CSV.")

    if not raw_students:
        raise HTTPException(status_code=400, detail="No names found in file. Check the format or the file may be empty.")

    # Get the current maximum admission number for this school to generate new ones
    # We'll query the highest existing admission number (assuming format like PREFIX0001)
    prefix = school_id[:4].upper()
    existing = db.table("students").select("admission_number").eq("school_id", school_id).order("admission_number", desc=True).limit(1).execute()
    max_num = 0
    if existing.data:
        last_adm = existing.data[0]["admission_number"]
        # Extract numeric part (last 4 digits)
        try:
            max_num = int(last_adm[-4:])
        except:
            max_num = 0

    # Prepare data for batch insert
    to_insert = []
    errors = []
    for idx, student in enumerate(raw_students):
        name = student["name"]
        admission_num = student.get("admission_number")
        if not admission_num:
            max_num += 1
            admission_num = f"{prefix}{max_num:04d}"
        access_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        to_insert.append({
            "school_id": school_id,
            "class_id": class_id,
            "name": name,
            "admission_number": admission_num,
            "access_code": access_code,
        })

    # Batch insert
    inserted = 0
    for i in range(0, len(to_insert), BATCH_SIZE):
        batch = to_insert[i:i + BATCH_SIZE]
        try:
            result = db.table("students").insert(batch).execute()
            inserted += len(result.data) if result.data else 0
        except Exception as e:
            # If batch fails, try one by one for this batch
            for student in batch:
                try:
                    db.table("students").insert(student).execute()
                    inserted += 1
                except Exception as single_err:
                    errors.append(f"{student['name']}: {str(single_err)}")

    if inserted == 0:
        return {"message": "No students were imported. See errors for details.", "count": 0, "errors": errors}

    return {"message": f"{inserted} students imported successfully", "count": inserted, "errors": errors}