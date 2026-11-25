# ruff: noqa: RUF001, RUF002 -- Chinese user-facing copy uses native punctuation.
"""商机输单的共享约束文案。

页面阻断、Assistant 阻断和 CRUD 拒绝必须使用同一句原因，
否则同一条规则会在三处漂移。
"""

CONTRACT_LOSS_BLOCK_REASON = "该商机已有合同，请先处理合同后再标记输单"
