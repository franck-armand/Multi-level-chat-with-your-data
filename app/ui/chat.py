import streamlit as st

def init_chat_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []

def render_history():
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sql"):
                with st.expander("SQL used", expanded=False):
                    st.code(msg["sql"], language="sql")
            if msg.get("df") is not None:
                st.dataframe(msg["df"], use_container_width=True)
            if msg.get("chart") is not None:
                # chart is rendered in render.py; here just reserve
                pass
