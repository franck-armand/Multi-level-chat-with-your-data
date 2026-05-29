"""Export conversations to various formats."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chatwithdocs.chat.models import Thread


class ConversationExporter:
    """Export conversations to markdown or PDF format."""

    def to_markdown(self, thread: Thread) -> str:
        """Export conversation as markdown.

        Args:
            thread: Chat thread to export

        Returns:
            Markdown formatted conversation
        """
        md = f"# Conversation: {thread.title or 'Untitled'}\n\n"
        md += f"*Thread ID: {thread.id}*  \n"
        md += (
            f"*Created: {thread.created_at.isoformat() if thread.created_at else 'Unknown'}*  \n\n"
        )

        for msg in thread.messages:
            timestamp = (
                msg.timestamp.strftime("%Y-%m-%d %H:%M:%S") if hasattr(msg, "timestamp") else ""
            )

            if msg.role.value == "user":
                md += f"## User ({timestamp})\n\n"
                md += f"{msg.content}\n\n"
            else:
                md += f"## Assistant ({timestamp})\n\n"
                md += f"{msg.content}\n\n"

                # Add citations if present
                if hasattr(msg, "metadata") and msg.metadata.get("citations"):
                    md += "### Sources\n\n"
                    for cite in msg.metadata["citations"]:
                        md += f"- **{cite.get('source_file', 'Unknown')}**"
                        if cite.get("page_number"):
                            md += f" (Page {cite['page_number']})"
                        if cite.get("section"):
                            md += f" - *{cite['section']}*"
                        md += "\n"
                    md += "\n"

        return md

    async def to_pdf(self, thread: Thread) -> bytes:
        """Export conversation as PDF.

        Args:
            thread: Chat thread to export

        Returns:
            PDF bytes
        """
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

            pdf_buffer = BytesIO()
            doc = SimpleDocTemplate(
                pdf_buffer, pagesize=letter, rightMargin=0.5 * inch, leftMargin=0.5 * inch
            )

            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                "CustomTitle",
                parent=styles["Heading1"],
                fontSize=16,
                textColor="black",
                spaceAfter=6,
            )

            user_style = ParagraphStyle(
                "UserMessage", parent=styles["Normal"], fontSize=10, textColor="navy", spaceAfter=12
            )

            assistant_style = ParagraphStyle(
                "AssistantMessage",
                parent=styles["Normal"],
                fontSize=10,
                textColor="darkgreen",
                spaceAfter=12,
            )

            source_style = ParagraphStyle(
                "Source",
                parent=styles["Normal"],
                fontSize=8,
                textColor="gray",
                spaceAfter=6,
                leftIndent=20,
            )

            story = []

            # Add title
            title = thread.title or "Untitled Conversation"
            story.append(Paragraph(title, title_style))
            story.append(Paragraph(f"<i>Thread ID: {thread.id}</i>", source_style))
            story.append(Spacer(1, 0.2 * inch))

            # Add messages
            for msg in thread.messages:
                timestamp = (
                    msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    if hasattr(msg, "timestamp")
                    else "Unknown"
                )

                if msg.role.value == "user":
                    story.append(Paragraph(f"<b>User ({timestamp})</b>", user_style))
                    story.append(Paragraph(msg.content, user_style))
                else:
                    story.append(Paragraph(f"<b>Assistant ({timestamp})</b>", assistant_style))
                    story.append(Paragraph(msg.content, assistant_style))

                    # Add citations
                    if hasattr(msg, "metadata") and msg.metadata.get("citations"):
                        story.append(Paragraph("<b>Sources:</b>", source_style))
                        for cite in msg.metadata["citations"]:
                            source_text = f"• {cite.get('source_file', 'Unknown')}"
                            if cite.get("page_number"):
                                source_text += f" (Page {cite['page_number']})"
                            if cite.get("section"):
                                source_text += f" - {cite['section']}"
                            story.append(Paragraph(source_text, source_style))

                story.append(Spacer(1, 0.1 * inch))

            # Build PDF
            doc.build(story)
            pdf_buffer.seek(0)
            return pdf_buffer.getvalue()

        except ImportError:
            raise ImportError("reportlab required for PDF export: pip install reportlab")
