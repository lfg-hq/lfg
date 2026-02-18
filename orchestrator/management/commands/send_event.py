"""
Management command to send test events to the orchestrator event bus.

Usage:
    python manage.py send_event --list-runs
    python manage.py send_event --project <id>
    python manage.py send_event --project <id> --type ticket_completed --payload '{"title": "Build login"}'
"""
import json
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Send a test event to the orchestrator via Django-Q"

    def add_arguments(self, parser):
        parser.add_argument("--project", type=str, help="Project ID (UUID or numeric)")
        parser.add_argument("--type", type=str, help="Event type (e.g. ticket_completed)")
        parser.add_argument("--payload", type=str, help="JSON payload string")
        parser.add_argument("--run-id", type=str, help="AgentRun UUID directly")
        parser.add_argument("--list-runs", action="store_true", help="List orchestrator runs")

    def handle(self, *args, **options):
        from orchestrator.models import AgentRun

        if options["list_runs"]:
            self._list_runs()
            return

        # Resolve agent run
        run_id = options.get("run_id")
        if run_id:
            agent_run = AgentRun.objects.select_related("project", "conversation").get(id=run_id)
        else:
            project_id = options.get("project")
            if not project_id:
                # Show projects with active runs and ask
                self._list_runs()
                project_id = input("\nProject ID: ").strip()
                if not project_id:
                    return

            # Find active run for this project
            from projects.models import Project
            try:
                project = Project.objects.get(project_id=project_id)
            except (Project.DoesNotExist, ValueError):
                try:
                    project = Project.objects.get(id=project_id)
                except Project.DoesNotExist:
                    self.stderr.write(self.style.ERROR(f"Project not found: {project_id}"))
                    return

            agent_run = (
                AgentRun.objects
                .select_related("project", "conversation")
                .filter(
                    project=project,
                    status__in=["executing", "waiting_on_user", "planning"],
                )
                .order_by("-created_at")
                .first()
            )
            if not agent_run:
                self.stderr.write(self.style.ERROR(
                    f"No active orchestrator run for project '{project}'. Use --list-runs."
                ))
                return

        self.stdout.write(f"AgentRun: {agent_run.id}")
        self.stdout.write(f"  Project: {agent_run.project}")
        self.stdout.write(f"  Status:  {agent_run.status}")
        self.stdout.write(f"  Conv:    {agent_run.conversation_id}")

        # Get event type
        event_type = options.get("type")
        if not event_type:
            self.stdout.write("\nEvent types:")
            for et in [
                "ticket_completed", "ticket_failed", "ticket_blocked",
                "project_ticket_completed", "project_ticket_failed",
                "new_user_message", "user_response",
            ]:
                self.stdout.write(f"  {et}")
            event_type = input("\nEvent type: ").strip()
            if not event_type:
                return

        # Get payload
        payload_str = options.get("payload")
        if not payload_str:
            payload_str = input("Payload JSON (Enter for empty): ").strip()
        payload = json.loads(payload_str) if payload_str else {}

        self.stdout.write(f"\nSending: {event_type} -> {json.dumps(payload)}")

        from django_q.tasks import async_task
        task_id = async_task(
            "orchestrator.tasks.handle_orchestrator_event",
            str(agent_run.id),
            event_type,
            payload,
            task_name=f"test-{event_type}",
        )
        self.stdout.write(self.style.SUCCESS(f"Queued Django-Q task: {task_id}"))

    def _list_runs(self):
        from orchestrator.models import AgentRun
        runs = AgentRun.objects.select_related("project", "conversation").order_by("-created_at")[:20]
        if not runs:
            self.stdout.write("No runs found.")
            return
        self.stdout.write(
            f"{'ID':<40} {'Status':<18} {'Project':<30} {'Conv':<6} {'Created'}"
        )
        self.stdout.write("-" * 110)
        for r in runs:
            proj_name = str(r.project)[:28] if r.project else "-"
            self.stdout.write(
                f"{str(r.id):<40} {r.status:<18} "
                f"{proj_name:<30} {str(r.conversation_id or '-'):<6} "
                f"{r.created_at.strftime('%m-%d %H:%M')}"
            )
