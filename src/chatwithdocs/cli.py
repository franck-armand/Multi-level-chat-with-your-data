"""
ChatWithDocs CLI - Command line interface for the RAG document chat system.

Usage:
    chatwithdocs --help
    chatwithdocs upload document.pdf
    chatwithdocs chat "What is this document about?"
    chatwithdocs server --api
    chatwithdocs server --ui
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from pathlib import Path


def print_header():
    """Print CLI header."""
    print("=" * 60)
    print("ChatWithDocs CLI v2.0")
    print("=" * 60)


def cmd_upload(args: argparse.Namespace) -> int:
    """Upload and index a document."""
    print_header()

    from chatwithdocs.ingestion import IngestionPipeline

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        return 1

    print(f"File: {file_path.name}")
    print(f"   Type: {file_path.suffix}")
    print(f"   Size: {file_path.stat().st_size / 1024:.1f} KB")
    print()

    async def do_upload():
        pipeline = IngestionPipeline()
        result = await pipeline.ingest_file(file_path, user_id=args.user or "cli_user")

        if result["success"]:
            print("Success: Upload successful!")
            print(f"   Chunks indexed: {result['chunks_indexed']}")
            print(f"   File: {result['file_path']}")
            return 0
        else:
            print(f"Error: Upload failed: {result['error']}")
            return 1

    return asyncio.run(do_upload())


def cmd_list(args: argparse.Namespace) -> int:
    """List uploaded documents."""
    print_header()

    async def do_list():
        # Get unique source files from vector store
        # This is a simplified version - in production we'd query properly
        print("Documents:")
        print("-" * 60)

        # TODO: Implement proper document listing
        # For now, check the data/uploads directory
        uploads_dir = Path("data/uploads")
        if uploads_dir.exists():
            files = list(uploads_dir.rglob("*.*"))
            if files:
                for i, file in enumerate(files[:20], 1):  # Limit to 20
                    if file.is_file():
                        size = file.stat().st_size / 1024
                        print(f"{i:2}. {file.name:<40} ({size:>7.1f} KB)")
            else:
                print("   No documents found. Use 'chatwithdocs upload <file>' to add documents.")
        else:
            print("   No documents found. Use 'chatwithdocs upload <file>' to add documents.")

        return 0

    return asyncio.run(do_list())


def cmd_chat(args: argparse.Namespace) -> int:
    """Chat with documents."""
    print_header()

    from chatwithdocs.chat.engine import ChatEngine
    from chatwithdocs.config.manager import ConfigManager

    # Check if AI is configured
    config = ConfigManager().get_current_config()
    if not config["llm_available"]:
        print("Warning: No AI model configured.")
        print("   Using fallback mode (limited responses).")
        print("   Configure an AI model with: chatwithdocs config")
        print()

    print(f"AI: Chat Mode (User: {args.user})")
    print("   Type your questions or 'quit' to exit")
    print("-" * 60)

    engine = ChatEngine()
    user_id = args.user or "cli_user"
    thread_id = args.thread

    async def do_chat():
        nonlocal thread_id

        # If question provided, ask it once
        if args.question:
            response = await engine.chat(
                user_id=user_id, thread_id=thread_id, message=args.question
            )

            print(f"\nQ: {args.question}")
            print(f"\nA: {response['content']}")

            if response["sources"]:
                print(f"\nSources: {', '.join(response['sources'][:3])}")

            print(f"\nThread ID: {response['thread_id']}")
            return 0

        # Interactive mode
        while True:
            try:
                question = input("\nQ: ").strip()

                if question.lower() in ["quit", "exit", "q"]:
                    print("\nGoodbye!")
                    break

                if not question:
                    continue

                print("AI: Thinking...")

                response = await engine.chat(user_id=user_id, thread_id=thread_id, message=question)

                thread_id = response["thread_id"]  # Update for follow-ups

                print(f"\n{response['content']}")

                if response["sources"]:
                    print(f"\nSources: {', '.join(response['sources'][:3])}")

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"\nError: {e}")

        return 0

    return asyncio.run(do_chat())


def cmd_conversations(args: argparse.Namespace) -> int:
    """List or manage conversations."""
    print_header()

    from chatwithdocs.chat.manager import ConversationManager

    manager = ConversationManager()
    user_id = args.user or "cli_user"

    if args.delete:
        # Delete conversation
        if manager.delete_conversation(args.delete, user_id):
            print(f"Success: Deleted conversation: {args.delete}")
        else:
            print(f"Error: Conversation not found: {args.delete}")
        return 0

    # List conversations
    conversations = manager.list_conversations(user_id)

    if not conversations:
        print("No conversations found.")
        return 0

    print(f"Conversations for {user_id}:")
    print("-" * 60)

    for i, conv in enumerate(conversations[:20], 1):
        title = conv.get("title") or "Untitled"
        msg_count = (
            len(manager.get_thread(conv["id"]).messages) if manager.get_thread(conv["id"]) else 0
        )
        updated = conv.get("updated_at", "Unknown")

        print(f"{i:2}. {title:<35} ({msg_count} messages)")
        print(f"    ID: {conv['id']}")
        print(f"    Updated: {updated}")
        print()

    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """Configure AI settings."""
    print_header()

    from chatwithdocs.config.manager import ConfigManager

    config_manager = ConfigManager()

    if args.show:
        # Show current config
        config = config_manager.get_current_config()
        print("Config: Current Configuration:")
        print("-" * 60)
        print(f"Provider: {config['provider'].upper()}")
        print(f"Model: {config.get('model', 'N/A')}")
        print(f"Status: {'OK: Connected' if config['llm_available'] else 'Error: Not Connected'}")
        if config.get("error"):
            print(f"Error: {config['error']}")
        return 0

    if args.provider:
        # Set provider
        provider = args.provider.lower()

        if provider == "ollama":
            # Check Ollama
            models = config_manager.load_available_ollama_models()
            if not models:
                print("Error: Ollama not running. Start with: ollama serve")
                return 1

            print("OK: Ollama is running!")
            print(f"Available models: {', '.join(models[:5])}")

            if args.model and args.model in [m.replace(":latest", "") for m in models]:
                if config_manager.save_config("ollama", model=args.model):
                    print(f"Success: Saved Ollama with model: {args.model}")
                else:
                    print("Error: Failed to save configuration")
            elif models:
                # Use first available
                first_model = models[0].replace(":latest", "")
                if config_manager.save_config("ollama", model=first_model):
                    print(f"Success: Saved Ollama with model: {first_model}")

        elif provider in ["openai", "deepseek", "kimi"]:
            if not args.api_key:
                print(f"Error: API key required for {provider}")
                print(f"   Usage: chatwithdocs config --provider {provider} --api-key <key>")
                return 1

            # Test connection first
            print(f"Test: Testing {provider} connection...")
            success, msg = config_manager.test_connection(provider, api_key=args.api_key)

            if success:
                # Save
                if config_manager.save_config(provider, api_key=args.api_key, model=args.model):
                    print(f"Success: Connected and saved: {msg}")
                else:
                    print("Error: Failed to save configuration")
            else:
                print(f"Error: Connection failed: {msg}")
                return 1

        return 0

    # Interactive config
    print("AI Model Configuration")
    print("-" * 60)
    print()
    print("Available providers:")
    print("  1. Ollama (Local - Free)")
    print("  2. OpenAI")
    print("  3. DeepSeek")
    print("  4. Kimi (Moonshot AI)")
    print()

    choice = input("Select provider (1-4): ").strip()

    providers = {"1": "ollama", "2": "openai", "3": "deepseek", "4": "kimi"}
    provider = providers.get(choice)

    if not provider:
        print("Error: Invalid choice")
        return 1

    if provider == "ollama":
        return cmd_config(
            argparse.Namespace(provider="ollama", api_key=None, model=None, show=False)
        )
    else:
        api_key = input(f"Enter {provider.upper()} API key: ").strip()
        if api_key:
            return cmd_config(
                argparse.Namespace(provider=provider, api_key=api_key, model=None, show=False)
            )
        else:
            print("Error: API key required")
            return 1


def cmd_server(args: argparse.Namespace) -> int:
    """Start server (API or UI)."""
    print_header()

    if args.api:
        print("Starting: FastAPI server...")
        print(f"   URL: http://localhost:{args.port}")
        print(f"   Docs: http://localhost:{args.port}/docs")
        print("-" * 60)
        print("Press Ctrl+C to stop")
        print()

        import uvicorn

        # Add project root to path so uvicorn can find api.main
        cli_dir = Path(__file__).parent
        project_root = cli_dir.parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        uvicorn.run("api.main:app", host="0.0.0.0", port=args.port, reload=args.reload)

    elif args.ui:
        print("Starting: Streamlit UI...")
        print(f"   URL: http://localhost:{args.port}")
        print("-" * 60)
        print("Press Ctrl+C to stop")
        print()

        import subprocess

        subprocess.run(
            [
                "streamlit",
                "run",
                "app/streamlit_app.py",
                "--server.port",
                str(args.port),
                "--server.address",
                "0.0.0.0",
            ]
        )

    else:
        print("Error: Specify --api or --ui")
        return 1

    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    """Clear all data."""
    print_header()

    from chatwithdocs.chat.engine import ChatEngine
    from chatwithdocs.chat.manager import ConversationManager

    print("Warning: This will delete all data!")
    print("   - All conversations")
    print("   - All uploaded documents")
    print("   - All vector embeddings")
    print()

    if not args.force:
        confirm = input("Type 'DELETE' to confirm: ").strip()
        if confirm != "DELETE":
            print("Cancelled")
            return 1

    user_id = args.user or "cli_user"

    # Delete conversations
    manager = ConversationManager()
    conversations = manager.list_conversations(user_id)
    deleted_conv = 0
    for conv in conversations:
        if manager.delete_conversation(conv["id"], user_id):
            deleted_conv += 1

    # Delete documents
    async def clear_docs():
        engine = ChatEngine()
        result = await engine.delete_all_user_data(user_id)
        return result

    result = asyncio.run(clear_docs())

    # Delete files from filesystem
    upload_dir = Path(f"data/uploads/{user_id}")
    files_deleted = 0
    if upload_dir.exists():
        # Count files before deletion
        files_deleted = len(list(upload_dir.rglob("*")))
        shutil.rmtree(upload_dir)

    print("Success: Cleared:")
    print(f"   Conversations: {deleted_conv}")
    print(f"   Document chunks: {result.get('document_chunks_deleted', 0)}")
    print(f"   Files deleted: {files_deleted}")

    return 0


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="chatwithdocs",
        description="ChatWithDocs - Chat with your documents using AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s upload document.pdf              Upload a PDF document
  %(prog)s list                            List uploaded documents
  %(prog)s chat "What is this about?"      Ask a question
  %(prog)s chat --interactive              Interactive chat mode
  %(prog)s config --show                   Show current AI configuration
  %(prog)s config --provider openai --api-key sk-...   Configure OpenAI
  %(prog)s server --ui                     Start Streamlit UI server
  %(prog)s server --api                    Start FastAPI server
  %(prog)s conversations                   List chat conversations
  %(prog)s clear --force                   Clear all data (WARNING!)
        """,
    )

    parser.add_argument("--version", action="version", version="%(prog)s 2.0.0")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Upload command
    upload_parser = subparsers.add_parser(
        "upload",
        help="Upload and index a document",
        description="Upload a PDF, DOCX, CSV, TXT, or MD file",
    )
    upload_parser.add_argument("file", help="Path to document file")
    upload_parser.add_argument("--user", "-u", help="User ID (default: cli_user)")
    upload_parser.set_defaults(func=cmd_upload)

    # List command
    list_parser = subparsers.add_parser("list", help="List uploaded documents")
    list_parser.add_argument("--user", "-u", help="User ID")
    list_parser.set_defaults(func=cmd_list)

    # Chat command
    chat_parser = subparsers.add_parser(
        "chat",
        help="Chat with your documents",
        description="Ask questions about your uploaded documents",
    )
    chat_parser.add_argument(
        "question", nargs="?", help="Question to ask (if not provided, enters interactive mode)"
    )
    chat_parser.add_argument("--user", "-u", help="User ID")
    chat_parser.add_argument("--thread", "-t", help="Thread ID for conversation continuity")
    chat_parser.add_argument(
        "--interactive", "-i", action="store_true", help="Interactive chat mode"
    )
    chat_parser.set_defaults(func=cmd_chat)

    # Conversations command
    conv_parser = subparsers.add_parser(
        "conversations", aliases=["conv"], help="List or manage conversations"
    )
    conv_parser.add_argument("--user", "-u", help="User ID")
    conv_parser.add_argument("--delete", "-d", help="Delete conversation by ID")
    conv_parser.set_defaults(func=cmd_conversations)

    # Config command
    config_parser = subparsers.add_parser("config", help="Configure AI model settings")
    config_parser.add_argument(
        "--show", "-s", action="store_true", help="Show current configuration"
    )
    config_parser.add_argument(
        "--provider", "-p", choices=["ollama", "openai", "deepseek", "kimi"], help="AI provider"
    )
    config_parser.add_argument("--api-key", "-k", help="API key")
    config_parser.add_argument("--model", "-m", help="Model name (e.g., llama3.2, gpt-4o-mini)")
    config_parser.set_defaults(func=cmd_config)

    # Server command
    server_parser = subparsers.add_parser("server", help="Start web server")
    server_parser.add_argument("--api", action="store_true", help="Start FastAPI server")
    server_parser.add_argument("--ui", action="store_true", help="Start Streamlit UI server")
    server_parser.add_argument("--port", "-p", type=int, default=8501, help="Port number")
    server_parser.add_argument(
        "--reload", action="store_true", help="Auto-reload on code changes (API only)"
    )
    server_parser.set_defaults(func=cmd_server)

    # Clear command
    clear_parser = subparsers.add_parser(
        "clear",
        help="Clear all data (WARNING: destructive!)",
        description="Delete all conversations and documents",
    )
    clear_parser.add_argument("--force", "-f", action="store_true", help="Skip confirmation")
    clear_parser.add_argument("--user", "-u", help="User ID")
    clear_parser.set_defaults(func=cmd_clear)

    # Parse and run
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    try:
        return args.func(args)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        if hasattr(args, "debug") and args.debug:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
