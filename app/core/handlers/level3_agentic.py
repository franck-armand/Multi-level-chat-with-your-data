from __future__ import annotations

from pathlib import Path
import streamlit as st

from ui.chat import init_chat_state, render_history
from edan.level3.graph import run_level3
from edan.level3.disambiguate import run_sql_for_choice, apply_choice_and_update_memory, memory_key_from_query
from edan.sql.exec import run_query
from edan.obs.trace import new_trace, trace_event
from edan.obs.sinks import JsonlTraceSink

def _execute_choice(db_path: str, max_rows: int, pending: dict, choice_obj):
    trace = new_trace({
        "level": 3,
        "phase": "selection",
        "db": db_path,
        "original_query": pending.get("user_query"),
    })

    # Trace: selection
    with trace_event(trace, "l3.selection", {
        "choice_key": getattr(choice_obj, "key", None),
        "label": getattr(choice_obj, "label", None),
        "payload": getattr(choice_obj, "payload", None),
    }):
        pass

    # Remember selection (session memory)
    with trace_event(trace, "l3.memory.write", {}):
        st.session_state.l3_memory = apply_choice_and_update_memory(
            pending["user_query"], choice_obj, st.session_state.l3_memory
        )

    # Build SQL from the selected payload
    with trace_event(trace, "l3.choice.to_sql", {"mode": choice_obj.payload.get("mode")}):
        sql, narrative = run_sql_for_choice(Path(db_path), choice_obj.payload)

    msg = {"role": "assistant", "content": narrative}

    # Execute SQL (this will trace validate/execute/result via run_query(trace=...))
    if sql and sql.strip():
        df, final_sql = run_query(Path(db_path), sql, limit=max_rows, trace=trace)
        msg["sql"] = final_sql
        msg["df"] = df.head(50)

    # Finish + write trace to JSONL
    trace.finish()
    JsonlTraceSink(Path("logs/traces.jsonl")).write(trace)

    # Write message to chat history
    st.session_state.messages.append(msg)

    # Clear pending
    st.session_state.l3_pending = None


def run_level3_agentic(db_path: str, max_rows: int):
    init_chat_state()
    render_history()

    if "l3_memory" not in st.session_state:
        st.session_state.l3_memory = {}

    if "l3_pending" not in st.session_state:
        st.session_state.l3_pending = None

    pending = st.session_state.l3_pending

    # -----------------------------------------
    # PENDING MODE: show buttons, block chat
    # -----------------------------------------
    if pending is not None:
        with st.chat_message("assistant"):
            question_text = pending["question"].split('\n')[0] 
            st.markdown(f"**{question_text}**")

            st.caption("Please select one of the following:")
            
            # Show options as buttons
            for i, c in enumerate(pending["choices"], start=1):
                if st.button(f"{c.label}", key=f"l3_choice_{i}", width="stretch"):
                    _execute_choice(db_path, max_rows, pending, c)
                    st.rerun()

            # Action Bar
            st.divider()
            cols = st.columns([1, 1, 2])
            if cols[0].button("Cancel", key="l3_cancel"):
                st.session_state.l3_pending = None
                st.rerun()
            if cols[1].button("Reset", key="l3_reset"):
                st.rerun()
        
        st.stop()

    # -----------------------------------------
    # NORMAL MODE: accept a new question
    # -----------------------------------------
    prompt = st.chat_input("Ask a question (Level 3: clarifies ambiguity)…")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Memory shortcut: if we already resolved this mention, auto-run
    k = memory_key_from_query(prompt)
    if k and k in st.session_state.l3_memory:
        payload = st.session_state.l3_memory[k]
        sql, narrative = run_sql_for_choice(Path(db_path), payload)

        msg = {"role": "assistant", "content": narrative}
        if sql and sql.strip():
            df, final_sql = run_query(Path(db_path), sql, limit=max_rows)
            msg["sql"] = final_sql
            msg["df"] = df.head(50)

        st.session_state.messages.append(msg)
        st.rerun()
        return

    # Run Level 3 graph
    with st.chat_message("assistant"):
        thinking = st.empty()
        thinking.markdown("...")

        state = run_level3(prompt, db_path, st.session_state.l3_memory)

        thinking.empty()
        st.markdown(state.answer or "")

    if state.pending:
        st.session_state.l3_pending = {
            "user_query": prompt,
            "question": state.answer or "Please choose one option:",
            "choices": state.choices,
        }

        st.rerun()
        return

    st.session_state.messages.append({"role": "assistant", "content": state.answer or ""})
