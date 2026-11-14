"""The Op a console request acts through; MCP tools build theirs in tool_support.op()."""

from __future__ import annotations

from datetime import UTC, datetime

from memorydock_core.audit.chain import truncate_ms
from memorydock_core.ops import Op
from memorydock_core.principal import Principal

from memorydock_gateway import state


def console_op(p: Principal) -> Op:
    runtime = state.current()
    return Op(
        client=runtime.client,
        db=runtime.db,
        pdp=runtime.policy.pdp,
        principal=p,
        via="console",
        now=truncate_ms(datetime.now(UTC)),
    )
