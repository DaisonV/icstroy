from flask_login import current_user

from ..extensions import db
from ..models import AuditLog


def record_action(action, entity_type, entity_id=None, details=None):
    user_id = current_user.id if current_user.is_authenticated else None
    db.session.add(AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details,
    ))

