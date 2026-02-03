"""
Streamlit Application - Enhanced Version

A modern chat interface for ChatWithDocs system with dark mode support,
LLM configuration wizard, and better debugging.

Features:
- Document upload and management
- Chat with citations
- Conversation history
- Real-time indexing
- LLM configuration wizard
- Dark mode support
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import streamlit as st

# Import chatwithdocs modules BEFORE streamlit
from chatwithdocs.chat import MessageRole
from chatwithdocs.chat.engine import ChatEngine
from chatwithdocs.chat.manager import ConversationManager
from chatwithdocs.config import settings
from chatwithdocs.config.manager import ConfigManager
from chatwithdocs.ingestion import IngestionPipeline
from chatwithdocs.security import PromptInjectionDetector

# Page configuration must be first after imports
st.set_page_config(
    page_title="ChatWithDocs - AI Document Assistant",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state
if "user_id" not in st.session_state:
    st.session_state.user_id = f"user_{uuid.uuid4().hex[:8]}"

if "current_thread_id" not in st.session_state:
    st.session_state.current_thread_id = None

if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []

if "llm_configured" not in st.session_state:
    st.session_state.llm_configured = False

if "show_llm_setup" not in st.session_state:
    st.session_state.show_llm_setup = False

if "debug_mode" not in st.session_state:
    st.session_state.debug_mode = False


# Initialize services with versioning to force refresh on code updates
@st.cache_resource
def get_services(version: str = "3"):
    """Initialize and cache services.

    Args:
        version: Increment to force cache refresh
    """
    return {
        "chat_engine": ChatEngine(),
        "conversation_manager": ConversationManager(),
        "ingestion_pipeline": IngestionPipeline(),
        "injection_detector": PromptInjectionDetector(),
    }


services = get_services()
chat_engine = services["chat_engine"]
conversation_manager = services["conversation_manager"]
ingestion_pipeline = services["ingestion_pipeline"]
injection_detector = services["injection_detector"]

# Initialize config manager
config_manager = ConfigManager()

# Get current configuration
current_config = config_manager.get_current_config()
provider_name = current_config["provider"].upper()
current_model = current_config["model"] or "fallback"
llm_available = current_config["llm_available"]
connection_error = current_config.get("error")

# Dark mode compatible CSS - uses Streamlit's theme colors
st.markdown(
    """
