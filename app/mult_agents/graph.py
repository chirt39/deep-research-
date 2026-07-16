"""工作流编排模块：定义 LangGraph 节点、条件路由与整体执行路径。"""

"""
 * 小滴课堂,愿景：让技术不再难学
 * @Remark 有问题联系我【xdclass68】
 * 源码-笔记-技术交流群,官网 https://xdclass.net
"""
import logging

from langgraph.graph import StateGraph, START, END

from .nodes import (
    bind_agent,
    intent_node,
    direct_answer_node,
    plan_node,
    web_search_node,
    local_rag_node,
    deep_dive_node,
    analyze_node,
    reflect_node,
    write_node,
)
from .state import ResearchState


logger = logging.getLogger("mult_agents")


def route_after_intent(state: ResearchState) -> str:
    if state.get("intent") == "direct":
        return "direct_answer"
    return "plan"


def should_continue_research(state: ResearchState) -> str:
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 2)
    
    # If we reached max iterations, stop and write report
    if iteration >= max_iter:
        return "write"
        
    # If analyst found missing gaps and requested more research, go to reflect
    if state.get("needs_more_research", False):
        return "reflect"
        
    # Otherwise, we have enough evidence, go to write report
    return "write"


def build_app(agents, checkpointer):
    workflow = StateGraph(ResearchState)
    workflow.add_node("intent", bind_agent(intent_node, agents.intent_router, "intent_router"))
    workflow.add_node("direct_answer", bind_agent(direct_answer_node, agents.direct_responder, "direct_responder"))
    workflow.add_node("plan", bind_agent(plan_node, agents.planner, "planner"))
    workflow.add_node("web_search", bind_agent(web_search_node, agents.scout_web, "scout_web"))
    workflow.add_node("local_rag", bind_agent(local_rag_node, agents.scout_local, "scout_local"))
    workflow.add_node("deep_dive", bind_agent(deep_dive_node, agents.evidence_judge, "evidence_judge"))
    workflow.add_node("analyze", bind_agent(analyze_node, agents.analyst, "analyst"))
    workflow.add_node("reflect", bind_agent(reflect_node, agents.planner, "planner"))
    workflow.add_node("write", bind_agent(write_node, agents.writer, "writer"))
    
    workflow.add_edge(START, "intent")
    workflow.add_conditional_edges(
        "intent",
        route_after_intent,
        {
            "direct_answer": "direct_answer",
            "plan": "plan",
        },
    )
    workflow.add_edge("plan", "web_search")
    workflow.add_edge("plan", "local_rag")
    workflow.add_edge("web_search", "deep_dive")
    workflow.add_edge("local_rag", "deep_dive")
    workflow.add_edge("deep_dive", "analyze")
    
    workflow.add_conditional_edges(
        "analyze",
        should_continue_research,
        {
            "reflect": "reflect",
            "write": "write"
        }
    )
    
    workflow.add_edge("reflect", "web_search")
    workflow.add_edge("reflect", "local_rag")
    workflow.add_edge("direct_answer", END)
    workflow.add_edge("write", END)
    
    return workflow.compile(checkpointer=checkpointer)
