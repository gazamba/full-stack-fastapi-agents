"""
Temporal worker — runs as a separate process alongside the FastAPI server.

Start with:
    cd backend && uv run python -m app.worker

The worker connects to Temporal, registers all workflows and activities,
and polls the task queue for work. Temporal handles scheduling, retries,
and durability — if the worker dies, it restarts and resumes from where it left off.
"""

import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from app.activities.ticket_activities import (
    classify_ticket,
    decide_action,
    fetch_ticket,
    get_similar_tickets_activity,
    respond_to_user,
    run_investigation_agent,
    update_ticket,
    validate_result,
)
from app.core.config import settings
from app.workflows.ticket_workflow import TicketWorkflow

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    client = await Client.connect(settings.TEMPORAL_HOST)

    worker = Worker(
        client,
        task_queue=settings.TEMPORAL_TASK_QUEUE,
        workflows=[TicketWorkflow],
        activities=[
            fetch_ticket,
            classify_ticket,
            decide_action,
            get_similar_tickets_activity,
            run_investigation_agent,
            validate_result,
            update_ticket,
            respond_to_user,
        ],
    )

    logger.info(
        "🚀 Worker started | queue=%s | host=%s",
        settings.TEMPORAL_TASK_QUEUE,
        settings.TEMPORAL_HOST,
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
