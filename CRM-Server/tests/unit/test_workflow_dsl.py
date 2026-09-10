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
