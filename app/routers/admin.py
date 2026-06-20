from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_supabase
from app.core.config import settings
from app.core.security import verify_password, hash_password
from app.services.rate_limit_service import list_banned_ips, unban_ip
from app.services.email_service import send_email
from app.services.audit_service import log_action
from datetime import datetime, timedelta
import os

router = APIRouter(prefix="/admin", tags=["super-admin"])

# Simple token-based auth for admin (we'll use a static admin token for now)
# In production, use JWT. For simplicity, we'll issue a token on login.
# We'll store the admin session in a simple dict (or use Supabase).
# For now, we'll just accept a bearer token that we generate on login (a random string).
# But that requires a sessions table. Instead, we can use a hardcoded admin API key from .env
# OR use a proper JWT. Given simplicity, we'll rely on a secret admin key for internal use.
# Let's implement a real login with bcrypt and a sessions table? No, to keep it minimal:
# We'll use a single admin API key from .env (ADMIN_API_KEY).
# The user can set it in .env and pass it in headers.

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "admin-secret-change-me")

def verify_admin(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    if credentials.credentials != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin credentials")
    return True

# Alternative: proper admin login using admins table (we can add later).
# For now, use the simple API key method.

# We'll provide both: a login endpoint that returns an admin token (simple random string)
# and also support the API key from env for direct access.

# Let's implement a proper login with bcrypt and the admins table.
# On first startup, if no admin exists, create a default one.
# The default password can be printed in console.

import random, string

def generate_admin_token() -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=32))

# Store active admin tokens in memory (simple)
admin_tokens = {}

class AdminLoginRequest(BaseModel):
    username: str
    password: str

class AdminLoginResponse(BaseModel):
    token: str