<style>
    /* Main header - uses theme colors */
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #FF4B4B;
        margin-bottom: 0.5rem;
    }
    .subheader {
        font-size: 1.1rem;
        color: rgba(49, 51, 63, 0.8);
        margin-bottom: 2rem;
    }
    
    /* Citation box - theme aware */
    .citation-box {
        background-color: rgba(255, 75, 75, 0.1);
        border-left: 3px solid #FF4B4B;
        padding: 0.75rem;
        margin: 0.5rem 0;
        font-size: 0.9rem;
        border-radius: 0 0.25rem 0.25rem 0;
    }
    
    /* Chat messages - use theme-aware colors */
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .user-message {
        background-color: rgba(255, 75, 75, 0.15);
        border-left: 3px solid #FF4B4B;
    }
    .assistant-message {
        background-color: rgba(128, 128, 128, 0.15);
        border-left: 3px solid #00C853;
    }

    /* File cards - theme aware */
    .file-card {
        background-color: rgba(128, 128, 128, 0.15);
        border: 1px solid rgba(128, 128, 128, 0.3);
        border-radius: 0.5rem;
        padding: 0.75rem;
        margin: 0.5rem 0;
    }

    /* Warning banner - theme aware */
    .warning-banner {
        background-color: rgba(255, 152, 0, 0.2);
        border-left: 4px solid #FF9800;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 0 0.25rem 0.25rem 0;
    }

    /* Success banner - theme aware */
    .success-banner {
        background-color: rgba(76, 175, 80, 0.2);
        border-left: 4px solid #4CAF50;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 0 0.25rem 0.25rem 0;
    }

    /* Info box - theme aware */
    .info-box {
        background-color: rgba(28, 131, 225, 0.2);
        border-left: 4px solid #1C83E1;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 0 0.25rem 0.25rem 0;
    }

    /* LLM status badge - theme aware */
    .llm-status {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 1rem;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .llm-active {
        background-color: rgba(76, 175, 80, 0.3);
        color: inherit;
    }
    .llm-inactive {
        background-color: rgba(244, 67, 54, 0.3);
        color: inherit;
    }
    /* Theme-aware text color for secondary text */
    .text-secondary {
        color: rgba(128, 128, 128, 0.8);
    }
</style>
""",
    unsafe_allow_html=True,
)


# Sidebar
with st.sidebar:
    # Title section
    st.markdown('<div class="main-header">ChatWithDocs</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subheader">Chat with your documents using AI</div>',
        unsafe_allow_html=True,
    )

    # LLM Status Section - Show Current Configuration
    st.subheader("AI Model Status")

    # Display current active configuration
    if llm_available:
        st.markdown(
            f'<span class="llm-status llm-active">[ACTIVE] {provider_name} Active</span>',
            unsafe_allow_html=True,
        )
        st.caption(f"Model: {current_model}")
    else:
        st.markdown(
            '<span class="llm-status llm-inactive">[!] Not Connected</span>',
            unsafe_allow_html=True,
        )
        if connection_error:
            st.caption(f"Error: {connection_error}")
        else:
            st.caption(f"Current: {provider_name} | Model: {current_model}")

    # Always show configure option
    st.session_state.show_llm_setup = st.checkbox(
        "Configure / Switch AI Model",
        value=st.session_state.show_llm_setup,
    )

    st.divider()

    # LLM Configuration Wizard
    if st.session_state.show_llm_setup:
        st.subheader("AI Configuration")

        # Show current config summary
        st.info(f"**Currently Active:** {provider_name} with {current_model}")

        provider = st.selectbox(
            "Select AI Provider",
            ["Kimi (Moonshot AI)", "OpenAI", "DeepSeek", "Ollama (Local - Free)"],
            help="Choose your AI model provider",
        )

        if provider == "Kimi (Moonshot AI)":
            st.info("Tip: Kimi K2.5 is a capable Chinese LLM. Get API key at platform.moonshot.cn")

            col1, col2 = st.columns(2)
            with col1:
                api_key = st.text_input(
                    "Kimi API Key",
                    type="password",
                    value=settings.kimi_api_key or "",
                    help="Your Kimi API key",
                    key="kimi_key",
                )
            with col2:
                model = st.selectbox(
                    "Model",
                    ["kimi-k2.5", "kimi-k1.5"],
                    index=0,
                    key="kimi_model",
                )

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Test Connection", key="test_kimi"):
                    with st.spinner("Testing..."):
                        success, msg = config_manager.test_connection(
                            "kimi", api_key=api_key, model=model
                        )
                        if success:
                            st.success(f"[OK] {msg}")
                        else:
                            st.error(f"[X] {msg}")
            with col2:
                if api_key and st.button("Save & Activate", type="primary", key="save_kimi"):
                    if config_manager.save_config("kimi", api_key=api_key, model=model):
                        st.success("Configuration saved to .env file!")
                        st.info("Please restart the app to activate the new configuration.")
                        st.balloons()
                    else:
                        st.error("Failed to save configuration")

        elif provider == "OpenAI":
            st.info("Tip: OpenAI offers reliable GPT models. Get API key at openai.com")

            col1, col2 = st.columns(2)
            with col1:
                api_key = st.text_input(
                    "OpenAI API Key",
                    type="password",
                    value=settings.openai_api_key or "",
                    help="Your OpenAI API key (sk-...)",
                    key="openai_key",
                )
            with col2:
                model = st.selectbox(
                    "Model",
                    ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
                    index=0,
                    key="openai_model",
                )

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Test Connection", key="test_openai"):
                    with st.spinner("Testing..."):
                        success, msg = config_manager.test_connection(
                            "openai", api_key=api_key, model=model
                        )
                        if success:
                            st.success(f"[OK] {msg}")
                        else:
                            st.error(f"[X] {msg}")
            with col2:
                if api_key and st.button("Save & Activate", type="primary", key="save_openai"):
                    if config_manager.save_config("openai", api_key=api_key, model=model):
                        st.success("Configuration saved to .env file!")
                        st.info("Please restart the app to activate the new configuration.")
                    else:
                        st.error("Failed to save configuration")

        elif provider == "DeepSeek":
            st.info("Tip: DeepSeek offers affordable, capable models. Get API key at deepseek.com")

            api_key = st.text_input(
                "DeepSeek API Key",
                type="password",
                value=settings.openai_api_key or "",
                help="Your DeepSeek API key",
                key="deepseek_key",
            )

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Test Connection", key="test_deepseek"):
                    with st.spinner("Testing..."):
                        success, msg = config_manager.test_connection("deepseek", api_key=api_key)
                        if success:
                            st.success(f"[OK] {msg}")
                        else:
                            st.error(f"[X] {msg}")
            with col2:
                if api_key and st.button("Save & Activate", type="primary", key="save_deepseek"):
                    if config_manager.save_config("deepseek", api_key=api_key):
                        st.success("Configuration saved to .env file!")
                        st.info("Please restart the app to activate the new configuration.")
                    else:
                        st.error("Failed to save configuration")

        elif provider == "Ollama (Local - Free)":
            st.info("Tip: Ollama runs locally for FREE. Install from ollama.com")

            # Check Ollama status using config manager
            with st.spinner("Checking Ollama..."):
                ollama_models = config_manager.load_available_ollama_models()
                ollama_running = len(ollama_models) > 0

            if ollama_running:
                st.success(f"[OK] Ollama is running with {len(ollama_models)} model(s)!")

                if ollama_models:
                    st.write("**Currently installed:**")
                    cols = st.columns(min(3, len(ollama_models)))
                    for i, model in enumerate(ollama_models[:6]):
                        with cols[i % 3]:
                            st.caption(f"• {model}")

                # Model selection - show both installed and recommended
                st.write("**Select or switch model:**")

                # Combine installed models with recommended ones
                from chatwithdocs.llm.client import OllamaLLMClient

                recommended = dict(OllamaLLMClient.RECOMMENDED_MODELS)

                # Create options: installed models first, then recommended
                all_options = []
                for model in ollama_models:
                    clean_name = model.replace(":latest", "")
                    if clean_name not in all_options:
                        all_options.append(clean_name)

                for model in recommended.keys():
                    if model not in all_options:
                        all_options.append(model)

                selected_model = st.selectbox(
                    "Choose Model",
                    all_options,
                    format_func=lambda x: f"[INSTALLED] {x}"
                    if x in [m.replace(":latest", "") for m in ollama_models]
                    else f"[DOWNLOAD] {x} (not installed)",
                    help="Select a model. [INSTALLED] = installed, [DOWNLOAD] = needs download",
                    key="ollama_model_select",
                )

                col1, col2 = st.columns(2)
                with col1:
                    if selected_model:
                        is_installed = any(selected_model in m for m in ollama_models)
                        if is_installed:
                            if st.button("Save & Activate", type="primary", key="save_ollama"):
                                if config_manager.save_config("ollama", model=selected_model):
                                    st.success(f"[OK] Ollama with {selected_model} saved!")
                                    st.info("Please restart the app to activate.")
                                else:
                                    st.error("Failed to save configuration")
                        else:
                            st.warning(f"[!] {selected_model} not installed")
                            st.code(f"ollama pull {selected_model}", language="bash")

                with col2:
                    if st.button("Refresh Model List", key="refresh_ollama"):
                        st.rerun()

            else:
                st.error("[X] Ollama not running or no models installed")
                st.code("ollama serve", language="bash")
                st.caption("Run this in terminal to start Ollama")

                st.code("ollama pull llama3.2", language="bash")
                st.caption("Then pull a model (in another terminal)")

            with st.expander("Setup Instructions"):
                st.markdown("""
                **Step 1: Install Ollama**
                ```bash
                # macOS/Linux
                curl -fsSL https://ollama.com/install.sh | sh
                # Or download from ollama.com
                ```

                **Step 2: Start Ollama Server**
                ```bash
                ollama serve
                ```

                **Step 3: Pull Models** (in another terminal)
                ```bash
                # Fast & good (3B params) - RECOMMENDED
                ollama pull llama3.2

                # Better quality (7B params)
                ollama pull mistral

                # Multilingual expert
                ollama pull qwen2.5
                ```

                **Step 4: Return here and select your model**
                """)

        st.divider()

    # Debug mode toggle
    st.session_state.debug_mode = st.checkbox("Debug Mode", value=st.session_state.debug_mode)

    if st.session_state.debug_mode:
        st.subheader("Debug Info")
        st.json(
            {
                "user_id": st.session_state.user_id,
                "current_thread": st.session_state.current_thread_id,
                "llm_provider": settings.llm_provider,
                "llm_available": llm_available,
                "uploaded_files": len(st.session_state.uploaded_files),
            }
        )

    st.divider()

    # File upload section
    st.subheader("Upload Documents")

    uploaded_files = st.file_uploader(
        "Drop files here",
        type=["pdf", "docx", "csv", "xlsx", "txt", "md"],
        accept_multiple_files=True,
        key="file_uploader",
        help="Upload documents to chat with them",
    )

    if uploaded_files:
        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, uploaded_file in enumerate(uploaded_files):
            status_text.text(f"Processing {uploaded_file.name}...")

            # Save to temp location
            temp_path = Path("/tmp") / uploaded_file.name
            temp_path.write_bytes(uploaded_file.getvalue())

            # Check if already processed
            if uploaded_file.name not in [f["name"] for f in st.session_state.uploaded_files]:
                # Process through ingestion pipeline
                result = asyncio.run(
                    ingestion_pipeline.ingest_file(temp_path, st.session_state.user_id)
                )

                if result["success"]:
                    st.session_state.uploaded_files.append(
                        {
                            "name": uploaded_file.name,
                            "chunks": result["chunks_indexed"],
                            "path": result["file_path"],
                        }
                    )
                    st.success(
                        f"[OK] {uploaded_file.name}: {result['chunks_indexed']} chunks indexed"
                    )
                else:
                    st.error(f"[X] {uploaded_file.name}: {result['error']}")

            progress_bar.progress((idx + 1) / len(uploaded_files))

        progress_bar.empty()
        status_text.empty()

    # Show uploaded files - compact display with expander
    if st.session_state.uploaded_files:
        file_count = len(st.session_state.uploaded_files)
        with st.expander(f"Your Documents ({file_count} files)", expanded=file_count <= 5):
            # Show first 5 files, then "+ X more" indicator
            display_files = st.session_state.uploaded_files[:5]
            for file_info in display_files:
                with st.container():
                    st.markdown(
                        f"""
                        <div class="file-card">
                            <strong>{file_info["name"]}</strong><br/>
                            <small class="text-secondary">{file_info["chunks"]} chunks indexed</small>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            if file_count > 5:
                st.caption(f"+ {file_count - 5} more file(s)...")

    # Danger zone - Clear all data
    st.divider()
    with st.expander("Danger Zone: Clear My Data"):
        st.warning("This will permanently delete all your conversations and uploaded documents!")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Clear Conversations Only", use_container_width=True):
                conversations = conversation_manager.list_conversations(st.session_state.user_id)
                deleted = 0
                for conv in conversations:
                    if conversation_manager.delete_conversation(
                        conv["id"], st.session_state.user_id
                    ):
                        deleted += 1
                st.session_state.current_thread_id = None
                st.success(f"[OK] Deleted {deleted} conversations")
                st.rerun()

        with col2:
            if st.button("Clear Everything", type="primary", use_container_width=True):
                try:
                    # Delete all user data
                    result = asyncio.run(chat_engine.delete_all_user_data(st.session_state.user_id))
                    st.session_state.uploaded_files = []
                    st.session_state.current_thread_id = None
                    st.success(
                        f"[OK] Deleted {result['conversations_deleted']} conversations and "
                        f"{result['document_chunks_deleted']} document chunks"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"[X] Error clearing data: {e}")
                    if st.session_state.debug_mode:
                        st.exception(e)

    # Conversation list
    st.divider()
    st.subheader("Conversations")

    conversations = conversation_manager.list_conversations(st.session_state.user_id)

    if conversations:
        for conv in conversations:
            col1, col2 = st.columns([4, 1])
            with col1:
                title = conv["title"] or "Untitled Chat"
                if st.button(
                    f"{title}",
                    key=f"conv_{conv['id']}",
                    use_container_width=True,
                    type="secondary"
                    if conv["id"] != st.session_state.current_thread_id
                    else "primary",
                ):
                    st.session_state.current_thread_id = conv["id"]
                    st.rerun()
            with col2:
                if st.button("X", key=f"del_{conv['id']}", help="Delete conversation"):
                    conversation_manager.delete_conversation(conv["id"], st.session_state.user_id)
                    if st.session_state.current_thread_id == conv["id"]:
                        st.session_state.current_thread_id = None
                    st.rerun()

    # New conversation button
    if st.button("New Conversation", use_container_width=True, type="primary"):
        thread = conversation_manager.create_thread(st.session_state.user_id, title="New Chat")
        st.session_state.current_thread_id = thread.id
        st.rerun()

# Main chat area
st.markdown('<div class="main-header">Chat</div>', unsafe_allow_html=True)

# Show LLM warning if not configured
if not llm_available and not st.session_state.show_llm_setup:
    st.markdown(
        """
        <div class="warning-banner">
            <strong>[!] AI Model Not Configured</strong><br/>
            You're in <strong>Fallback Mode</strong> with limited responses.<br/>
            For best results, configure an AI model in the sidebar.<br/>
            <strong>Recommended:</strong> Kimi K2.5 (free credits available)
        </div>
        """,
        unsafe_allow_html=True,
    )

if not st.session_state.current_thread_id:
    # Welcome screen
    st.info("Welcome! Upload documents and start chatting with AI.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("What You Can Do")
        st.markdown("""
        - Upload PDFs, Word docs, CSVs, text files
        - Ask questions about your documents
        - Get AI responses with source citations
        - Have multiple conversation threads
        """)

    with col2:
        st.subheader("AI Models Supported")
        st.markdown("""
        - **Kimi K2.5** - Best quality (Recommended)
        - **OpenAI GPT-4** - Reliable, fast
        - **DeepSeek** - Open source alternative
        - **Ollama** - Run locally for privacy
        """)

    st.divider()
    st.caption("Tip: Click 'Configure AI Model' in the sidebar to set up your AI")

else:
    # Load current thread
    thread = conversation_manager.get_thread(st.session_state.current_thread_id)

    if thread:
        # Display chat history
        for msg in thread.messages:
            if msg.role == MessageRole.USER:
                st.markdown(
                    f"""
                    <div class="chat-message user-message">
                        <strong>You:</strong><br/>{msg.content}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                    <div class="chat-message assistant-message">
                        <strong>Assistant:</strong><br/>{msg.content}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Show citations (deduplicated and limited)
                if msg.citations:
                    # Group citations by source file to reduce verbosity
                    seen_sources = set()
                    unique_citations = []
                    for citation in msg.citations:
                        source_key = f"{citation.source_file}:{citation.page_number or 0}"
                        if source_key not in seen_sources:
                            seen_sources.add(source_key)
                            unique_citations.append(citation)

                    # Show at most 3 unique sources
                    unique_citations = unique_citations[:3]

                    with st.expander(f"Sources ({len(unique_citations)})", expanded=False):
                        for citation in unique_citations:
                            excerpt = (
                                citation.excerpt[:120]
                                if len(citation.excerpt) > 120
                                else citation.excerpt
                            )
                            st.markdown(
                                f"""
                                <div class="citation-box">
                                    <strong>{citation.source_file.split("/")[-1]}</strong>
                                    {f" (Page {citation.page_number})" if citation.page_number else ""}
                                    <br/><em class="text-secondary">{excerpt}...</em>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

        # Chat input
        user_input = st.chat_input("Ask about your documents...")

        if user_input:
            # Check for injection attempts
            check = injection_detector.check(user_input)
            if not check.is_safe:
                st.warning(
                    f"[!] {injection_detector.get_safe_alternative(user_input, check.reason)}"
                )
            else:
                # Show processing indicator
                with st.spinner(
                    f"Thinking... ({settings.llm_provider.upper() if llm_available else 'Fallback'})"
                ):
                    try:
                        response = asyncio.run(
                            chat_engine.chat(
                                user_id=st.session_state.user_id,
                                thread_id=st.session_state.current_thread_id,
                                message=user_input,
                            )
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"[X] Error: {e}")
                        if st.session_state.debug_mode:
                            st.exception(e)
    else:
        st.error("Conversation not found. Please create a new one.")
        st.session_state.current_thread_id = None

# Footer
st.markdown("---")
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.markdown(
        "<center><small>ChatWithDocs v2.0 - Powered by AI | Built with Streamlit & ChromaDB</small></center>",
        unsafe_allow_html=True,
    )
