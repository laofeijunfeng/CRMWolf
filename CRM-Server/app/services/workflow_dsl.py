"""CRMWolf Workflow DSL 结构校验（schema_version 1）。"""

NODE_CONFIG_REQUIREMENTS: dict[str, list[str]] = {
    "trigger.opportunity_stage_changed": ["to_stage"],
    "approval.step": ["node_name", "approve_role"],
    "control.condition": ["field", "operator", "value"],
    "action.create_follow_up_task": ["title"],
    "action.notify": ["notify_target"],
    "crm.create_customer": ["account_name", "city", "product_public_id"],
    "crm.create_contact": ["customer_ref", "name", "gender", "position", "mobile"],
    "crm.create_opportunity": [
        "customer_ref", "total_amount", "user_count", "license_type",
        "purchase_type", "expected_closing_date",
        "product_public_id", "product_module_public_ids",
    ],
}
KNOWN_NODE_TYPES = frozenset(NODE_CONFIG_REQUIREMENTS)
TRIGGER_TYPES = frozenset(t for t in KNOWN_NODE_TYPES if t.startswith("trigger."))
VALID_OPERATORS = frozenset({"eq", "neq", "gt", "lt", "in"})
VALID_NOTIFY_TARGETS = frozenset({"owner", "role", "users"})


def validate_workflow_dsl(dsl: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(dsl, dict):
        return ["DSL 必须是对象"]
    if dsl.get("schema_version") != 1:
        errors.append("schema_version 必须为 1")

    nodes = dsl.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return errors + ["nodes 必须是非空列表"]

    seen_ids: set[str] = set()
    trigger_count = 0
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"nodes[{i}] 必须是对象")
            continue
        nid = node.get("id")
        if not isinstance(nid, str) or not nid:
            errors.append(f"nodes[{i}].id 必须是非空字符串")
        elif nid in seen_ids:
            errors.append(f"节点 id 重复: {nid}")
        else:
            seen_ids.add(nid)

        ntype = node.get("type")
        is_known_type = isinstance(ntype, str) and ntype in KNOWN_NODE_TYPES
        if not is_known_type:
            errors.append(f"节点 {nid} 类型未知: {ntype}")
        if isinstance(ntype, str) and ntype in TRIGGER_TYPES:
            trigger_count += 1

        pos = node.get("position")
        if not isinstance(pos, dict) or not isinstance(pos.get("x"), (int, float)) \
                or not isinstance(pos.get("y"), (int, float)):
            errors.append(f"节点 {nid} 缺少有效 position")

        config = node.get("config", {})
        if not isinstance(config, dict):
            config = {}
            errors.append(f"节点 {nid} config 必须是对象")
        for field in NODE_CONFIG_REQUIREMENTS.get(ntype, []) if is_known_type else []:
            v = config.get(field)
            if v is None or (isinstance(v, str) and not v.strip()):
                errors.append(f"节点 {nid} 缺少必填配置: {field}")
        if ntype == "control.condition" and (
            not isinstance(config.get("operator"), str) or config.get("operator") not in VALID_OPERATORS
        ):
            errors.append("节点 {0} operator 非法，允许: eq/neq/gt/lt/in".format(nid))
        if ntype == "action.notify" and (
            not isinstance(config.get("notify_target"), str)
            or config.get("notify_target") not in VALID_NOTIFY_TARGETS
        ):
            errors.append("节点 {0} notify_target 非法，允许: owner/role/users".format(nid))

    if trigger_count > 1:
        errors.append("trigger 类型节点全图至多 1 个")

    edges = dsl.get("edges", [])
    if not isinstance(edges, list):
        edges = []
        errors.append("edges 必须是列表")
    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"edges[{i}] 必须是对象")
            continue
        src, tgt = edge.get("source"), edge.get("target")
        tgt_type = next((n.get("type") for n in nodes if isinstance(n, dict) and n.get("id") == tgt), None)
        valid_endpoints = isinstance(src, str) and isinstance(tgt, str)
        if not valid_endpoints or src not in seen_ids or tgt not in seen_ids:
            errors.append(f"edges[{i}] 引用了不存在的节点: {src} -> {tgt}")
            continue
        if src == tgt:
            errors.append(f"edges[{i}] 不允许自环")
        if isinstance(tgt_type, str) and tgt_type in TRIGGER_TYPES:
            errors.append(f"edges[{i}] 目标不能是 trigger 节点: {tgt}")

    return errors
