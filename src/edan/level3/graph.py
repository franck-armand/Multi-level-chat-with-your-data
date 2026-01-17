from __future__ import annotations

from pathlib import Path
from langgraph.graph import StateGraph, END

from edan.level3.state import L3State
from edan.level3.disambiguate import propose_choices
from edan.level2.graph import run_level2
from edan.obs.trace import new_trace
from edan.obs.sinks import JsonlTraceSink
from edan.obs.trace import trace_event


def node_check_ambiguity(state: L3State) -> L3State:
    if state.trace:
        with trace_event(state.trace, "l3.ambiguity.check", {"query": state.user_query}):
            needs, question, choices = propose_choices(state.user_query, Path(state.db_path), state.memory)
    else:
        needs, question, choices = propose_choices(state.user_query, Path(state.db_path), state.memory)

    if needs:
        state.pending = True
        state.clarify_question = question
        state.choices = choices

        lines = [question, ""]
        for i, c in enumerate(choices, start=1):
            lines.append(f"{i}) {c.label}")
        state.answer = "\n".join(lines)

        if state.trace:
            with trace_event(state.trace, "l3.ambiguity.triggered", {
                "question": question,
                "num_choices": len(choices),
                "choices": [{"key": c.key, "label": c.label} for c in choices],
            }):
                pass

    else:
        if state.trace:
            with trace_event(state.trace, "l3.ambiguity.not_triggered", {}):
                pass

    return state


def node_delegate_level2(state: L3State) -> L3State:
    # If ambiguous, stop here
    if state.pending:
        return state
    # Otherwise reuse Level 2 full pipeline
    st2 = run_level2(state.user_query, state.db_path)
    state.answer = st2.answer
    return state


def build_graph():
    g = StateGraph(L3State)
    g.add_node("ambiguity", node_check_ambiguity)
    g.add_node("level2", node_delegate_level2)

    g.set_entry_point("ambiguity")
    g.add_edge("ambiguity", "level2")
    g.add_edge("level2", END)

    return g.compile()


_GRAPH = build_graph()


def run_level3(user_query: str, db_path: str, memory: dict, trace_out: str | None = "logs/traces.jsonl") -> L3State:
    trace = new_trace({"level": 3, "query": user_query, "db": db_path})

    state = L3State(user_query=user_query, db_path=db_path, memory=memory, trace=trace)
    final_dict = _GRAPH.invoke(state)
    final_state = L3State(**final_dict)

    if final_state.trace is None:
        final_state.trace = trace

    final_state.trace.finish()

    if trace_out:
        JsonlTraceSink(Path(trace_out)).write(final_state.trace)

    return final_state
