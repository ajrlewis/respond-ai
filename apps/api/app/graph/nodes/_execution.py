"""Shared execution wrapper for node observability/error handling."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.graph.state import WorkflowState


async def execute_node(
    *,
    nodes: Any,
    node_name: str,
    state: WorkflowState,
    operation: Callable[[], Awaitable[WorkflowState]],
    set_current_node: bool = True,
) -> WorkflowState:
    """Run a node operation with consistent observation/error semantics."""

    node_run_id, context_token = await nodes._start_node_observation(node_name, state)
    try:
        if set_current_node:
            await nodes._set_current_node(state.get("session_id"), node_name)
        output = await operation()
        await nodes._finish_node_observation(
            node_run_id=node_run_id,
            context_token=context_token,
            output_state=output,
            status="success",
        )
        await nodes._publish_session_update(
            output.get("session_id") or state.get("session_id"),
            reason="node_completed",
            node_name=str(output.get("current_node") or node_name),
            status=str(output.get("status")) if output.get("status") is not None else None,
        )
        return output
    except BaseException as exc:
        is_interrupt = nodes._is_human_wait_interrupt(exc)
        await nodes._finish_node_observation(
            node_run_id=node_run_id,
            context_token=context_token,
            output_state=state,
            status="waiting_for_human" if is_interrupt else "error",
            error_message=None if is_interrupt else str(exc),
        )
        await nodes._publish_session_update(
            state.get("session_id"),
            reason="waiting_for_human" if is_interrupt else "node_error",
            node_name=node_name,
            status="waiting_for_human" if is_interrupt else "error",
            error=None if is_interrupt else str(exc),
        )
        raise
