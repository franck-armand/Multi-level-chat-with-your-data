from __future__ import annotations
from pathlib import Path
import streamlit as st

from edan.llm.config import get_llm_config

DEFAULT_DB = Path("data/edan.duckdb")

def setup_page():
    st.set_page_config(page_title="EDAN Chat", page_icon="", layout="wide")
    st.title("EDAN Chat")
    st.caption("Dataset-only answers (Level 1 SQL) + Hybrid RAG (Level 2).")

def sidebar_controls():
    st.sidebar.header("Settings")

    mode = st.sidebar.selectbox(
        "Mode",
        ["Level 1 (SQL)", "Level 2 (Hybrid SQL+RAG)"],
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

