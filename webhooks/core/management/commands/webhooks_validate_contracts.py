from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError

from webhooks.core.registry import list_events, validate_event_contract


def _event_family(event_type: str) -> str:
    return ".".join(event_type.split(".")[:-1]) if ".v" in event_type else event_type


class Command(BaseCommand):
    help = "Validate registered webhook contracts and basic version compatibility"

    def handle(self, *args, **options):
        events = list_events()
        errors: list[str] = []
        warnings: list[str] = []

        if not events:
            self.stdout.write(self.style.WARNING("No events are currently registered."))
            self.stdout.write("Tip: ensure your domain app is in INSTALLED_APPS and registry code runs in AppConfig.ready().")
            return

        families: dict[str, list[str]] = defaultdict(list)
        for event in events:
            event_type = event.get("type", "<missing>")
            contract_errors = validate_event_contract(event)
            for err in contract_errors:
                errors.append(f"{event_type}: {err}")
            families[_event_family(event_type)].append(event_type)

        for family, versions in families.items():
            normalized = sorted(versions)
            if len(normalized) > 1 and any(not item.startswith(family + ".v") for item in normalized):
                warnings.append(f"{family}: mixed naming styles detected -> {', '.join(normalized)}")

        if warnings:
            self.stdout.write(self.style.WARNING("Compatibility warnings:"))
            for warning in warnings:
                self.stdout.write(f"- {warning}")

        if errors:
            self.stdout.write(self.style.ERROR("Contract validation failed:"))
            for err in errors:
                self.stdout.write(f"- {err}")
            self.stdout.write("")
            self.stdout.write("How to resolve:")
            self.stdout.write("- Ensure each event defines `type` and `payload_schema`.")
            self.stdout.write("- Use semantic names ending in version suffix (e.g. `orders.created.v1`).")
            self.stdout.write("- Keep payload_schema.type as `object` and required as list.")
            raise CommandError(f"Found {len(errors)} invalid contract issue(s).")

        self.stdout.write(self.style.SUCCESS(f"Contracts valid: {len(events)} event(s) checked."))
