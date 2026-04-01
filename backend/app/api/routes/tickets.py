import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import selectinload
from sqlmodel import col, func, select

from app.api.deps import CurrentUser, SessionDep, TemporalClientDep
from app.models import (
    Message,
    Ticket,
    TicketCreate,
    TicketPublic,
    TicketsPublic,
    TicketStatus,
)
from app.workflows.ticket_workflow import TicketWorkflow
from app.core.config import settings

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("/", response_model=TicketsPublic)
def read_tickets(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """List all tickets belonging to the current user."""
    count_statement = (
        select(func.count())
        .select_from(Ticket)
        .where(Ticket.owner_id == current_user.id)
    )
    count = session.exec(count_statement).one()

    statement = (
        select(Ticket)
        .where(Ticket.owner_id == current_user.id)
        .options(selectinload(Ticket.analysis))  # type: ignore[arg-type]
        .order_by(col(Ticket.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    tickets = session.exec(statement).all()

    return TicketsPublic(data=list(tickets), count=count)


@router.post("/", response_model=TicketPublic, status_code=201)
async def create_ticket(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    ticket_in: TicketCreate,
    temporal: TemporalClientDep,
) -> Any:
    """
    Submit a new support ticket.

    Saves the ticket as 'analyzing' and immediately starts a Temporal workflow
    that orchestrates the full analysis pipeline. The workflow runs durably —
    if the worker restarts, it resumes from the last completed activity.

    Poll GET /tickets/{id} until status changes from 'analyzing'.
    """
    ticket = Ticket.model_validate(
        ticket_in,
        update={"owner_id": current_user.id, "status": TicketStatus.analyzing},
    )
    session.add(ticket)
    session.commit()
    session.refresh(ticket)

    await temporal.start_workflow(
        TicketWorkflow.handle_ticket,
        str(ticket.id),
        id=f"ticket-{ticket.id}",
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )

    return ticket


@router.get("/{id}", response_model=TicketPublic)
def read_ticket(
    session: SessionDep,
    current_user: CurrentUser,
    id: uuid.UUID,
) -> Any:
    """Get a single ticket with its AI analysis (once available)."""
    statement = (
        select(Ticket)
        .where(Ticket.id == id)
        .options(selectinload(Ticket.analysis))  # type: ignore[arg-type]
    )
    ticket = session.exec(statement).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return ticket


@router.delete("/{id}")
def delete_ticket(
    session: SessionDep,
    current_user: CurrentUser,
    id: uuid.UUID,
) -> Message:
    """Delete a ticket and its analysis."""
    ticket = session.get(Ticket, id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    session.delete(ticket)
    session.commit()
    return Message(message="Ticket deleted successfully")
