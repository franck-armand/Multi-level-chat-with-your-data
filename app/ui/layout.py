from __future__ import annotations
from pathlib import Path
import streamlit as st

from edan.llm.config import get_llm_config

DEFAULT_DB = Path("data/edan.duckdb")

def setup_page():
    st.set_page_config(page_title="Chat with your data (EDAN 2025)", page_icon="🗳️", layout="wide")
    st.title("Chat with your data")
    st.caption("Ask questions about the EDAN 2025 election results dataset.")

def sidebar_controls():
    st.sidebar.header("Settings")

    mode = st.sidebar.selectbox(
        "Mode",
        [
        "Level 1 (SQL)",
        "Level 2 (Hybrid SQL+RAG)",
        "Level 3 (Agentic: clarify/disambiguate)"
        ],
        index=0
    )

    db_path = st.sidebar.text_input("DuckDB path", value=str(DEFAULT_DB))
    max_rows = st.sidebar.slider("Max rows", 50, 1000, 200, 50)

    st.sidebar.header("LLM Enhancer")
    cfg = get_llm_config()
    if cfg.enabled:
        st.sidebar.success(f"Enabled: {cfg.provider} / {cfg.model}")
    else:
        st.sidebar.warning(f"Disabled: {cfg.reason}")

    return mode, db_path, max_rows

