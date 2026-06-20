from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.security import decode_token
from app.core.database import get_supabase
import datetime

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
    db = get_supabase()
    school_id = current_user["school_id"]
    
    school = db.table("schools").select("is_active, subscription_tier, subscription_expiry, is_manual_override").eq("id", school_id).single().execute()
    if not school.data or not school.data.get("is_active", True):
         raise HTTPException(status_code=403, detail="Account suspended or school not found")

    # Inject subscription info into user object
    is_active = False
    if school.data["is_manual_override"]:
        is_active = True
    elif school.data["subscription_expiry"]:
        expiry = datetime.datetime.fromisoformat(school.data["subscription_expiry"].replace('Z', '+00:00'))
        if expiry > datetime.datetime.now(expiry.tzinfo):
            is_active = True
    
    current_user["subscription_tier"] = school.data["subscription_tier"] if is_active else "basic"
    return current_user

async def require_tier(required_tier: str):
    """
    Dependency to require a specific subscription tier.
    Tiers: basic < standard < elite
    """
    tier_hierarchy = {"basic": 0, "standard": 1, "elite": 2}
    
    async def tier_checker(current_user: dict = Depends(get_current_active_user)):
        user_tier = current_user.get("subscription_tier", "basic")
        if tier_hierarchy.get(user_tier, 0) < tier_hierarchy.get(required_tier, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail=f"This feature requires {required_tier.capitalize()} subscription."
            )
        return current_user
    return tier_checker

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