@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(payload: AdminLoginRequest):
    db = get_supabase()
    admin = db.table("admins").select("*").eq("username", payload.username).single().execute()
    if not admin.data:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(payload.password, admin.data["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = generate_admin_token()
    admin_tokens[token] = admin.data["id"]
    return {"token": token}

def verify_admin_token(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    token = credentials.credentials
    if token not in admin_tokens:
        # Also check if it matches the hardcoded API key (for easy dev)
        if token == ADMIN_API_KEY:
            return True
        raise HTTPException(status_code=403, detail="Invalid or expired admin token")
    return True

# --- School Management ---

from app.schemas.school import SchoolRegistrationResponse  # reuse maybe

# --- Subscription Management ---

@router.get("/subscriptions/pending")
async def list_pending_subscriptions(_: bool = Depends(verify_admin_token)):
    db = get_supabase()
    # Join with schools to show school name
    requests = db.table("subscription_requests").select(
        "*, schools(name, student_count)"
    ).eq("status", "pending").execute().data or []
    return requests

@router.post("/subscriptions/{request_id}/approve")
async def approve_subscription(request_id: str, _: bool = Depends(verify_admin_token)):
    db = get_supabase()
    
    # Get request details
    req = db.table("subscription_requests").select("*").eq("id", request_id).single().execute()
    if not req.data:
        raise HTTPException(status_code=404, detail="Request not found")
    
    school_id = req.data["school_id"]
    tier = req.data["requested_tier"]
    
    # Set expiry to 4 months from now
    expiry = (datetime.now() + timedelta(days=120)).isoformat()
    
    # Update school
    db.table("schools").update({
        "subscription_tier": tier,
        "subscription_expiry": expiry,
        "is_manual_override": False
    }).eq("id", school_id).execute()
    
    # Update request status
    db.table("subscription_requests").update({"status": "approved"}).eq("id", request_id).execute()
    
    # Check for student count discrepancy to calculate debt
    # If students increased since request, add the difference to debt
    school = db.table("schools").select("student_count, subscription_debt").eq("id", school_id).single().execute()
    current_students = school.data.get("student_count", 0)
    requested_students = req.data.get("student_count_at_request", 0)
    
    if current_students > requested_students:
        price_per_student = 10 if tier == "standard" else 17
        debt_incurred = (current_students - requested_students) * price_per_student * 4
        new_debt = school.data.get("subscription_debt", 0) + debt_incurred
        db.table("schools").update({"subscription_debt": new_debt}).eq("id", school_id).execute()
        
        log_action(
            school_id=school_id,
            action="DEBT_INCURRED",
            entity_type="school",
            entity_id=school_id,
            new_value={"debt": debt_incurred, "reason": "Student count increase during sub approval"}
        )

    log_action(
        school_id=school_id,
        action="SUBSCRIPTION_APPROVED",
        entity_type="subscription",
        entity_id=request_id,
        new_value={"tier": tier, "expiry": expiry}
    )
    
    return {"message": f"Subscription for {tier} approved until {expiry}"}

@router.post("/subscriptions/{request_id}/decline")
async def decline_subscription(request_id: str, _: bool = Depends(verify_admin_token)):
    db = get_supabase()
    db.table("subscription_requests").update({"status": "declined"}).eq("id", request_id).execute()
    return {"message": "Subscription request declined"}

@router.put("/schools/{school_id}/override")
async def manual_subscription_override(school_id: str, tier: str, active: bool, _: bool = Depends(verify_admin_token)):
    db = get_supabase()
    db.table("schools").update({
        "subscription_tier": tier,
        "is_manual_override": active,
        "subscription_expiry": (datetime.now() + timedelta(days=365)).isoformat() if active else None
    }).eq("id", school_id).execute()
    return {"message": f"Manual override set to {tier} (Active: {active})"}

@router.get("/schools")
async def list_all_schools(_: bool = Depends(verify_admin_token)):
    db = get_supabase()
    schools = db.table("schools").select("id, name, county, student_count, teacher_count, is_active, is_premium, email, phone, created_at").execute().data or []
    return schools

@router.put("/schools/{school_id}/suspend")
async def toggle_school_suspend(school_id: str, suspend: bool = True, _: bool = Depends(verify_admin_token)):
    db = get_supabase()
    result = db.table("schools").update({"is_active": not suspend}).eq("id", school_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="School not found")
    status = "suspended" if suspend else "reactivated"
    return {"message": f"School {status} successfully"}

@router.delete("/schools/{school_id}")
async def delete_school(school_id: str, _: bool = Depends(verify_admin_token)):
    db = get_supabase()
    # Check school exists
    school = db.table("schools").select("id, name").eq("id", school_id).single().execute()
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")
    school_name = school.data["name"]
    # Delete school (cascade will remove all related data due to ON DELETE CASCADE)
    db.table("schools").delete().eq("id", school_id).execute()
    return {"message": f"School '{school_name}' and all its data permanently deleted."}
@router.put("/schools/{school_id}/premium")
async def toggle_premium(school_id: str, premium: bool = True, _: bool = Depends(verify_admin_token)):
    db = get_supabase()
    result = db.table("schools").update({"is_premium": premium}).eq("id", school_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="School not found")
    status = "activated" if premium else "deactivated"
    return {"message": f"Premium features {status} for school"}
@router.get("/schools/{school_id}/details")
async def get_school_details(school_id: str, _: bool = Depends(verify_admin_token)):
    db = get_supabase()
    # Verify school exists
    school = db.table("schools").select("id, name").eq("id", school_id).single().execute()
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")

    # Get all teachers of this school
    teachers = db.table("teachers").select("id, name, teacher_code, role").eq("school_id", school_id).execute().data or []

    # Get all students with class names and access codes
    students = db.table("students").select("id, name, admission_number, access_code, classes(name)").eq("school_id", school_id).execute().data or []
    # Flatten class name
    for s in students:
        if s.get("classes"):
            s["class_name"] = s["classes"]["name"]
            del s["classes"]

    return {
        "school_name": school.data["name"],
        "teachers": teachers,
        "students": students,
    }
    
@router.post("/setup-default-admin")
async def setup_default_admin():
    """Run once to create default admin if none exists."""
    db = get_supabase()
    existing = db.table("admins").select("id").execute()
    if existing.data and len(existing.data) > 0:
        return {"message": "Admin already exists"}
    # Create default admin
    default_username = "admin"
    default_password = "admin123"  # change this immediately
    hashed = hash_password(default_password)
    db.table("admins").insert({"username": default_username, "password_hash": hashed}).execute()
    return {"message": f"Default admin created. Username: {default_username}, Password: {default_password} (change immediately!)"}

class BrandingUpdate(BaseModel):
    slug: Optional[str] = None
    logo_url: Optional[str] = None

@router.put("/schools/{school_id}/branding")
async def update_school_branding(school_id: str, payload: BrandingUpdate, _: bool = Depends(verify_admin_token)):
    db = get_supabase()
    data = {}
    if payload.slug is not None:
        data["slug"] = payload.slug
    if payload.logo_url is not None:
        data["logo_url"] = payload.logo_url
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    result = db.table("schools").update(data).eq("id", school_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="School not found")
    return {"message": "Branding updated", "school": result.data[0]}

class SendEmailRequest(BaseModel):
    to: str          # "all", "school:<school_id>", or a custom email address
    subject: str
    body: str

@router.post("/send-email")
async def admin_send_email(payload: SendEmailRequest, _: bool = Depends(verify_admin_token)):
    db = get_supabase()
    recipients = []

    if payload.to == "all":
        # Fetch all school emails (non‑null and non‑empty)
        schools = db.table("schools").select("email, name").not_.is_("email", "null").execute().data or []
        recipients = [(s["email"], s["name"]) for s in schools if s.get("email")]
    elif payload.to.startswith("school:"):
        school_id = payload.to.split(":", 1)[1]
        school = db.table("schools").select("email, name").eq("id", school_id).single().execute()
        if school.data and school.data.get("email"):
            recipients = [(school.data["email"], school.data["name"])]
    else:
        # Assume it's a direct email address
        recipients = [(payload.to, payload.to)]

    if not recipients:
        raise HTTPException(status_code=400, detail="No valid recipients found")

    sent_count = 0
    for email, name in recipients:
        # Personalize slightly
        body = f"Dear {name},\n\n{payload.body}\n\n-- Ar‑Learn Team"
        if send_email(email, payload.subject, body):
            sent_count += 1

    return {"message": f"Email sent to {sent_count} recipient(s)"}
@router.get("/banned-ips")
async def get_banned_ips(_: bool = Depends(verify_admin_token)):
    return list_banned_ips()

@router.delete("/banned-ips/{ip_address}")
async def unban_ip_address(ip_address: str, _: bool = Depends(verify_admin_token)):
    unban_ip(ip_address)
    return {"message": f"IP {ip_address} unbanned"}    
class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

@router.put("/change-password")
async def change_admin_password(
    payload: ChangePasswordRequest,
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    token = credentials.credentials
    admin_id = admin_tokens.get(token)
    if not admin_id:
        # also check if it matches API key (not usable for password change)
        raise HTTPException(status_code=403, detail="Invalid admin token")

    db = get_supabase()
    admin = db.table("admins").select("*").eq("id", admin_id).single().execute()
    if not admin.data:
        raise HTTPException(status_code=404, detail="Admin not found")

    # Verify old password
    if not verify_password(payload.old_password, admin.data["password_hash"]):
        raise HTTPException(status_code=400, detail="Old password is incorrect")

    # Hash new password and update
    new_hash = hash_password(payload.new_password)
    db.table("admins").update({"password_hash": new_hash}).eq("id", admin_id).execute()

    # Invalidate current token (remove it) so they must re-login with new password
    del admin_tokens[token]

    return {"message": "Password changed successfully. Please log in again."}
@router.get("/debug-login-attempts")
async def debug_login_attempts(_: bool = Depends(verify_admin_token)):
    db = get_supabase()
    result = db.table("login_attempts").select("*").execute()
    return {"raw_data": result.data, "count": len(result.data or [])}    