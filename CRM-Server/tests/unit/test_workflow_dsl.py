import pytest
from app.services.workflow_dsl import validate_workflow_dsl, KNOWN_NODE_TYPES

VALID = {
    "schema_version": 1,
    "nodes": [
        {"id": "n1", "type": "trigger.opportunity_stage_changed",
         "position": {"x": 0, "y": 0}, "config": {"to_stage": "QUOTE"}},
        {"id": "n2", "type": "action.create_follow_up_task",
         "position": {"x": 200, "y": 0}, "config": {"title": "跟进"}},
    ],
    "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
}

CRM_CONFIGS = {
    "crm.create_customer": {"account_name": "Acme", "city": "上海"},
    "crm.create_contact": {
        "customer_ref": "cust_1",
        "name": "张三",
        "gender": "男",
        "position": "采购负责人",
        "mobile": "13800000000",
    },
    "crm.create_opportunity": {
        "customer_ref": "cust_1",
        "total_amount": 100000,
        "user_count": 20,
        "license_type": "annual",
        "purchase_type": "new",
        "expected_closing_date": "2026-12-31",
        "product_public_id": "prd_crm",
        "product_module_public_ids": "prm_base",
    },
}


def _crm_dsl(nodes: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "nodes": [
            {"id": "trigger", "type": "trigger.opportunity_stage_changed",
             "position": {"x": 0, "y": 0}, "config": {"to_stage": "QUOTE"}},
            *nodes,
        ],
        "edges": [
            {"id": f"edge-{node['id']}", "source": "trigger", "target": node["id"]}
            for node in nodes
        ],
    }


def test_valid_dsl_with_each_crm_node_passes():
    nodes = [
        {"id": node_type, "type": node_type, "position": {"x": 100, "y": 100}, "config": config}
        for node_type, config in CRM_CONFIGS.items()
    ]

    assert validate_workflow_dsl(_crm_dsl(nodes)) == []


@pytest.mark.parametrize("node_type, missing_field", [
    ("crm.create_customer", "account_name"),
    ("crm.create_customer", "city"),
    ("crm.create_contact", "customer_ref"),
    ("crm.create_contact", "name"),
    ("crm.create_contact", "gender"),
    ("crm.create_contact", "position"),
    ("crm.create_contact", "mobile"),
    ("crm.create_opportunity", "customer_ref"),
    ("crm.create_opportunity", "total_amount"),
    ("crm.create_opportunity", "user_count"),
    ("crm.create_opportunity", "license_type"),
    ("crm.create_opportunity", "purchase_type"),
    ("crm.create_opportunity", "expected_closing_date"),
    ("crm.create_opportunity", "product_public_id"),
    ("crm.create_opportunity", "product_module_public_ids"),
])
def test_crm_node_missing_required_field_is_rejected(node_type, missing_field):
    config = {key: value for key, value in CRM_CONFIGS[node_type].items() if key != missing_field}
    node = {"id": "crm-node", "type": node_type, "position": {"x": 100, "y": 100}, "config": config}

    errors = validate_workflow_dsl(_crm_dsl([node]))

    assert any(missing_field in error for error in errors)


def test_valid_dsl_passes():
    assert validate_workflow_dsl(VALID) == []

def test_unknown_node_type():
    dsl = {**VALID, "nodes": [{**VALID["nodes"][0], "type": "action.unknown"}]}
    errs = validate_workflow_dsl(dsl)
    assert any("未知" in e for e in errs)

def test_duplicate_node_id():
    dsl = {**VALID, "nodes": [VALID["nodes"][0], dict(VALID["nodes"][0])]}
    assert any("唯一" in e or "重复" in e for e in validate_workflow_dsl(dsl))

def test_two_triggers_rejected():
    d2 = {**VALID["nodes"][1], "id": "n0", "type": "trigger.opportunity_stage_changed",
          "config": {"to_stage": "PROPOSAL"}}
    dsl = {**VALID, "nodes": [d2] + VALID["nodes"]}
    assert any("至多 1 个" in e or "trigger" in e for e in validate_workflow_dsl(dsl))

def test_dangling_edge_rejected():
    dsl = {**VALID, "edges": [{"id": "e2", "source": "n1", "target": "nx"}]}
    assert any("不存在" in e for e in validate_workflow_dsl(dsl))

def test_self_loop_rejected():
    dsl = {**VALID, "edges": [{"id": "e2", "source": "n1", "target": "n1"}]}
    assert any("自环" in e for e in validate_workflow_dsl(dsl))

def test_edge_into_trigger_rejected():
    dsl = {**VALID, "edges": [{"id": "e2", "source": "n2", "target": "n1"}]}
    assert any("trigger" in e for e in validate_workflow_dsl(dsl))

def test_missing_required_config():
    dsl = {**VALID, "nodes": [
        VALID["nodes"][0],
        {"id": "n2", "type": "action.create_follow_up_task",
         "position": {"x": 0, "y": 0}, "config": {}},
    ]}
    assert any("title" in e for e in validate_workflow_dsl(dsl))

def test_wrong_schema_version():
    assert validate_workflow_dsl({**VALID, "schema_version": 2}) != []
