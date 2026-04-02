"""LangGraph workflow assembly."""

import logging

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import WorkflowNodes
from app.graph.router import route_review
from app.graph.state import WorkflowState

logger = logging.getLogger(__name__)


def build_workflow(nodes: WorkflowNodes, checkpointer) -> object:
    """Compile the workflow graph with the configured checkpointer."""

    logger.debug("Compiling workflow graph")
    builder = StateGraph(WorkflowState)

    builder.add_node("ask", nodes.ask)
    builder.add_node("classify_question", nodes.classify_question)
    builder.add_node("retrieve_evidence", nodes.retrieve_evidence)
    builder.add_node("cross_reference_evidence", nodes.cross_reference_evidence)
    builder.add_node("draft_response", nodes.draft_response)
    builder.add_node("polish_response", nodes.polish_response)
    builder.add_node("human_review", nodes.human_review)
    builder.add_node("revise_response", nodes.revise_response)
    builder.add_node("finalize_response", nodes.finalize_response)

    builder.add_edge(START, "ask")
    builder.add_edge("ask", "classify_question")
    builder.add_edge("classify_question", "retrieve_evidence")
    builder.add_edge("retrieve_evidence", "cross_reference_evidence")
    builder.add_edge("cross_reference_evidence", "draft_response")
    builder.add_edge("draft_response", "polish_response")
    builder.add_edge("polish_response", "human_review")
    builder.add_conditional_edges(
        "human_review",
        route_review,
        {
            "approve": "finalize_response",
            "revise": "revise_response",
        },
    )
    builder.add_edge("revise_response", "polish_response")
    builder.add_edge("finalize_response", END)

    graph = builder.compile(checkpointer=checkpointer)
    logger.debug("Workflow graph compiled")
    return graph
