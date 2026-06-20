import logging
import typing
from app.core.database import get_supabase

logger = logging.getLogger(__name__)

def log_action(
    school_id: str,
    action: str,
    actor_id: typing.Optional[str] = None,
    actor_name: typing.Optional[str] = None,
    entity_type: typing.Optional[str] = None,
    entity_id: typing.Optional[str] = None,
    old_value: typing.Any = None,
    new_value: typing.Any = None,
    ip_address: typing.Optional[str] = None
):
    """
    Logs an action to the audit_logs table and the system logger.
    """
    db = get_supabase()
    
    audit_data = {
        "school_id": school_id,
        "action": action,
        "actor_id": actor_id,
        "actor_name": actor_name,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "old_value": old_value,
        "new_value": new_value,
        "ip_address": ip_address
    }
    
    try:
        db.table("audit_logs").insert(audit_data).execute()
        logger.info(f"Audit: {action} by {actor_name} on {entity_type} {entity_id}")
    except Exception as e:
        logger.error(f"Failed to write audit log: {str(e)}")
