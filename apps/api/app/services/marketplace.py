from datetime import datetime,timezone
from sqlalchemy.orm import Session
from ..models import AuditLog,MarketplaceAccount,User
class MarketplaceAdminService:
    transitions={"approve":"ACTIVE","reject":"REJECTED","suspend":"SUSPENDED"}
    def __init__(self,db:Session):self.db=db
    def decide(self,account:MarketplaceAccount,decision:str,actor:User,reason:str|None):
        if decision not in self.transitions:raise ValueError("Invalid decision")
        account.status=self.transitions[decision];account.rejection_reason=reason if decision=="reject" else None;account.approved_at=datetime.now(timezone.utc) if decision=="approve" else None
        self.db.add(AuditLog(actor_id=actor.id,action=f"MARKETPLACE_{decision.upper()}",entity="marketplace_account",entity_id=account.id));self.db.commit();return account
