"""
Investigation agent — Claude as the reasoning engine.

Uses the Anthropic SDK beta tool runner to handle the agentic loop automatically.
Tools are defined with @beta_tool; similar_tickets and the final analysis result
are captured via closures — no manual message loop needed.
"""

import asyncio
import json
import logging
from typing import Any

import anthropic
from anthropic import beta_tool

from app.core.config import settings
from app.tools.ticket_tools import search_knowledge_base as kb_search

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert AI support engineer. Your job is to analyze support tickets and provide structured diagnoses.

For each ticket:
1. Search the knowledge base for relevant solutions
2. Check similar past tickets if useful
3. Submit your final structured analysis using the submit_analysis tool

Be specific and actionable. Always end by calling submit_analysis."""


async def run_investigation(
    ticket_title: str,
    ticket_description: str,
    similar_tickets: list[dict[str, str]],
) -> dict[str, Any]:
    """
    Run the Claude agentic loop to investigate a support ticket.

    The tool runner handles calling tools and feeding results back to Claude
    automatically — no manual message loop needed. Similar tickets are
    pre-fetched by the Temporal activity and injected via closure so this
    layer stays stateless (no direct DB access).
    """
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    analysis_result: dict[str, Any] = {}

    @beta_tool
    def search_knowledge_base(query: str, category: str = "general") -> str:
        """Search the internal knowledge base for solutions relevant to this ticket.

        Args:
            query: The search query.
            category: Category to search — one of: authentication, database, api, performance, deployment, general.
        """
        results = kb_search(query, category)
        return json.dumps(results) if results else "No results found."

    @beta_tool
    def get_similar_tickets(keywords: list[str]) -> str:
        """Find previously resolved support tickets similar to this one.

        Args:
            keywords: Keywords to match against past ticket titles and descriptions.
        """
        return json.dumps(similar_tickets) if similar_tickets else "No similar tickets found."

    @beta_tool
    def submit_analysis(
        summary: str,
        diagnosis: str,
        suggested_fix: str,
        priority: str,
        needs_human: bool,
        confidence: float,
    ) -> str:
        """Submit your final structured analysis. Call this once you have enough information.

        Args:
            summary: 1-2 sentence summary of the issue.
            diagnosis: Detailed technical diagnosis of the root cause.
            suggested_fix: Step-by-step recommended solution.
            priority: Ticket priority — one of: low, medium, high, critical.
            needs_human: True if this ticket requires a human engineer to review.
            confidence: Confidence score from 0.0 (uncertain) to 1.0 (certain).
        """
        nonlocal analysis_result
        analysis_result = {
            "summary": summary,
            "diagnosis": diagnosis,
            "suggested_fix": suggested_fix,
            "priority": priority,
            "needs_human": needs_human,
            "confidence": confidence,
        }
        logger.info("📋 Analysis submitted | priority=%s | needs_human=%s", priority, needs_human)
        return "Analysis submitted."

    context = ""
    if similar_tickets:
        context = f"\n\nSimilar resolved tickets for reference:\n{json.dumps(similar_tickets, indent=2)}"

    prompt = (
        f"Please analyze this support ticket:\n\n"
        f"**Title:** {ticket_title}\n\n"
        f"**Description:**\n{ticket_description}"
        f"{context}"
    )

    logger.info("🤖 Starting investigation for ticket: '%s'", ticket_title)

    def _run() -> None:
        runner = client.beta.messages.tool_runner(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[search_knowledge_base, get_similar_tickets, submit_analysis],
            messages=[{"role": "user", "content": prompt}],
        )
        for message in runner:
            for block in message.content:
                if block.type == "tool_use":
                    logger.info("🔧 Tool call: %s | input=%s", block.name, block.input)
                elif block.type == "text" and block.text.strip():
                    logger.info("💬 Claude: %s", block.text.strip())

    await asyncio.to_thread(_run)

    if not analysis_result:
        logger.warning("Agent finished without calling submit_analysis for ticket: '%s'", ticket_title)

    return analysis_result
