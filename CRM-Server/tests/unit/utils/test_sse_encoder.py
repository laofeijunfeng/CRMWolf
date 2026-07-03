"""SSEJsonEncoder 单测。

对齐 1a57897 后的 Encoder 语义：不依赖 langchain_core，
用 hasattr(obj, 'isoformat') 处理 datetime，其余不可序列化对象 str() 兜底。
"""
import json
from datetime import datetime

from app.utils.sse_encoder import SSEJsonEncoder


def _encode(obj) -> str:
    return json.dumps(obj, cls=SSEJsonEncoder, ensure_ascii=False)


def test_encode_plain_dict_passthrough():
    """普通 dict 不触发 custom default，原样序列化。"""
    assert _encode({"a": 1, "b": "x"}) == '{"a": 1, "b": "x"}'


def test_encode_datetime_converts_to_isoformat():
    """datetime 对象被转成 isoformat 字符串。"""
    dt = datetime(2026, 7, 2, 19, 40, 0)
    result = json.loads(_encode({"ts": dt}))
    assert result["ts"] == "2026-07-02T19:40:00"


def test_encode_non_serializable_falls_back_to_str():
    """不可序列化对象走 str() 兜底（不再抛 TypeError）。"""
    class Opaque:
        def __str__(self):
            return "opaque-str"
    result = json.loads(_encode({"obj": Opaque()}))
    assert result["obj"] == "opaque-str"


def test_encoder_is_json_encoder_subclass():
    """SSEJsonEncoder 必须是 json.JSONEncoder 子类（保持 SSE 兼容）。"""
    assert issubclass(SSEJsonEncoder, json.JSONEncoder)
