"""
Temporal activities for ticket processing.

Each activity is a discrete, retryable unit of work. Activities can:
- Make DB calls (fetch_ticket, get_similar_tickets_activity, update_ticket)
- Call external APIs (classify_ticket, run_investigation_agent)
- Perform pure computation (decide_action, validate_result, respond_to_user)

Temporal retries failed activities automatically based on the retry policy
set in the workflow. All state is passed explicitly — no shared mutable state.
"""

import logging
import uuid
from typing import Any

import anthropic
from sqlmodel import Session
from temporalio import activity

from app.agents.investigation_agent import run_investigation
from app.core.config import settings
from app.core.db import engine
from app.models import Ticket, TicketAnalysis, TicketPriority, TicketStatus
from app.tools.ticket_tools import get_similar_tickets

logger = logging.getLogger(__name__)


@activity.defn
async def fetch_ticket(ticket_id: str) -> dict[str, Any]:
    """Load ticket from DB and return a plain dict (serializable across Temporal)."""
    with Session(engine) as session:
        ticket = session.get(Ticket, uuid.UUID(ticket_id))
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")
        return {
            "id": str(ticket.id),
            "title": ticket.title,
            "description": ticket.description,
            "status": ticket.status.value,
        }


@activity.defn
async def classify_ticket(title: str, description: str) -> str:
    """
    Use Claude Haiku to classify the ticket into a support category.
    Returns one of: authentication, database, api, performance, deployment, general.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=20,
        messages=[
            {
                "role": "user",
                "content": (
                    "Classify into ONE of: authentication, database, api, performance, deployment, general.\n"
                    f"Title: {title}\n"
                    f"Description: {description}\n"
                    "Respond with ONLY the category name, nothing else."
                ),
            }
        ],
    )
    category = response.content[0].text.strip().lower()
    valid = {"authentication", "database", "api", "performance", "deployment", "general"}
    result = category if category in valid else "general"
    logger.info("📂 Classified ticket as: %s", result)
    return result


@activity.defn
async def decide_action(category: str) -> str:
    """
    Route the ticket: 'investigate' triggers the full agent, 'auto_resolve' skips it.
    Extend this with ML-based routing or confidence thresholds in production.
    """
    # All non-general categories benefit from the full investigation agent
    return "auto_resolve" if category == "general" else "investigate"


@activity.defn
async def get_similar_tickets_activity(keywords: list[str]) -> list[dict[str, str]]:
    """Fetch resolved tickets sharing keywords with the current ticket."""
    with Session(engine) as session:
        return get_similar_tickets(session, keywords)


@activity.defn
async def run_investigation_agent(
    ticket_data: dict[str, Any],
    similar_tickets: list[dict[str, str]],
) -> dict[str, Any]:
    """
    Delegate to the investigation agent (Claude agentic loop).
    The agent layer is stateless — all context is passed in explicitly.
    """
    logger.info("🎫 Running investigation agent for ticket: '%s'", ticket_data["title"])
    return await run_investigation(
        ticket_title=ticket_data["title"],
        ticket_description=ticket_data["description"],
        similar_tickets=similar_tickets,
    )


@activity.defn
async def validate_result(analysis: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitize the agent's output before writing to the DB.
    Ensures required fields exist and confidence is clamped to [0, 1].
    """
    if not analysis:
        return {
            "summary": "Automatic analysis could not determine the root cause.",
            "diagnosis": "The agent was unable to identify a specific root cause.",
            "suggested_fix": "Please escalate to a human engineer for manual review.",
            "priority": "medium",
            "needs_human": True,
            "confidence": 0.0,
        }
    confidence = float(analysis.get("confidence", 0.5))
    analysis["confidence"] = max(0.0, min(1.0, confidence))
    return analysis


@activity.defn
async def update_ticket(ticket_id: str, analysis: dict[str, Any]) -> None:
    """Persist the analysis and update the ticket status in the DB."""
    with Session(engine) as session:
        ticket = session.get(Ticket, uuid.UUID(ticket_id))
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")

        ticket_analysis = TicketAnalysis(
            ticket_id=ticket.id,
            summary=str(analysis["summary"]),
            diagnosis=str(analysis["diagnosis"]),
            suggested_fix=str(analysis["suggested_fix"]),
            priority=TicketPriority(analysis["priority"]),
            needs_human=bool(analysis["needs_human"]),
            confidence=float(analysis["confidence"]),
        )
        session.add(ticket_analysis)

        ticket.status = (
            TicketStatus.escalated if analysis["needs_human"] else TicketStatus.resolved
        )
        session.add(ticket)
        session.commit()


@activity.defn
async def respond_to_user(ticket_id: str, analysis: dict[str, Any]) -> None:
    """
    Final activity — notify the user that analysis is complete.
    Currently logs only; extend to send email/webhook/Slack in production.
    """
    status = "escalated" if analysis.get("needs_human") else "resolved"
    logger.info(
        "✅ Ticket %s → %s | priority=%s | needs_human=%s | confidence=%.0f%%",
        ticket_id,
        status,
        analysis.get("priority", "unknown"),
        analysis.get("needs_human", False),
        float(analysis.get("confidence", 0)) * 100,
    )
