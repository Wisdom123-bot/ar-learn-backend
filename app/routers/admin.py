from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_supabase
from app.core.config import settings
from app.core.security import verify_password, hash_password
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

@router.get("/schools")
async def list_all_schools(_: bool = Depends(verify_admin_token)):
    db = get_supabase()
    schools = db.table("schools").select("id, name, county, student_count, teacher_count, is_active, created_at").execute().data or []
    return schools

@router.put("/schools/{school_id}/suspend")
async def toggle_school_suspend(school_id: str, suspend: bool = True, _: bool = Depends(verify_admin_token)):
    db = get_supabase()
    result = db.table("schools").update({"is_active": not suspend}).eq("id", school_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="School not found")
    status = "suspended" if not suspend else "reactivated"
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