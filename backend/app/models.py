from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from database import Base

class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    account_id = Column(String, index=True, nullable=False)
    pattern_type = Column(String, nullable=False)
    cluster_id = Column(String, nullable=True)
    risk_score = Column(Float, nullable=False)
    risk_bucket = Column(String, nullable=False)
    evidence_summary = Column(Text, nullable=False)
    status = Column(String, default="open", nullable=False)  # "open", "reviewed_legitimate", "escalated"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "account_id": self.account_id,
            "pattern_type": self.pattern_type,
            "cluster_id": self.cluster_id,
            "risk_score": self.risk_score,
            "risk_bucket": self.risk_bucket,
            "evidence_summary": self.evidence_summary,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

class PayerEvent(Base):
    __tablename__ = "payer_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    payer_account_id = Column(String, nullable=False)
    payee_account_id = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    risk_score_at_time = Column(Float, nullable=True)
    risk_bucket_at_time = Column(String, nullable=True)
    user_action = Column(String, nullable=True)  # "proceeded_normally", "cancelled", "overrode_warning"

    def to_dict(self):
        return {
            "id": self.id,
            "payer_account_id": self.payer_account_id,
            "payee_account_id": self.payee_account_id,
            "amount": self.amount,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "risk_score_at_time": self.risk_score_at_time,
            "risk_bucket_at_time": self.risk_bucket_at_time,
            "user_action": self.user_action,
        }
