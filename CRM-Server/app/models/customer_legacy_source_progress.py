"""Customer-scoped monotonic eligible-source progress, separate from display windows."""

from sqlalchemy import BigInteger, Column, ForeignKey, Index, String, UniqueConstraint

from app.core.database import Base


class CustomerLegacySourceProgress(Base):
    __tablename__ = "crm_customer_legacy_source_progress"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    team_id = Column(BigInteger, nullable=False)
    customer_id = Column(BigInteger, ForeignKey("crm_customers.id", ondelete="CASCADE"), nullable=False)
    policy_version = Column(String(40), nullable=False, default="LEGACY_PROFILE_ELIGIBLE_V1")
    eligible_revision = Column(BigInteger, nullable=False, default=0)
    deletion_revision = Column(BigInteger, nullable=False, default=0)
    provenance_status = Column(String(20), nullable=False, default="UNVERIFIED")

    __table_args__ = (
        UniqueConstraint("team_id", "customer_id", name="uq_customer_legacy_source_progress"),
        Index("idx_customer_legacy_progress_team_customer", "team_id", "customer_id"),
    )
