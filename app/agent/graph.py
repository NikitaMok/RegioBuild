from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agent import nodes
from app.agent.state import AgentState


@lru_cache
def build_agent_graph():
    """Граф: normalize → transform → retrieve → classify → rerank → LLM → format/guardrail."""
    graph = StateGraph(AgentState)

    graph.add_node("normalize_business_type", nodes.normalize_business_type)
    graph.add_node("understand_query", nodes.understand_query)
    graph.add_node("query_transform", nodes.query_transform)
    graph.add_node("retrieve_chunks", nodes.retrieve_chunks)
    graph.add_node("classify_requirements", nodes.classify_requirements)
    graph.add_node("rerank_retrieved", nodes.rerank_retrieved)
    graph.add_node("llm_compare_or_extract", nodes.llm_compare_or_extract)
    graph.add_node("format_response", nodes.format_response)

    graph.add_edge(START, "normalize_business_type")
    graph.add_edge("normalize_business_type", "understand_query")
    graph.add_edge("understand_query", "query_transform")
    graph.add_edge("query_transform", "retrieve_chunks")
    graph.add_edge("retrieve_chunks", "classify_requirements")
    graph.add_edge("classify_requirements", "rerank_retrieved")
    graph.add_edge("rerank_retrieved", "llm_compare_or_extract")
    graph.add_edge("llm_compare_or_extract", "format_response")
    graph.add_edge("format_response", END)

    return graph.compile()


def run_info_query(business_type: str, region_code: str) -> AgentState:
    initial_state: AgentState = {
        "mode": "info",
        "business_type": business_type,
        "region_a": region_code,
    }
    return build_agent_graph().invoke(initial_state)


def run_compare_query(business_type: str, region_a_code: str, region_b_code: str) -> AgentState:
    initial_state: AgentState = {
        "mode": "compare",
        "business_type": business_type,
        "region_a": region_a_code,
        "region_b": region_b_code,
    }
    return build_agent_graph().invoke(initial_state)
