from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from webhooks.producer.models import WebhookEndpoint
from webhooks.receiver.services import bootstrap_receiver


class Command(BaseCommand):
    help = "Bootstrap receiver/producer webhook resources with secure defaults"

    def add_arguments(self, parser):
        parser.add_argument("--integration-name", default="producer-a")
        parser.add_argument("--endpoint-name", default="receiver-a")
        parser.add_argument("--endpoint-url", default="https://receiver.example.com/webhooks/")
        parser.add_argument("--secret", default=None, help="Shared webhook secret. If omitted, generated automatically.")
        parser.add_argument("--expires-days", type=int, default=30)
        parser.add_argument("--receiver-only", action="store_true")
        parser.add_argument("--producer-only", action="store_true")
        parser.add_argument(
            "--update-endpoint",
            action="store_true",
            help="If endpoint exists, update url/secret/is_active with provided values.",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        receiver_only = options["receiver_only"]
        producer_only = options["producer_only"]
        dry_run = options["dry_run"]

        if receiver_only and producer_only:
            raise CommandError("Use only one of --receiver-only or --producer-only")
        if options["expires_days"] <= 0:
            raise CommandError("--expires-days must be >= 1")

        create_receiver = not producer_only
        create_producer = not receiver_only

        result = {
            "integration": None,
            "api_key_plaintext": None,
            "secret": options["secret"],
            "endpoint": None,
            "integration_reused": False,
            "endpoint_reused": False,
        }

        if create_receiver:
            if dry_run:
                from webhooks.receiver.models import Integration
                from django.utils.timezone import now
                from datetime import timedelta
                existing_integration = Integration.objects.filter(name=options["integration_name"]).first()
                expires_at = now() + timedelta(days=options["expires_days"])
                label = "existing" if existing_integration else "new"
                self.stdout.write(
                    f"[dry-run] receiver integration='{options['integration_name']}' ({label}) secret_expires_at='{expires_at.isoformat()}'"
                )
            else:
                bootstrap_result = bootstrap_receiver(
                    integration_name=options["integration_name"],
                    shared_secret=options["secret"],
                    expires_days=options["expires_days"],
                )
                result["integration"] = bootstrap_result["integration"]
                result["api_key_plaintext"] = bootstrap_result["api_key_plaintext"]
                result["secret"] = bootstrap_result["secret"]
                result["integration_reused"] = bootstrap_result["integration_reused"]

        if create_producer:
            shared_secret = result["secret"]
            if dry_run:
                self.stdout.write(
                    f"[dry-run] producer endpoint='{options['endpoint_name']}' url='{options['endpoint_url']}'"
                )
            else:
                endpoint, endpoint_created = WebhookEndpoint.objects.get_or_create(
                    name=options["endpoint_name"],
                    defaults={
                        "url": options["endpoint_url"],
                        "secret": shared_secret,
                        "is_active": True,
                    },
                )
                if not endpoint_created:
                    result["endpoint_reused"] = True
                    if options["update_endpoint"]:
                        endpoint.url = options["endpoint_url"]
                        endpoint.secret = shared_secret
                        endpoint.is_active = True
                        endpoint.save(update_fields=["url", "secret", "is_active"])
                result["endpoint"] = endpoint

        status = "Bootstrap completed (dry-run)." if dry_run else "Bootstrap completed."
        self.stdout.write(self.style.SUCCESS(status))
        self.stdout.write("Store these values in your vault (do NOT commit):")
        self.stdout.write(f"- WEBHOOK_SHARED_SECRET: {result['secret']}")
        if result["api_key_plaintext"]:
            self.stdout.write(f"- RECEIVER_API_KEY: {result['api_key_plaintext']}")
            self.stdout.write("  (shown once; rotate if exposed)")
        elif result["integration_reused"]:
            self.stdout.write("- RECEIVER_API_KEY: [existing integration reused; plaintext key cannot be recovered]")
            self.stdout.write("  Action: rotate/create key if you do not have it stored in vault.")
        else:
            self.stdout.write("- RECEIVER_API_KEY: [not generated in this mode]")

        if result["endpoint_reused"] and not options["update_endpoint"]:
            self.stdout.write("- ENDPOINT_UPDATE: skipped (existing endpoint kept unchanged)")
            self.stdout.write("  Tip: rerun with --update-endpoint to align URL/secret.")
        self.stdout.write("")
        self.stdout.write("Next steps:")
        self.stdout.write("1) Configure producer endpoint with this shared secret.")
        self.stdout.write("2) Configure receiver integration API key in caller.")
        self.stdout.write("3) Run a connection test with `webhooks-info test-endpoint`.")
