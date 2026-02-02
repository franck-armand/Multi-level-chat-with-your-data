from __future__ import annotations

from typing import Any, Dict, List, Optional

from chatwithdocs.level2.state import Citation
from chatwithdocs.llm.config import get_llm_config
from chatwithdocs.llm.openai_client import openai_narrative


def format_citations(hits: List[Citation], max_citations: int = 5) -> str:
    if not hits:
        return ""
    lines = ["\n**Sources**:"]
    for h in hits[:max_citations]:
        lines.append(
            f"- [chunk_id={h.chunk_id} | region={h.region} | code={h.circonscription_code} | {h.party} | {h.candidate}] "
            f"“{h.excerpt}…”"
        )
    return "\n".join(lines)


def answer_from_sql_local(sql_rows: Optional[List[Dict[str, Any]]], sql_used: str) -> str:
    if not sql_rows:
        return "**No matching rows were returned from the dataset.**"

    # Single row summarization
    if len(sql_rows) == 1:
        row = sql_rows[0]
        if "party" in row and "seats" in row:
            return f"**{row['party']}** won **{row['seats']}** seats."
        if "seats" in row and len(row.keys()) == 1:
            return f"Seats: **{row['seats']}**"
        # generic
        bullets = "\n".join([f"- **{k}**: {row[k]}" for k in row.keys()])
        return "Here's what I found:\n\n" + bullets

    # Multi-row: short narrative only
    return f"Here's what I found (**{len(sql_rows)} rows**). Showing a preview below."


def answer_from_rag_local(user_query: str, hits: List[Citation]) -> str:
    if not hits:
        return (
            "**Not found in the provided PDF dataset.**\n\n"
            "I searched the indexed dataset rows but couldn't find a close match.\n"
            "Try rephrasing with a party name, region, circonscription code, or candidate name."
        )

    top = hits[0]
    text = (
        "I found the closest matches in the dataset for your query:\n\n"
        f"- Best match: **{top.candidate}** ({top.party}), circonscription **{top.circonscription_code}**.\n"
    )
    text += format_citations(hits)
    return text


def enhance_with_openai_if_enabled(base_answer: str, user_query: str, citations: str) -> str:
    """
    If OpenAI mode is enabled, rewrite answer in fluent narrative while staying grounded.
    If OpenAI isn't enabled (or fails), return base_answer.
    """
    cfg = get_llm_config()
    if not cfg.enabled:
        return base_answer

    # Strong grounding instruction
    prompt = f"""You are a helpful assistant answering questions about an election results dataset.
    You MUST follow these rules:
    - Use ONLY the evidence provided in the "EVIDENCE" section.
    - If the answer is not supported, say: "Not found in the provided PDF dataset."
    - Keep the final answer concise and factual.
    - End with a short "Sources" section listing chunk_id/circonscription_code from evidence.

    USER QUESTION:
    {user_query}

    DRAFT ANSWER (may be imperfect):
    {base_answer}

    EVIDENCE (citations + excerpts):
    {citations}
    """

    result = openai_narrative(cfg, prompt)
    if result.used_llm and result.text.strip():
        return result.text.strip()

    # fallback if OpenAI failed
    return base_answer