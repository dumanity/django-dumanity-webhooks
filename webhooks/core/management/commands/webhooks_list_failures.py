from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from webhooks.producer.models import OutgoingEvent
from webhooks.receiver.models import DeadLetter


class Command(BaseCommand):
    help = "List failed outgoing events and dead-letter records for operations"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        limit = options["limit"]
        as_json = options["json"]

        failed_outgoing = list(
            OutgoingEvent.objects.filter(status="failed")
            .order_by("-id")[:limit]
            .values("id", "endpoint__name", "attempts", "status", "next_retry_at")
        )
        dead_letters = list(
            DeadLetter.objects.order_by("-id")[:limit].values("id", "reason", "retries", "correlation_id", "request_id")
        )

        if as_json:
            self.stdout.write(
                json.dumps({"failed_outgoing": failed_outgoing, "dead_letters": dead_letters}, indent=2, default=str)
            )
            return

        self.stdout.write(self.style.WARNING("Failed outgoing events:"))
        if not failed_outgoing:
            self.stdout.write("- none")
        for item in failed_outgoing:
            self.stdout.write(
                f"- id={item['id']} endpoint={item['endpoint__name']} attempts={item['attempts']} status={item['status']}"
            )

        self.stdout.write("")
        self.stdout.write(self.style.WARNING("Dead letters:"))
        if not dead_letters:
            self.stdout.write("- none")
        for item in dead_letters:
            self.stdout.write(
                f"- id={item['id']} retries={item['retries']} reason={item['reason'][:120]}"
            )

        self.stdout.write("")
        self.stdout.write("How to resolve:")
        self.stdout.write("- Fix endpoint/secrets/handler issues first.")
        self.stdout.write("- Then replay safely with `python manage.py webhooks_replay --dead-letter-id <id> --reason <text> --dry-run`.")
