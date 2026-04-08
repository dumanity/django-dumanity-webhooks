from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import AuditLog, DeadLetter, EventLog, Integration, Secret

# App label for this app (defined in apps.py) used in all admin URL name lookups.
_APP = "dumanity_webhooks_receiver"


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------

class SecretInline(admin.TabularInline):
    model = Secret
    extra = 0
    fields = ("secret_display", "is_active", "expires_at")
    readonly_fields = ("secret_display",)
    can_delete = False

    @admin.display(description="Secret (parcial)")
    def secret_display(self, obj):
        if obj.pk and obj.secret:
            return f"{obj.secret[:8]}…[REDACTED]"
        return "—"


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

@admin.register(Integration)
class IntegrationAdmin(admin.ModelAdmin):
    list_display = ("name", "active_secrets_count", "rotate_secret_link", "bootstrap_new_link")
    inlines = [SecretInline]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:integration_id>/rotate-secret/",
                self.admin_site.admin_view(self.rotate_secret_view),
                name=f"{_APP}_integration_rotate_secret",
            ),
            path(
                "bootstrap/",
                self.admin_site.admin_view(self.bootstrap_view),
                name=f"{_APP}_integration_bootstrap",
            ),
        ]
        return custom_urls + urls

    @admin.display(description="Secretos activos")
    def active_secrets_count(self, obj):
        return Secret.objects.filter(
            integration=obj,
            is_active=True,
            expires_at__gt=timezone.now(),
        ).count()

    @admin.display(description="Rotar secreto")
    def rotate_secret_link(self, obj):
        url = reverse(f"admin:{_APP}_integration_rotate_secret", args=[obj.pk])
        return format_html('<a class="button" href="{}">Rotar secreto</a>', url)

    @admin.display(description="Nueva integración")
    def bootstrap_new_link(self, obj):
        url = reverse(f"admin:{_APP}_integration_bootstrap")
        return format_html('<a href="{}">Bootstrap</a>', url)

    def rotate_secret_view(self, request, integration_id):
        integration = get_object_or_404(Integration, pk=integration_id)
        new_secret = f"whsec_{secrets.token_urlsafe(24)}"
        expires_at = timezone.now() + timedelta(days=30)
        Secret.objects.create(
            integration=integration,
            secret=new_secret,
            is_active=True,
            expires_at=expires_at,
        )
        self.message_user(
            request,
            (
                f"[{integration.name}] Nuevo secreto creado. "
                f"Prefijo: {new_secret[:8]}…  "
                f"Copia el valor completo desde la sección de Secretos y guárdalo en vault."
            ),
            level=messages.WARNING,
        )
        return redirect(reverse(f"admin:{_APP}_integration_changelist"))

    def bootstrap_view(self, request):
        from .services import bootstrap_receiver

        if request.method == "POST":
            integration_name = request.POST.get("integration_name", "").strip()
            shared_secret = request.POST.get("shared_secret", "").strip() or None
            try:
                expires_days = int(request.POST.get("expires_days", 30))
            except (ValueError, TypeError):
                expires_days = 30

            if not integration_name:
                self.message_user(
                    request,
                    "El nombre de integración es obligatorio.",
                    level=messages.ERROR,
                )
                return redirect(reverse(f"admin:{_APP}_integration_bootstrap"))

            result = bootstrap_receiver(
                integration_name=integration_name,
                shared_secret=shared_secret,
                expires_days=expires_days,
            )

            if result["api_key_plaintext"]:
                self.message_user(
                    request,
                    format_html(
                        "<strong>[{}] Integración creada.</strong> "
                        "Guarda en vault (se muestra UNA sola vez):<br>"
                        "• RECEIVER_API_KEY: <code>{}</code><br>"
                        "• WEBHOOK_SHARED_SECRET: <code>{}</code>",
                        result["integration"].name,
                        result["api_key_plaintext"],
                        result["secret"],
                    ),
                    level=messages.SUCCESS,
                )
            else:
                self.message_user(
                    request,
                    format_html(
                        "<strong>[{}] Integración reutilizada.</strong> "
                        "Nuevo secreto añadido: <code>{}</code><br>"
                        "La API key existente no puede recuperarse.",
                        result["integration"].name,
                        result["secret"],
                    ),
                    level=messages.WARNING,
                )

            return redirect(reverse(f"admin:{_APP}_integration_changelist"))

        context = {
            **self.admin_site.each_context(request),
            "title": "Bootstrap nueva integración (Receiver)",
            "opts": self.model._meta,
        }
        return render(request, "admin/dumanity_webhooks_receiver/integration/bootstrap.html", context)


