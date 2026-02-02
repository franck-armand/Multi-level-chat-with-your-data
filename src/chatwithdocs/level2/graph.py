from __future__ import annotations
from pathlib import Path

from langgraph.graph import StateGraph, END

from chatwithdocs.level2.state import L2State
from chatwithdocs.level2.nodes import node_resolve, node_route, node_sql, node_rag, node_compose
from chatwithdocs.obs.trace import new_trace
from chatwithdocs.obs.sinks import JsonlTraceSink

def build_graph():
    g = StateGraph(L2State)

    g.add_node("resolve", node_resolve)
    g.add_node("route", node_route)
    g.add_node("sql", node_sql)
    g.add_node("rag", node_rag)
    g.add_node("compose", node_compose)

    g.set_entry_point("resolve")
    g.add_edge("resolve", "route")

    def choose_next(state: L2State) -> str:
        if state.route == "sql":
            return "sql"
        if state.route == "rag":
            return "rag"
        # blocked or unknown
        return "compose"

    g.add_conditional_edges("route", choose_next, {
        "sql": "sql",
        "rag": "rag",
        "compose": "compose",
    })

    g.add_edge("sql", "compose")
    g.add_edge("rag", "compose")
    g.add_edge("compose", END)

    return g.compile()


_GRAPH = build_graph()


def run_level2(user_query: str, db_path: str, trace_out: str | None = "logs/traces.jsonl") -> L2State:
    trace = new_trace({"level": 2, "query": user_query, "db": db_path})

    state = L2State(user_query=user_query, db_path=db_path, trace=trace)
    final_dict = _GRAPH.invoke(state)

    final_state = L2State(**final_dict)

    if final_state.trace is None:
        final_state.trace = trace

    final_state.trace.finish()

    if trace_out:
        JsonlTraceSink(Path(trace_out)).write(final_state.trace)

    return final_state