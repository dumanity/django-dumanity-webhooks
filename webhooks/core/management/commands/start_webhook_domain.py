"""Scaffold command for creating a domain webhook plugin package."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError


_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _sanitize_token(value: str) -> str:
    token = value.strip().lower().replace("-", "_")
    token = re.sub(r"[^a-z0-9_]", "", token)
    token = re.sub(r"_+", "_", token).strip("_")
    return token


def _is_identifier(value: str) -> bool:
    return bool(_IDENTIFIER_RE.match(value))


def _candidate_taken(candidate: str, output_dir: Path) -> bool:
    if (output_dir / candidate).exists() or (output_dir / f"{candidate}.py").exists():
        return True

    if importlib.util.find_spec(candidate) is not None:
        return True

    for app_config in apps.get_app_configs():
        module_name = app_config.name.split(".")[-1]
        if candidate in {app_config.label, app_config.name, module_name}:
            return True

    return False


def resolve_domain_package_name(domain: str, output_dir: Path, package_name: str | None = None) -> tuple[str, bool]:
    """Resolve a safe package name, adding suffixes when collisions are detected."""
    domain_token = _sanitize_token(domain)
    if not domain_token:
        raise CommandError("Domain must contain at least one alphanumeric character")

    base = _sanitize_token(package_name) if package_name else f"{domain_token}_events"
    if not _is_identifier(base):
        raise CommandError(
            "Resolved package name is invalid. Use lowercase letters, digits and underscores, and start with a letter."
        )

    candidate = base
    attempt = 2
    while _candidate_taken(candidate, output_dir):
        candidate = f"{base}_{attempt}"
        attempt += 1

    return candidate, candidate != base


def _to_camel_case(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("_"))


def _render_files(domain: str, package_name: str) -> dict[str, str]:
    domain_token = _sanitize_token(domain)
    class_name = f"{_to_camel_case(package_name)}Config"

    return {
        "__init__.py": "",
        "apps.py": (
            "from django.apps import AppConfig\n\n"
            f"class {class_name}(AppConfig):\n"
            f"    name = \"{package_name}\"\n"
            f"    verbose_name = \"{domain_token.capitalize()} Webhook Domain\"\n\n"
            "    def ready(self):\n"
            "        from . import registry  # noqa: F401\n"
            "        from . import handlers  # noqa: F401\n"
        ),
        "events.py": (
            '"""Domain event names for webhook contracts."""\n\n'
            f"DOMAIN = \"{domain_token}\"\n\n"
            "PROFILE_PROVISIONED_V1 = f\"{DOMAIN}.profile.provisioned.v1\"\n"
            "EMAIL_VERIFIED_V1 = f\"{DOMAIN}.auth.email_verified.v1\"\n"
            "ACTION_REQUESTED_V1 = f\"{DOMAIN}.action.requested.v1\"\n"
        ),
        "handlers.py": (
            '"""Domain handlers for inbound events."""\n\n'
            "from webhooks.core.handlers import register_handler\n"
            "from . import events\n\n\n"
            "@register_handler(events.PROFILE_PROVISIONED_V1)\n"
            "def handle_profile_provisioned(data):\n"
            "    \"\"\"Handle profile provisioning confirmation from peer app.\"\"\"\n"
            "    return None\n\n\n"
            "@register_handler(events.EMAIL_VERIFIED_V1)\n"
            "def handle_email_verified(data):\n"
            "    \"\"\"Handle email verification confirmation from peer app.\"\"\"\n"
            "    return None\n"
        ),
        "registry.py": (
            '"""Domain event schema registry."""\n\n'
            "from webhooks.core.registry import register_event\n"
            "from . import events\n\n\n"
            "def register_domain_events():\n"
            "    register_event(\n"
            "        {\n"
            "            \"type\": events.PROFILE_PROVISIONED_V1,\n"
            "            \"payload_schema\": {\n"
            "                \"type\": \"object\",\n"
            "                \"properties\": {\n"
            "                    \"profile_id\": {\"type\": \"string\"},\n"
            "                    \"tenant_id\": {\"type\": \"string\"},\n"
            "                },\n"
            "                \"required\": [\"profile_id\", \"tenant_id\"],\n"
            "            },\n"
            "        }\n"
            "    )\n\n"
            "    register_event(\n"
            "        {\n"
            "            \"type\": events.EMAIL_VERIFIED_V1,\n"
            "            \"payload_schema\": {\n"
            "                \"type\": \"object\",\n"
            "                \"properties\": {\n"
            "                    \"profile_id\": {\"type\": \"string\"},\n"
            "                    \"verified_at\": {\"type\": \"string\"},\n"
            "                },\n"
            "                \"required\": [\"profile_id\", \"verified_at\"],\n"
            "            },\n"
            "        }\n"
            "    )\n\n\n"
            "register_domain_events()\n"
        ),
        "signals.py": (
            '"""Optional domain signal hooks for publishing outbound events."""\n\n'
            "# Add Django signals here if your domain needs event publication hooks.\n"
        ),
        "README.md": (
            f"# {package_name}\n\n"
            f"Scaffold generated for domain `{domain_token}`.\n\n"
            "## Next steps\n\n"
            "1. Add this package to INSTALLED_APPS.\n"
            "2. Replace sample events in events.py with domain contracts.\n"
            "3. Update schemas in registry.py.\n"
            "4. Implement handlers.py with real business logic.\n"
            "5. Run contract validation: `python manage.py webhooks_validate_contracts`.\n"
            "6. Add tests for command and event flows in your project.\n"
        ),
    }


class Command(BaseCommand):
    help = "Create a webhook domain scaffold package with collision-safe naming"

    def add_arguments(self, parser):
        parser.add_argument("domain", help="Domain name, e.g. orders, billing, notifications")
        parser.add_argument(
            "--output-dir",
            default=".",
            help="Directory where the generated package will be created (default: current directory)",
        )
        parser.add_argument(
            "--package-name",
            default=None,
            help="Optional package/module name. If omitted, uses <domain>_events",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show planned output without writing files",
        )

    def handle(self, *args, **options):
        domain = options["domain"]
        output_dir = Path(options["output_dir"]).expanduser().resolve()
        explicit_package_name = options["package_name"]
        dry_run = options["dry_run"]

        output_dir.mkdir(parents=True, exist_ok=True)

        package_name, collision_resolved = resolve_domain_package_name(
            domain=domain,
            output_dir=output_dir,
            package_name=explicit_package_name,
        )

        if collision_resolved:
            self.stdout.write(
                self.style.WARNING(
                    f"Name collision detected. Using package name '{package_name}' instead."
                )
            )

        package_dir = output_dir / package_name
        files = _render_files(domain=domain, package_name=package_name)

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"[dry-run] Package: {package_dir}"))
            for rel_path in files:
                self.stdout.write(f"[dry-run] create: {package_dir / rel_path}")
            self.stdout.write("[dry-run] next: add package to INSTALLED_APPS and run webhooks_validate_contracts")
            return

        package_dir.mkdir(parents=True, exist_ok=False)
        for rel_path, content in files.items():
            target = package_dir / rel_path
            target.write_text(content, encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Created webhook domain scaffold at: {package_dir}"))
        self.stdout.write("Next steps:")
        self.stdout.write("1) Add the generated package to INSTALLED_APPS in your Django project.")
        self.stdout.write("2) Replace sample events/schemas/handlers with your domain contracts.")
        self.stdout.write("3) Run: python manage.py webhooks_validate_contracts")
