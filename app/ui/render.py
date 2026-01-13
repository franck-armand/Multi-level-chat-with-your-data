from __future__ import annotations
import streamlit as st
import matplotlib.pyplot as plt

from edan.charts import make_chart_payload

def render_sql(sql: str):
    with st.expander("SQL used", expanded=False):
        st.code(sql, language="sql")

def render_table(df):
    st.dataframe(df, use_container_width=True)

def render_chart_from_plan(df, plan):
    payload = make_chart_payload(df, plan.chart_type, plan.x, plan.y, plan.title)

    if payload["type"] == "bar":
        st.subheader(payload["title"])
        st.bar_chart(payload["dataframe"].set_index(plan.x)[plan.y])

    elif payload["type"] == "hist":
        st.subheader(payload["title"])
        fig, ax = plt.subplots()
        ax.hist(payload["data"], bins=20)
        st.pyplot(fig)

    elif payload["type"] == "pie":
        st.subheader(payload["title"])
        fig, ax = plt.subplots()
        ax.pie(payload["values"], labels=payload["labels"], autopct="%1.1f%%")
        ax.axis("equal")
        st.pyplot(fig)
