from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.contract import Contract
from app.models.customer import Contact, Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_fact import CustomerFact, CustomerFactRevision, CustomerFactSource
from app.models.industry import Industry
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan, PaymentRecord
from app.services.customer_brief_service import CustomerBriefService
from app.services.customer_fact_service import CustomerFactInput, CustomerFactSourceInput, customer_fact_service
from app.services.customer_intelligence_context_service import CustomerIntelligenceContextService
from app.services.customer_profile_service import CustomerProfileService
from app.services.customer_qdrant_index_service import CustomerEvidenceSearchResult, SourceType


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


class FakeEmbeddingService:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_query(self, db: Session, team_id: int, text: str) -> list[float]:
        self.queries.append(text)
        assert team_id == 2
        return [0.1, 0.2, 0.3]


class FailingEmbeddingService:
    def embed_query(self, db: Session, team_id: int, text: str) -> list[float]:
        raise RuntimeError("embedding failed")


class FakeQdrantIndexService:
    enabled = True

    def __init__(self) -> None:
        self.searches: list[tuple[int, int, int, list[float], int, tuple[SourceType, ...] | None]] = []

    def search_customer_evidence(
        self,
        query_vector: list[float],
        tenant_id: int,
        team_id: int,
        customer_id: int,
        limit: int = 8,
        source_types: tuple[SourceType, ...] | None = None,
        business_object_type: str | None = None,
    ) -> list[CustomerEvidenceSearchResult]:
        assert business_object_type is None
        self.searches.append((tenant_id, team_id, customer_id, query_vector, limit, source_types))
        return [
            CustomerEvidenceSearchResult(
                id="evidence-1",
                score=0.91,
                tenant_id=tenant_id,
                team_id=team_id,
                customer_id=customer_id,
                source_type="follow_up",
                source_object_id="9001",
                business_object_type="customer_activity",
                business_object_id="9001",
                title="电话跟进",
                text="张总确认本周开始 POC。",
            )
        ]


class LowScoreQdrantIndexService(FakeQdrantIndexService):
    def search_customer_evidence(
        self,
        query_vector: list[float],
        tenant_id: int,
        team_id: int,
        customer_id: int,
        limit: int = 8,
        source_types: tuple[SourceType, ...] | None = None,
        business_object_type: str | None = None,
    ) -> list[CustomerEvidenceSearchResult]:
        self.searches.append((tenant_id, team_id, customer_id, query_vector, limit, source_types))
        return [
            CustomerEvidenceSearchResult(
                id="weak-evidence",
                score=0.21,
                tenant_id=tenant_id,
                team_id=team_id,
                customer_id=customer_id,
                source_type="follow_up",
                source_object_id="9002",
                business_object_type="customer_activity",
                business_object_id="9002",
                title="弱相关跟进",
                text="客户提到另一个不相关项目。",
            )
        ]


def _session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            Contact.__table__,
            Opportunity.__table__,
            Contract.__table__,
            PaymentPlan.__table__,
            PaymentRecord.__table__,
            CustomerActivity.__table__,
            CustomerFact.__table__,
            CustomerFactSource.__table__,
            CustomerFactRevision.__table__,
            Industry.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine)
    return engine, session_factory()


def _seed_industries(db: Session) -> None:
    government = Industry(id=1, level=1, code="government", name="政府", sort_order=1, is_active=1)
    public = Industry(
        id=2,
        level=2,
        parent_id=1,
        code="government_public",
        name="公共机构",
        sort_order=1,
        is_active=1,
    )
    db.add_all([government, public])
    db.flush()


