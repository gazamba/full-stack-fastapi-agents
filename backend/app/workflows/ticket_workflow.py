"""
TicketWorkflow — durable orchestration for support ticket analysis.

Temporal guarantees that this workflow runs to completion even if the worker
restarts mid-execution. Each activity is independently retried on failure.

Workflow code must be deterministic:
- No random numbers, no datetime.now(), no direct I/O
- All external calls go through activities
- The `workflow.unsafe.imports_passed_through()` block allows importing
  activity functions without Temporal's sandbox intercepting them
"""

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
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

_ACTIVITY_OPTIONS: dict[str, Any] = dict(
    start_to_close_timeout=timedelta(minutes=5),
    retry_policy=RetryPolicy(maximum_attempts=3),
)


@workflow.defn
class TicketWorkflow:
    @workflow.run
    async def handle_ticket(self, ticket_id: str) -> None:
        """
        7-step pipeline:
        fetch → classify → decide → investigate → validate → update → notify
        """
        # 1. Load ticket data from DB
        ticket = await workflow.execute_activity(
            fetch_ticket, ticket_id, **_ACTIVITY_OPTIONS
        )

        # 2. Classify into a support category
        category = await workflow.execute_activity(
            classify_ticket,
            args=[ticket["title"], ticket["description"]],
            **_ACTIVITY_OPTIONS,
        )

        # 3. Route: full investigation vs. quick auto-resolve
        action = await workflow.execute_activity(
            decide_action, category, **_ACTIVITY_OPTIONS
        )

        # 4. Build analysis
        if action == "investigate":
            keywords = ticket["title"].lower().split()[:5]
            similar = await workflow.execute_activity(
                get_similar_tickets_activity, keywords, **_ACTIVITY_OPTIONS
            )
            analysis = await workflow.execute_activity(
                run_investigation_agent,
                args=[ticket, similar],
                **_ACTIVITY_OPTIONS,
            )
        else:
            # Quick response for general / low-complexity tickets
            analysis = {
                "summary": f"General inquiry — categorized as: {category}.",
                "diagnosis": "Routine inquiry that can be resolved with documentation.",
                "suggested_fix": "Please refer to the API docs at /api/v1/docs.",
                "priority": "low",
                "needs_human": False,
                "confidence": 0.7,
            }

        # 5. Sanitize agent output
        analysis = await workflow.execute_activity(
            validate_result, analysis, **_ACTIVITY_OPTIONS
        )

        # 6. Persist analysis and update ticket status
        await workflow.execute_activity(
            update_ticket, args=[ticket_id, analysis], **_ACTIVITY_OPTIONS
        )

        # 7. Notify user (log / email / webhook)
        await workflow.execute_activity(
            respond_to_user, args=[ticket_id, analysis], **_ACTIVITY_OPTIONS
        )
