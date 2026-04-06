from __future__ import annotations

import uuid

from django.core.management.base import BaseCommand, CommandError
from django.utils.timezone import now

from webhooks.producer.models import OutgoingEvent, WebhookEndpoint
from webhooks.producer.services import publish_event
from webhooks.receiver.models import DeadLetter


class Command(BaseCommand):
    help = "Replay dead-letter payloads to producer outbox with idempotent-safe controls"

    def add_arguments(self, parser):
        parser.add_argument("--dead-letter-id", type=int, required=True)
        parser.add_argument("--endpoint-id", required=True, help="WebhookEndpoint UUID")
        parser.add_argument("--reason", required=True, help="Why replay is needed (for audit traceability)")
        parser.add_argument("--new-event-id", action="store_true", help="Generate a new event id for replay")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dead_letter_id = options["dead_letter_id"]
        endpoint_id = options["endpoint_id"]
        reason = options["reason"].strip()
        dry_run = options["dry_run"]

        if not reason:
            raise CommandError("--reason is required for replay traceability.")

        try:
            dead_letter = DeadLetter.objects.get(id=dead_letter_id)
        except DeadLetter.DoesNotExist as exc:
            raise CommandError(f"DeadLetter {dead_letter_id} not found.") from exc

        try:
            endpoint = WebhookEndpoint.objects.get(id=endpoint_id)
        except WebhookEndpoint.DoesNotExist as exc:
            raise CommandError(f"WebhookEndpoint {endpoint_id} not found.") from exc

        payload = dict(dead_letter.payload or {})
        if "id" not in payload:
            raise CommandError("DeadLetter payload has no 'id', cannot replay safely.")
        if "type" not in payload or "data" not in payload:
            raise CommandError("DeadLetter payload must contain 'type' and 'data'.")

        original_id = str(payload["id"])
        replay_id = str(uuid.uuid4()) if options["new_event_id"] else original_id
        payload["id"] = replay_id
        meta = dict(payload.get("meta") or {})
        meta["replay"] = {
            "source_dead_letter_id": dead_letter.id,
            "reason": reason,
            "original_event_id": original_id,
            "replay_event_id": replay_id,
        }
        payload["meta"] = meta

        duplicate_outbox = OutgoingEvent.objects.filter(
            endpoint=endpoint,
            payload__id=replay_id,
            status__in=["pending", "delivered"],
        ).exists()
        if duplicate_outbox:
            raise CommandError(
                f"Replay blocked: event id '{replay_id}' already exists in outbox for endpoint '{endpoint.name}'. "
                "Use --new-event-id for deterministic safe replay."
            )

        if dry_run:
            self.stdout.write(self.style.SUCCESS("[dry-run] Replay validated; no outbox event created."))
            self.stdout.write(f"dead_letter_id={dead_letter.id} endpoint_id={endpoint.id} replay_event_id={replay_id}")
            return

        event = publish_event(endpoint=endpoint, payload=payload)
        dead_letter.replayed_at = now()
        dead_letter.replay_reason = reason
        dead_letter.replay_event_id = replay_id
        dead_letter.save(update_fields=["replayed_at", "replay_reason", "replay_event_id"])
        self.stdout.write(self.style.SUCCESS("Replay enqueued in outbox."))
        self.stdout.write(f"outgoing_event_id={event.id} replay_event_id={replay_id}")
