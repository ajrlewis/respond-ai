import inspect

from app.core.database import get_db
from app.graph.nodes import WorkflowNodes
from app.graph.runtime import resume_from_review, run_until_human_review
from app.graph.tools import expand_chunk_context, keyword_search, semantic_search
from app.routes.ask import ask_question, compare_drafts, get_draft, get_final_audit, get_session, get_session_by_thread_id, list_drafts
from app.routes.documents import list_documents
from app.routes.review import review_history, review_session
from app.services.retrieval import RetrievalService
from app.services.review_service import ReviewService
from app.services.session_service import SessionService


def test_async_api_and_graph_entrypoints() -> None:
    assert inspect.isasyncgenfunction(get_db)
    assert inspect.iscoroutinefunction(run_until_human_review)
    assert inspect.iscoroutinefunction(resume_from_review)

    assert inspect.iscoroutinefunction(ask_question)
    assert inspect.iscoroutinefunction(get_session)
    assert inspect.iscoroutinefunction(get_session_by_thread_id)
    assert inspect.iscoroutinefunction(list_drafts)
    assert inspect.iscoroutinefunction(get_draft)
    assert inspect.iscoroutinefunction(compare_drafts)
    assert inspect.iscoroutinefunction(get_final_audit)
    assert inspect.iscoroutinefunction(list_documents)
    assert inspect.iscoroutinefunction(review_session)
    assert inspect.iscoroutinefunction(review_history)


def test_async_graph_nodes_and_services() -> None:
    assert inspect.iscoroutinefunction(WorkflowNodes.ask)
    assert inspect.iscoroutinefunction(WorkflowNodes.classify_and_plan)
    assert inspect.iscoroutinefunction(WorkflowNodes.adaptive_retrieve)
    assert inspect.iscoroutinefunction(WorkflowNodes.evaluate_evidence)
    assert inspect.iscoroutinefunction(WorkflowNodes.classify_question)
    assert inspect.iscoroutinefunction(WorkflowNodes.retrieve_evidence)
    assert inspect.iscoroutinefunction(WorkflowNodes.cross_reference_evidence)
    assert inspect.iscoroutinefunction(WorkflowNodes.draft_response)
    assert inspect.iscoroutinefunction(WorkflowNodes.polish_response)
    assert inspect.iscoroutinefunction(WorkflowNodes.human_review)
    assert inspect.iscoroutinefunction(WorkflowNodes.revise_response)
    assert inspect.iscoroutinefunction(WorkflowNodes.finalize_response)

    assert inspect.iscoroutinefunction(semantic_search)
    assert inspect.iscoroutinefunction(keyword_search)
    assert inspect.iscoroutinefunction(expand_chunk_context)

    assert inspect.iscoroutinefunction(RetrievalService.semantic_search)
    assert inspect.iscoroutinefunction(RetrievalService.keyword_search)
    assert inspect.iscoroutinefunction(RetrievalService.expand_chunk_context)
    assert inspect.iscoroutinefunction(RetrievalService.hybrid_search)

    assert inspect.iscoroutinefunction(SessionService.get_session)
    assert inspect.iscoroutinefunction(SessionService.get_session_by_thread_id)
    assert inspect.iscoroutinefunction(SessionService.persist)
    assert inspect.iscoroutinefunction(SessionService.refresh)

    assert inspect.iscoroutinefunction(ReviewService.create_review)
    assert inspect.iscoroutinefunction(ReviewService.list_reviews)
