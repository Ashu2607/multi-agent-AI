"""Assembles the multi-agent LangGraph StateGraph:

        START -> supervisor -> (researcher | writer | human_approval | END)
                     ^                |          |            |
                     |________________|__________|            |
                                                                v
                                                               END

The Supervisor is the only node with conditional fan-out; every specialist
node returns control to the Supervisor so it can re-plan.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.human_approval import human_approval_node
from app.agents.researcher import researcher_node
from app.agents.supervisor import supervisor_node
from app.agents.writer import writer_node
from app.graph.state import GraphState
from app.schemas import RouteTarget


def _route_after_supervisor(state: GraphState) -> str:
    route = state.get("route")
    return route.value if route else RouteTarget.END.value


def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("writer", writer_node)
    graph.add_node("human_approval", human_approval_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        {
            RouteTarget.RESEARCHER.value: "researcher",
            RouteTarget.WRITER.value: "writer",
            RouteTarget.HUMAN_APPROVAL.value: "human_approval",
            RouteTarget.END.value: END,
        },
    )
    graph.add_edge("researcher", "supervisor")
    graph.add_edge("writer", "supervisor")
    graph.add_edge("human_approval", "supervisor")

    return graph.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
