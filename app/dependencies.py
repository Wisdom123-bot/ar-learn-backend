from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.security import decode_token
from app.core.database import get_supabase

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Dependency that validates the JWT and returns the current teacher/user.
    """
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
        )
    
    db = get_supabase()
    # Fetch user data from database to ensure it still exists and role is correct
    result = db.table("teachers").select("*").eq("id", user_id).single().execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    return result.data

async def get_current_active_user(current_user: dict = Depends(get_current_user)):
    # You could add checks for is_active here if that column exists on teachers or schools
    return current_user

async def require_role(role: str):
    """
    Closure to require a specific role for a route.
    """
    async def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires {role} role",
            )
        return current_user
    return role_checker

async def require_admin_or_headteacher(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "headteacher", "dean"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return current_user