def _seed_customer_context(db: Session) -> Customer:
    customer = Customer(
        id=101,
        team_id=2,
        account_name="越秀金融",
        industry="金融",
        city="广州",
        company_scale="1000人以上",
        source="客户推荐",
        creator_id="9",
        profile_status="COMPLETED",
        company_background="地方金融控股集团。",
        main_business="金融控股与投资管理。",
        project_background="希望规范合同和采购流程。",
        customer_brief_status="COMPLETED",
        customer_brief_markdown="## 客户概况\n客户正在推进 POC，并关注合同与采购流程规范。",
    )
    db.add(customer)
    db.flush()
    db.add(
        Contact(
            id=201,
            team_id=2,
            customer_id=101,
            name="张总",
            position="采购负责人",
            is_primary=1,
            is_decision_maker=1,
            mobile="13800000000",
        )
    )
    db.add(
        Opportunity(
            id=301,
            team_id=2,
            opportunity_number="OPP202608030001",
            opportunity_name="越秀金融采购项目",
            customer_id=101,
            current_stage_name="POC",
            current_win_probability=60,
            total_amount=Decimal("120000.00"),
            user_count=120,
            unit_price=Decimal("1000.00"),
            license_type="SUBSCRIPTION",
            subscription_years=1,
            purchase_type="NEW",
            expected_closing_date=date(2026, 12, 31),
            owner_id="9",
            creator_id="9",
            status=0,
            approval_phase="approved",
        )
    )
    db.add(
        Contract(
            id=401,
            team_id=2,
            contract_number="HT-001",
            contract_name="越秀金融合同",
            customer_id=101,
            opportunity_id=301,
            user_count=120,
            total_amount=Decimal("120000.00"),
            license_type="SUBSCRIPTION",
            subscription_years=1,
            standard_unit_price=Decimal("1000.00"),
            owner_id="9",
            creator_id="9",
            status="SIGNED",
            payment_status="PARTIAL",
            signing_date=date(2026, 8, 1),
        )
    )
    db.add(
        PaymentPlan(
            id=501,
            team_id=2,
            contract_id=401,
            plan_number="P-001",
            stage_name="首付款",
            planned_amount=Decimal("60000.00"),
            due_date=date(2026, 8, 15),
            status="PENDING",
        )
    )
    db.add(
        PaymentRecord(
            id=601,
            team_id=2,
            record_number="R-001",
            payment_plan_id=501,
            actual_amount=Decimal("30000.00"),
            payment_date=date(2026, 8, 20),
            creator_id="9",
            confirmation_status="CONFIRMED",
            approval_phase="approved",
        )
    )
    db.add(
        CustomerActivity(
            id=701,
            team_id=2,
            customer_id=101,
            activity_kind="PHONE_FOLLOW_UP",
            title="电话跟进",
            source_content="张总说本周开始 POC。",
            summary="客户进入 POC。",
            next_action="准备试用环境",
            occurred_at=datetime(2026, 8, 2, 10, 0, 0),
            creator_id="9",
            owner_id="9",
        )
    )
    customer_fact_service.upsert_fact(
        db,
        CustomerFactInput(
            tenant_id=2,
            team_id=2,
            customer_id=101,
            fact_type="need",
            subject="试用",
            content="客户已经进入 POC，需要准备试用环境。",
            confidence=0.91,
            source=CustomerFactSourceInput(
                source_type="customer_activity",
                source_object_id="701",
                business_object_type="customer_activity",
                business_object_id="701",
                evidence_id="evidence-1",
            ),
        ),
    )
    db.commit()
    return customer


def test_customer_intelligence_context_combines_strong_facts_and_semantic_evidence() -> None:
    engine, db = _session()
    embedding_service = FakeEmbeddingService()
    qdrant_index_service = FakeQdrantIndexService()
    service = CustomerIntelligenceContextService(
        embedding_service=embedding_service,
        qdrant_index_service=qdrant_index_service,
    )
    try:
        _seed_customer_context(db)

        context = service.build_context(
            db,
            team_id=2,
            customer_id=101,
            query_text="张总说今天开始 POC",
        )
        payload = context.to_agent_payload()

        assert payload["strong_context"]["customer"]["account_name"] == "越秀金融"
        assert payload["strong_context"]["customer"]["company_background"] == "地方金融控股集团。"
        assert payload["strong_context"]["customer"]["main_business"] == "金融控股与投资管理。"
        assert payload["strong_context"]["customer"]["project_background"] == "希望规范合同和采购流程。"
        assert payload["strong_context"]["customer"]["customer_brief_markdown"] == (
            "## 客户概况\n客户正在推进 POC，并关注合同与采购流程规范。"
        )
        assert payload["strong_context"]["customer_facts"][0]["content"] == "客户已经进入 POC，需要准备试用环境。"
        assert payload["strong_context"]["opportunities"][0]["stage"] == "POC"
        assert payload["strong_context"]["payment_records"][0]["actual_amount"] == "30000.00"
        assert payload["semantic_evidence"][0]["text"] == "张总确认本周开始 POC。"
        assert payload["retrieval"]["status"] == "ok"
        assert payload["retrieval"]["returned_count"] == 1
        assert payload["retrieval"]["top_score"] == 0.91
        assert payload["retrieval"]["min_score"] == 0.45
        assert payload["citations"][0]["evidence_id"] == "evidence-1"
        assert payload["usage_policy"]["memory_source"] == "langgraph_store"
        assert payload["usage_policy"]["grounding"]["ok"] == "可基于 citations 输出 grounded 回答。"
        assert embedding_service.queries == ["张总说今天开始 POC"]
        assert qdrant_index_service.searches[0][:4] == (2, 2, 101, [0.1, 0.2, 0.3])
    finally:
        db.close()
        engine.dispose()


def test_customer_intelligence_context_keeps_strong_facts_when_evidence_retrieval_fails() -> None:
    engine, db = _session()
    service = CustomerIntelligenceContextService(
        embedding_service=FailingEmbeddingService(),
        qdrant_index_service=FakeQdrantIndexService(),
    )
    try:
        _seed_customer_context(db)

        context = service.build_context(
            db,
            team_id=2,
            customer_id=101,
            query_text="查一下客户 POC 进展",
        )
        payload = context.to_agent_payload()

        assert payload["strong_context"]["customer"]["account_name"] == "越秀金融"
        assert payload["semantic_evidence"] == []
        assert payload["retrieval"]["status"] == "failed"
        assert payload["retrieval"]["enabled"] is True
    finally:
        db.close()
        engine.dispose()


