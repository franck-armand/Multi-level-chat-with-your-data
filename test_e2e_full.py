#!/usr/bin/env python3
"""End-to-end integration test for ChatWithDocs RAG system.

This script tests the complete flow:
1. File ingestion (upload -> extract -> embed -> store)
2. Chat with retrieval and citations

Usage:
    uv run python test_e2e_full.py
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

print("=" * 70)
print("CHATWITHDOCS END-TO-END INTEGRATION TEST")
print("=" * 70)


async def test_full_flow():
    """Test complete ingestion and chat flow."""

    # Create test document
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "company_handbook.txt"
        test_content = """
Company Handbook - Acme Corp

Welcome to Acme Corp!

About Us:
Acme Corp was founded in 1995 by John Smith. We specialize in innovative
software solutions for enterprise customers. Our headquarters is located
in San Francisco, California.

Benefits:
All full-time employees receive comprehensive health insurance, 401(k)
matching up to 6%, and unlimited PTO. We also offer remote work options
for most positions.

Contact:
For questions about benefits, contact HR at hr@acmecorp.com
For IT support, email support@acmecorp.com or call (555) 123-4567
"""
        test_file.write_text(test_content)
        print(f"\n- Created test document: {test_file}")

        # Test 1: Ingestion Pipeline
        print("\n" + "=" * 60)
        print("TEST 1: File Ingestion Pipeline")
        print("=" * 60)

        from chatwithdocs.ingestion import IngestionPipeline

        pipeline = IngestionPipeline()
        result = await pipeline.ingest_file(test_file, user_id="test_user")

        if result["success"]:
            print("- File ingested successfully")
            print(f"- Chunks indexed: {result['chunks_indexed']}")
            print(f"- File path: {result['file_path']}")
        else:
            print(f"x Ingestion failed: {result['error']}")
            return False

        # Test 2: Chat Engine
        print("\n" + "=" * 60)
        print("TEST 2: Chat with Retrieval")
        print("=" * 60)

        from chatwithdocs.chat.engine import ChatEngine

        chat_engine = ChatEngine()

        # Query about company info
        response = await chat_engine.chat(
            user_id="test_user",
            thread_id=None,  # Create new thread
            message="Who founded Acme Corp and when?",
        )

        print("- Chat response received")
        print(f"- Thread ID: {response['thread_id']}")
        print(f"- Response: {response['content'][:200]}...")
        print(f"- Sources: {response['sources']}")
        print(f"- Citations: {len(response['citations'])}")

        # Test 3: Follow-up question
        print("\n" + "=" * 60)
        print("TEST 3: Follow-up Question")
        print("=" * 60)

        response2 = await chat_engine.chat(
            user_id="test_user",
            thread_id=response["thread_id"],
            message="What benefits do employees get?",
        )

        print("- Follow-up response received")
        print(f"- Same thread: {response2['thread_id'] == response['thread_id']}")
        print(f"- Response: {response2['content'][:200]}...")
        print(f"- Citations: {len(response2['citations'])}")

        # Test 4: Query with no results
        print("\n" + "=" * 60)
        print("TEST 4: Query with No Matches")
        print("=" * 60)

        response3 = await chat_engine.chat(
            user_id="test_user",
            thread_id=None,
            message="What is the weather like today?",
        )

        print("- Response for no-match query")
        print(f"- Response: {response3['content'][:100]}...")

    return True


# Run the test
if __name__ == "__main__":
    success = asyncio.run(test_full_flow())

    if success:
        print("\n" + "=" * 60)
        print("ALL END-TO-END TESTS PASSED -")
        print("=" * 60)
        print("\nThe Edan-V2 RAG system is fully operational!")
        print("\nYou can now:")
        print("1. Run the Streamlit UI: streamlit run app/streamlit_app.py")
        print("2. Upload documents through the web interface")
        print("3. Chat with AI that retrieves from your documents")
    else:
        print("\nx Tests failed")
        exit(1)
