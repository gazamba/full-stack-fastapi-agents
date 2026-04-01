# This module has been refactored.
# Logic now lives in:
#   app/tools/ticket_tools.py      — knowledge base + tool schemas
#   app/agents/investigation_agent.py — Claude agentic loop
#   app/activities/ticket_activities.py — Temporal activities
#   app/workflows/ticket_workflow.py   — TicketWorkflow orchestration
#   app/worker.py                  — Temporal worker entry point
