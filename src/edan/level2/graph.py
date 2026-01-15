from __future__ import annotations

from langgraph.graph import StateGraph, END

from edan.level2.state import L2State
from edan.level2.nodes import node_resolve, node_route, node_sql, node_rag, node_compose


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


def run_level2(user_query: str, db_path: str) -> L2State:
    state = L2State(user_query=user_query, db_path=db_path)
    final_dict = _GRAPH.invoke(state)
    return L2State(**final_dict)