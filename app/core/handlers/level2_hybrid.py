from __future__ import annotations
import streamlit as st

from ui.chat import init_chat_state, render_history
from edan.level2.graph import run_level2 as run_level2_graph


def run_level2(db_path: str, max_rows: int):
    init_chat_state()
    render_history()

    prompt = st.chat_input("Ask a question (Level 2: Hybrid SQL + RAG + citations)…")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        thinking = st.empty()
        thinking.markdown("...")

        state = run_level2_graph(prompt, db_path)

        thinking.empty()
        st.markdown(state.answer or "")
        
        # Render output
        if state.sql_rows:
            with st.expander("Table preview", expanded=True):
                import pandas as pd
                df = pd.DataFrame(state.sql_rows)
                st.dataframe(df.head(50), width="stretch", hide_index=True)

        if state.sql_used:
            with st.expander("SQL used", expanded=False):
                st.code(state.sql_used, language="sql")
                
        # Show trace for debugging/evaluation
        with st.expander("Debug trace", expanded=False):
            st.write("route:", state.route)
            if state.resolved:
                st.write("resolved:", state.resolved)
            if state.sql_used:
                st.code(state.sql_used, language="sql")
            if state.rag_hits:
                st.write("rag_hits:", [h.__dict__ for h in state.rag_hits])
        
        # with st.expander("Trace", expanded=False):
        #     st.json(state.trace.to_dict() if state.trace else {})
        
        st.session_state.messages.append({
            "role": "assistant",
            "content": state.answer or "",
            "sql": state.sql_used,
            "df": None,  # Level 2 outputs text + sources (not dataframe)
        })
