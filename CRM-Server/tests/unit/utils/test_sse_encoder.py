"""SSEJsonEncoder 单测（迁自 langgraph/sse_wrapper.py，Encoder 逻辑保留）。

原 langgraph sse_wrapper 测试测的是已删的 build_*_event/filter_*/stream_sse_events
包装函数；SSEJsonEncoder 本身无既有用例，本文件为其新建单测。
"""
import json

import pytest
from langchain_core.messages import HumanMessage

from app.utils.sse_encoder import SSEJsonEncoder


def _encode(obj) -> str:
    return json.dumps(obj, cls=SSEJsonEncoder, ensure_ascii=False)


def test_encode_plain_dict_passthrough():
    """普通 dict 不触发 custom default，原样序列化。"""
    assert _encode({"a": 1, "b": "x"}) == '{"a": 1, "b": "x"}'


def test_encode_base_message_converts_to_dict():
    """BaseMessage 子类被转成 {type, content, additional_kwargs} dict。"""
    msg = HumanMessage(content="你好")
    result = json.loads(_encode({"msg": msg}))
    assert result["msg"]["content"] == "你好"
    assert result["msg"]["type"] == "human"
    assert "additional_kwargs" in result["msg"]


def test_encode_non_serializable_falls_back_to_default():
    """非 BaseMessage 的不可序列化对象走 json 默认行为（抛 TypeError）。"""
    with pytest.raises(TypeError):
        _encode({"obj": object()})


def test_encoder_is_json_encoder_subclass():
    """SSEJsonEncoder 必须是 json.JSONEncoder 子类（保持 SSE 兼容）。"""
    assert issubclass(SSEJsonEncoder, json.JSONEncoder)