"""
Tool implementations and knowledge base for ticket analysis.

These are used by the investigation agent as callable tools that Claude
can invoke during its reasoning loop.
"""

from sqlmodel import Session, select

from app.models import Ticket, TicketStatus

# Simple knowledge base — in production this would be a vector DB or search API
KNOWLEDGE_BASE: dict[str, list[dict[str, str]]] = {
    "authentication": [
        {
            "title": "JWT Token Expiry",
            "content": "Access tokens expire after 8 days. Re-authenticate via POST /api/v1/login/access-token.",
        },
        {
            "title": "403 Forbidden on API calls",
            "content": "Check that the Authorization header is 'Bearer <token>'. Token must not be expired.",
        },
    ],
    "database": [
        {
            "title": "Migration Failures",
            "content": "Run `alembic upgrade head`. If schema conflicts exist, check for duplicate column definitions.",
        },
        {
            "title": "Connection Errors",
            "content": "Verify POSTGRES_SERVER, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD in .env.",
        },
    ],
    "api": [
        {
            "title": "CORS Errors",
            "content": "Add your frontend URL to BACKEND_CORS_ORIGINS in .env. Restart the server after.",
        },
        {
            "title": "422 Unprocessable Entity",
            "content": "Request body does not match the expected schema. Check the API docs at /api/v1/docs.",
        },
    ],
    "performance": [
        {
            "title": "Slow Queries",
            "content": "Add indexes to frequently filtered columns. Use .limit() on large result sets.",
        },
    ],
    "deployment": [
        {
            "title": "Docker Build Failures",
            "content": "Ensure all dependencies are in pyproject.toml. Run `uv sync` before building.",
        },
        {
            "title": "Environment Variables Missing",
            "content": "Copy .env.example to .env and fill in all required values before starting.",
        },
    ],
    "general": [
        {
            "title": "Getting Started",
            "content": "Run `docker compose watch` for development. API docs available at /api/v1/docs.",
        },
    ],
}


def search_knowledge_base(query: str, category: str = "general") -> list[dict[str, str]]:
    """Keyword search over the knowledge base articles."""
    results = list(KNOWLEDGE_BASE.get(category, []))
    if category != "general":
        results += KNOWLEDGE_BASE.get("general", [])

    query_words = query.lower().split()
    matched = [
        article
        for article in results
        if any(
            word in article["title"].lower() or word in article["content"].lower()
            for word in query_words
        )
    ]
    return (matched or results)[:3]


def get_similar_tickets(session: Session, keywords: list[str]) -> list[dict[str, str]]:
    """Fetch resolved tickets that share keywords with the current ticket."""
    resolved = session.exec(
        select(Ticket).where(Ticket.status == TicketStatus.resolved).limit(20)
    ).all()

    matches = []
    for ticket in resolved:
        text = f"{ticket.title} {ticket.description}".lower()
        if any(kw.lower() in text for kw in keywords):
            entry: dict[str, str] = {
                "title": ticket.title,
                "status": ticket.status.value,
            }
            if ticket.analysis:
                entry["resolution"] = ticket.analysis.suggested_fix
            matches.append(entry)

    return matches[:3]
