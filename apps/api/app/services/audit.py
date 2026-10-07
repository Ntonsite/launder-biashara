import json

from sqlalchemy.orm import Session

from ..models import AuditLog


def audit(db: Session, actor_id: str | None, action: str, entity: str, entity_id: str, **metadata) -> None:
    """Adds an audit row to the current transaction; the caller commits."""
    db.add(AuditLog(actor_id=actor_id, action=action, entity=entity, entity_id=entity_id,
                    metadata_json=json.dumps(metadata, default=str)))
