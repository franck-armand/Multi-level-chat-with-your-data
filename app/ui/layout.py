from __future__ import annotations
from pathlib import Path
import streamlit as st

DEFAULT_DB = Path("data/edan.duckdb")

def setup_page():
    st.set_page_config(page_title="EDAN Chat", page_icon="", layout="wide")
    st.title("EDAN Chat")
    st.caption("Dataset-only answers (Level 1 SQL). Later: Hybrid SQL+RAG.")

def sidebar_controls():
    st.sidebar.header("Settings")
    mode = st.sidebar.selectbox("Mode", ["Level 1 (SQL)"], index=0)
    db_path = st.sidebar.text_input("DuckDB path", value=str(DEFAULT_DB))
    max_rows = st.sidebar.slider("Max rows", 50, 1000, 200, 50)
    return mode, db_path, max_rows
