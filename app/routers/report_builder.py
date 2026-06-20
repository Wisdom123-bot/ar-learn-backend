from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from app.core.database import get_supabase

router = APIRouter(prefix="/report-builder", tags=["report-builder"])


class TemplateCreate(BaseModel):
    name: str
    logo_url: Optional[str] = ""
    motto: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    primary_color: str = "#1e3a8a"
    secondary_color: str = "#f0f4ff"
    show_attendance: bool = True
    show_fee_status: bool = True
    show_teacher_remarks: bool = True
    show_overall_evaluation: bool = True


class TemplateResponse(BaseModel):
    id: UUID
    name: str
    logo_url: str
    motto: str
    phone: str
    email: str
    primary_color: str
    secondary_color: str
    show_attendance: bool
    show_fee_status: bool
    show_teacher_remarks: bool
    show_overall_evaluation: bool
    created_at: str
    updated_at: str


@router.get("/{school_id}", response_model=list[TemplateResponse])
async def list_templates(school_id: str):
    db = get_supabase()
    templates = db.table("report_templates").select("*").eq("school_id", school_id).order("created_at", desc=True).execute()
    return [
        TemplateResponse(
            id=t["id"],
            name=t["name"],
            logo_url=t.get("logo_url", ""),
            motto=t.get("motto", ""),
            phone=t.get("phone", ""),
            email=t.get("email", ""),
            primary_color=t.get("primary_color", "#1e3a8a"),
            secondary_color=t.get("secondary_color", "#f0f4ff"),
            show_attendance=t.get("show_attendance", True),
            show_fee_status=t.get("show_fee_status", True),
            show_teacher_remarks=t.get("show_teacher_remarks", True),
            show_overall_evaluation=t.get("show_overall_evaluation", True),
            created_at=str(t["created_at"]),
            updated_at=str(t["updated_at"]),
        ) for t in (templates.data or [])
    ]


@router.post("/{school_id}", response_model=TemplateResponse)
async def create_template(school_id: str, payload: TemplateCreate):
    db = get_supabase()
    # Check school exists
    school = db.table("schools").select("id").eq("id", school_id).execute()
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")

    data = {
        "school_id": school_id,
        "name": payload.name,
        "logo_url": payload.logo_url or "",
        "motto": payload.motto or "",
        "phone": payload.phone or "",
        "email": payload.email or "",
        "primary_color": payload.primary_color,
        "secondary_color": payload.secondary_color,
        "show_attendance": payload.show_attendance,
        "show_fee_status": payload.show_fee_status,
        "show_teacher_remarks": payload.show_teacher_remarks,
        "show_overall_evaluation": payload.show_overall_evaluation,
    }
    result = db.table("report_templates").insert(data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create template")
    t = result.data[0]
    return TemplateResponse(
        id=t["id"],
        name=t["name"],
        logo_url=t.get("logo_url", ""),
        motto=t.get("motto", ""),
        phone=t.get("phone", ""),
        email=t.get("email", ""),
        primary_color=t.get("primary_color", "#1e3a8a"),
        secondary_color=t.get("secondary_color", "#f0f4ff"),
        show_attendance=t.get("show_attendance", True),
        show_fee_status=t.get("show_fee_status", True),
        show_teacher_remarks=t.get("show_teacher_remarks", True),
        show_overall_evaluation=t.get("show_overall_evaluation", True),
        created_at=str(t["created_at"]),
        updated_at=str(t["updated_at"]),
    )


@router.put("/{school_id}/{template_id}", response_model=TemplateResponse)
async def update_template(school_id: str, template_id: str, payload: TemplateCreate):
    db = get_supabase()
    existing = db.table("report_templates").select("*").eq("id", template_id).eq("school_id", school_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Template not found")

    data = {
        "name": payload.name,
        "logo_url": payload.logo_url or "",
        "motto": payload.motto or "",
        "phone": payload.phone or "",
        "email": payload.email or "",
        "primary_color": payload.primary_color,
        "secondary_color": payload.secondary_color,
        "show_attendance": payload.show_attendance,
        "show_fee_status": payload.show_fee_status,
        "show_teacher_remarks": payload.show_teacher_remarks,
        "show_overall_evaluation": payload.show_overall_evaluation,
        "updated_at": "now()",
    }
    db.table("report_templates").update(data).eq("id", template_id).execute()
    # Fetch updated
    updated = db.table("report_templates").select("*").eq("id", template_id).single().execute().data
    return TemplateResponse(
        id=updated["id"],
        name=updated["name"],
        logo_url=updated.get("logo_url", ""),
        motto=updated.get("motto", ""),
        phone=updated.get("phone", ""),
        email=updated.get("email", ""),
        primary_color=updated.get("primary_color", "#1e3a8a"),
        secondary_color=updated.get("secondary_color", "#f0f4ff"),
        show_attendance=updated.get("show_attendance", True),
        show_fee_status=updated.get("show_fee_status", True),
        show_teacher_remarks=updated.get("show_teacher_remarks", True),
        show_overall_evaluation=updated.get("show_overall_evaluation", True),
        created_at=str(updated["created_at"]),
        updated_at=str(updated["updated_at"]),
    )


@router.delete("/{school_id}/{template_id}")
async def delete_template(school_id: str, template_id: str):
    db = get_supabase()
    db.table("report_templates").delete().eq("id", template_id).eq("school_id", school_id).execute()
    return {"message": "Template deleted"}