# ---------------------------------------------------------------------------
# Secret
# ---------------------------------------------------------------------------

@admin.register(Secret)
class SecretAdmin(admin.ModelAdmin):
    list_display = ("id", "integration", "secret_display", "is_active", "expires_at")
    list_filter = ("is_active", "integration")
    readonly_fields = ("secret_display",)
    fields = ("integration", "secret_display", "is_active", "expires_at")
    actions = ["deactivate_secrets"]

    @admin.display(description="Secret (parcial)")
    def secret_display(self, obj):
        if obj.secret:
            return f"{obj.secret[:8]}…[REDACTED]"
        return "—"

    @admin.action(description="Desactivar secretos seleccionados")
    def deactivate_secrets(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} secreto(s) desactivado(s).", level=messages.SUCCESS)


# ---------------------------------------------------------------------------
# EventLog
# ---------------------------------------------------------------------------

@admin.register(EventLog)
class EventLogAdmin(admin.ModelAdmin):
    list_display = ("event_id", "integration", "type", "status", "correlation_id", "request_id")
    list_filter = ("status", "integration", "type")
    search_fields = ("event_id", "correlation_id", "request_id")
    readonly_fields = (
        "integration", "event_id", "correlation_id",
        "request_id", "type", "payload", "status",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# DeadLetter
# ---------------------------------------------------------------------------

@admin.register(DeadLetter)
class DeadLetterAdmin(admin.ModelAdmin):
    list_display = ("id", "reason_short", "retries", "replay_status_display", "replayed_at")
    list_filter = [("replayed_at", admin.EmptyFieldListFilter)]
    search_fields = ("reason", "correlation_id", "request_id")
    readonly_fields = (
        "payload", "reason", "retries",
        "correlation_id", "request_id",
        "replayed_at", "replay_reason", "replay_event_id",
    )
    actions = ["replay_to_outbox"]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:dead_letter_id>/replay/",
                self.admin_site.admin_view(self.replay_view),
                name=f"{_APP}_deadletter_replay",
            ),
        ]
        return custom_urls + urls

    @admin.display(description="Razón")
    def reason_short(self, obj):
        return (obj.reason or "")[:80]

    @admin.display(description="Estado replay")
    def replay_status_display(self, obj):
        if obj.replayed_at:
            return format_html('<span style="color:gray">Ya replayado</span>')
        url = reverse(f"admin:{_APP}_deadletter_replay", args=[obj.pk])
        return format_html('<a class="button" href="{}">Replay</a>', url)

    def replay_view(self, request, dead_letter_id):
        from webhooks.producer.models import OutgoingEvent, WebhookEndpoint
        from webhooks.producer.services import publish_event

        dead_letter = get_object_or_404(DeadLetter, pk=dead_letter_id)

        if request.method == "POST":
            endpoint_id = request.POST.get("endpoint_id", "").strip()
            reason = request.POST.get("reason", "").strip()
            use_new_id = request.POST.get("new_event_id") == "1"

            if not endpoint_id or not reason:
                self.message_user(
                    request,
                    "Endpoint y razón son obligatorios.",
                    level=messages.ERROR,
                )
                return redirect(reverse(f"admin:{_APP}_deadletter_replay", args=[dead_letter_id]))

            if dead_letter.replayed_at:
                self.message_user(
                    request,
                    "Este DeadLetter ya fue replayado anteriormente.",
                    level=messages.ERROR,
                )
                return redirect(reverse(f"admin:{_APP}_deadletter_changelist"))

            try:
                endpoint = WebhookEndpoint.objects.get(id=endpoint_id)
            except (WebhookEndpoint.DoesNotExist, Exception):
                self.message_user(
                    request,
                    f"Endpoint '{endpoint_id}' no encontrado.",
                    level=messages.ERROR,
                )
                return redirect(reverse(f"admin:{_APP}_deadletter_replay", args=[dead_letter_id]))

            payload = dict(dead_letter.payload or {})
            if "id" not in payload or "type" not in payload or "data" not in payload:
                self.message_user(
                    request,
                    "Payload del DeadLetter incompleto (requiere id, type, data).",
                    level=messages.ERROR,
                )
                return redirect(reverse(f"admin:{_APP}_deadletter_changelist"))

            original_id = str(payload["id"])
            replay_id = str(uuid.uuid4()) if use_new_id else original_id
            payload["id"] = replay_id
            meta = dict(payload.get("meta") or {})
            meta["replay"] = {
                "source_dead_letter_id": dead_letter.id,
                "reason": reason,
                "original_event_id": original_id,
                "replay_event_id": replay_id,
            }
            payload["meta"] = meta

            if OutgoingEvent.objects.filter(endpoint=endpoint, payload__id=replay_id).exists():
                self.message_user(
                    request,
                    f"El event_id '{replay_id}' ya existe en el outbox. "
                    "Marca 'Generar nuevo event ID' para replay seguro.",
                    level=messages.ERROR,
                )
                return redirect(reverse(f"admin:{_APP}_deadletter_replay", args=[dead_letter_id]))

            event = publish_event(endpoint=endpoint, payload=payload)
            dead_letter.replayed_at = timezone.now()
            dead_letter.replay_reason = reason
            dead_letter.replay_event_id = replay_id
            dead_letter.save(update_fields=["replayed_at", "replay_reason", "replay_event_id"])

            self.message_user(
                request,
                format_html(
                    "Replay encolado. outgoing_event_id=<code>{}</code> "
                    "replay_event_id=<code>{}</code>",
                    event.id,
                    replay_id,
                ),
                level=messages.SUCCESS,
            )
            return redirect(reverse(f"admin:{_APP}_deadletter_changelist"))

        endpoints = WebhookEndpoint.objects.filter(is_active=True).order_by("name")
        context = {
            **self.admin_site.each_context(request),
            "title": f"Replay DeadLetter #{dead_letter_id}",
            "dead_letter": dead_letter,
            "endpoints": endpoints,
            "opts": self.model._meta,
        }
        return render(request, "admin/dumanity_webhooks_receiver/deadletter/replay.html", context)

    @admin.action(description="Replay seleccionados al outbox (nuevo event ID automático)")
    def replay_to_outbox(self, request, queryset):
        from webhooks.producer.models import WebhookEndpoint
        from webhooks.producer.services import publish_event

        endpoints = WebhookEndpoint.objects.filter(is_active=True).order_by("name")
        if not endpoints.exists():
            self.message_user(
                request,
                "No hay endpoints activos configurados.",
                level=messages.ERROR,
            )
            return

        endpoint = endpoints.first()
        skipped = 0
        enqueued = 0
        for dl in queryset:
            if dl.replayed_at:
                skipped += 1
                continue
            payload = dict(dl.payload or {})
            if "id" not in payload or "type" not in payload or "data" not in payload:
                skipped += 1
                continue
            original_id = str(payload["id"])
            replay_id = str(uuid.uuid4())
            payload["id"] = replay_id
            meta = dict(payload.get("meta") or {})
            meta["replay"] = {
                "source_dead_letter_id": dl.id,
                "reason": "bulk replay from admin",
                "original_event_id": original_id,
                "replay_event_id": replay_id,
            }
            payload["meta"] = meta
            publish_event(endpoint=endpoint, payload=payload)
            dl.replayed_at = timezone.now()
            dl.replay_reason = "bulk replay from admin"
            dl.replay_event_id = replay_id
            dl.save(update_fields=["replayed_at", "replay_reason", "replay_event_id"])
            enqueued += 1

        self.message_user(
            request,
            f"{enqueued} evento(s) replayado(s) al endpoint '{endpoint.name}'. "
            f"{skipped} omitido(s) (ya replayados o payload incompleto).",
            level=messages.SUCCESS if enqueued else messages.WARNING,
        )


# ---------------------------------------------------------------------------
# AuditLog
# ---------------------------------------------------------------------------

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("event_id", "integration", "correlation_id", "request_id", "created_at")
    search_fields = ("event_id", "integration", "correlation_id", "request_id")
    readonly_fields = (
        "event_id", "integration", "correlation_id",
        "request_id", "request_headers", "created_at",
    )
    list_filter = ("integration",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