def test_customer_intelligence_context_marks_low_confidence_evidence() -> None:
    engine, db = _session()
    service = CustomerIntelligenceContextService(
        embedding_service=FakeEmbeddingService(),
        qdrant_index_service=LowScoreQdrantIndexService(),
    )
    try:
        _seed_customer_context(db)

        context = service.build_context(
            db,
            team_id=2,
            customer_id=101,
            query_text="查一下客户 POC 进展",
        )
        payload = context.to_agent_payload()

        assert payload["semantic_evidence"] == []
        assert payload["citations"] == []
        assert payload["retrieval"]["status"] == "low_confidence"
        assert payload["usage_policy"]["grounding"]["low_confidence"].startswith("只能基于 strong_context")
        assert payload["retrieval"]["raw_count"] == 1
        assert payload["retrieval"]["returned_count"] == 0
        assert payload["retrieval"]["dropped_count"] == 1
        assert payload["retrieval"]["top_score"] == 0.21
    finally:
        db.close()
        engine.dispose()


def test_customer_brief_context_uses_unified_customer_intelligence(monkeypatch) -> None:
    engine, db = _session()
    embedding_service = FakeEmbeddingService()
    qdrant_index_service = FakeQdrantIndexService()
    intelligence_service = CustomerIntelligenceContextService(
        embedding_service=embedding_service,
        qdrant_index_service=qdrant_index_service,
    )
    monkeypatch.setattr(
        "app.services.customer_brief_service.customer_intelligence_context_service",
        intelligence_service,
    )
    try:
        customer = _seed_customer_context(db)
        db.add(
            Customer(
                id=102,
                team_id=2,
                account_name="同业客户",
                industry="金融",
                city="广州",
                creator_id="9",
            )
        )
        db.commit()

        context = CustomerBriefService()._build_context(db, customer, team_id=2)

        assert context["context_source"] == "customer_intelligence"
        assert context["customer"]["account_name"] == "越秀金融"
        assert context["opportunities"][0]["stage"] == "POC"
        assert context["payment_records"][0]["actual_amount"] == 30000.0
        assert context["semantic_evidence"][0]["text"] == "张总确认本周开始 POC。"
        assert context["same_industry_customers"] == ["同业客户"]
        assert embedding_service.queries == [CustomerBriefService.BRIEF_RETRIEVAL_QUERY]
    finally:
        db.close()
        engine.dispose()


def test_customer_brief_context_resolves_industry_code_for_user_facing_output(monkeypatch) -> None:
    engine, db = _session()
    embedding_service = FakeEmbeddingService()
    qdrant_index_service = FakeQdrantIndexService()
    intelligence_service = CustomerIntelligenceContextService(
        embedding_service=embedding_service,
        qdrant_index_service=qdrant_index_service,
    )
    monkeypatch.setattr(
        "app.services.customer_brief_service.customer_intelligence_context_service",
        intelligence_service,
    )
    try:
        _seed_industries(db)
        customer = Customer(
            id=901,
            team_id=2,
            account_name="广州公共服务中心",
            industry="government_public",
            city="广州",
            creator_id="9",
        )
        peer = Customer(
            id=902,
            team_id=2,
            account_name="同业公共客户",
            industry="government_public",
            city="广州",
            creator_id="9",
        )
        db.add_all([customer, peer])
        db.commit()

        context = CustomerBriefService()._build_context(db, customer, team_id=2)
        brief = CustomerBriefService()._normalize_brief({"overview": {}, "opportunity_summaries": []}, context)
        markdown = CustomerBriefService()._render_markdown(brief)

        assert context["customer"]["industry_code"] == "government_public"
        assert context["customer"]["industry_name"] == "政府/公共机构"
        assert "### 同行业客户" in markdown
        assert "政府/公共机构" in markdown
        assert "同业公共客户" in markdown
        assert "government_public" not in markdown
    finally:
        db.close()
        engine.dispose()


def test_customer_profile_prompt_uses_unified_customer_intelligence() -> None:
    engine, db = _session()
    service = CustomerIntelligenceContextService(
        embedding_service=FakeEmbeddingService(),
        qdrant_index_service=FakeQdrantIndexService(),
    )
    try:
        _seed_customer_context(db)
        intelligence_context = service.build_context(
            db,
            team_id=2,
            customer_id=101,
            query_text=CustomerProfileService.PROFILE_RETRIEVAL_QUERY,
        )

        prompt = CustomerProfileService()._build_prompt_for_profile(
            "越秀金融",
            "finance",
            {"finance": {"name": "金融", "children": []}},
            ["同业客户"],
            None,
            intelligence_context,
        )

        assert "CRM 统一客户智能上下文" in prompt
        assert "越秀金融采购项目" in prompt
        assert "张总确认本周开始 POC。" in prompt
        assert "业务字段以结构化事实为准" in prompt
    finally:
        db.close()
        engine.dispose()
