from __future__ import annotations
from pathlib import Path
import streamlit as st

from edan.agent.agent import plan_question, looks_malicious
from edan.sql.exec import run_query

from ui.chat import init_chat_state, render_history
from ui.render import render_sql, render_table, render_chart_from_plan

def run_level1(db_path: str, max_rows: int):
    init_chat_state()
    render_history()

    prompt = st.chat_input("Ask: seats by party, top candidates, participation rate, winners by party…")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        thinking = st.empty()
        thinking.markdown("...")

        if looks_malicious(prompt):
            thinking.empty()
            msg = "I can't help with destructive/exfiltration requests. Ask an analytics question about the dataset."
            st.markdown(msg)
            st.session_state.messages.append({"role": "assistant", "content": msg})
            return

        plan = plan_question(prompt)
        if not plan:
            thinking.empty()
            msg = (
                "**Not found in the provided PDF dataset.**\n\n"
                "Try: seats by party, top candidates in a region, participation rate by region, winners by party."
            )
            st.markdown(msg)
            st.session_state.messages.append({"role": "assistant", "content": msg})
            return

        try:
            df, final_sql = run_query(Path(db_path), plan.sql, limit=max_rows)
        except Exception as e:
            thinking.empty()
            msg = f"Query failed safely.\n\n**Reason:** `{e}`"
            st.markdown(msg)
            st.session_state.messages.append({"role": "assistant", "content": msg})
            return

        thinking.empty()
        st.markdown(plan.narrative or "Here's what I found:")
        render_sql(final_sql)

        if plan.intent == "chart":
            render_chart_from_plan(df, plan)

        render_table(df.head(200))

        st.session_state.messages.append({
            "role": "assistant",
            "content": plan.narrative or "Here's what I found:",
            "sql": final_sql,
            "df": df.head(200),
        })
