from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html

from .models import OutgoingEvent, WebhookEndpoint
from .services import probe_connection


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "url",
        "is_active",
        "max_retries",
        "request_timeout_seconds",
        "test_connection_link",
    )
    actions = ["test_connection_action"]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<uuid:endpoint_id>/test-connection/",
                self.admin_site.admin_view(self.test_connection_view),
                name="producer_webhookendpoint_test_connection",
            )
        ]
        return custom_urls + urls

    @admin.display(description="Conectividad")
    def test_connection_link(self, obj):
        url = reverse("admin:producer_webhookendpoint_test_connection", args=[obj.id])
        return format_html('<a class="button" href="{}">Probar</a>', url)

    def _emit_connection_result_message(self, request, endpoint, result):
        if result.get("ok"):
            self.message_user(
                request,
                (
                    f"[{endpoint.name}] conexión OK "
                    f"status={result.get('status_code')} "
                    f"latency_ms={result.get('latency_ms')}"
                ),
                level=messages.SUCCESS,
            )
        else:
            detail = result.get("error") or result.get("status")
            self.message_user(
                request,
                (
                    f"[{endpoint.name}] conexión falló "
                    f"status={result.get('status_code')} detail={detail}"
                ),
                level=messages.ERROR,
            )

    def test_connection_view(self, request, endpoint_id):
        endpoint = get_object_or_404(WebhookEndpoint, id=endpoint_id)
        result = probe_connection(endpoint=endpoint)
        self._emit_connection_result_message(request, endpoint, result)
        changelist_url = reverse(
            f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"
        )
        return redirect(changelist_url)

    @admin.action(description="Probar conexión al receiver")
    def test_connection_action(self, request, queryset):
        for endpoint in queryset:
            result = probe_connection(endpoint=endpoint)
            self._emit_connection_result_message(request, endpoint, result)


@admin.register(OutgoingEvent)
class OutgoingEventAdmin(admin.ModelAdmin):
    list_display = ("id", "endpoint", "status", "attempts", "next_retry_at")
    list_filter = ("status", "endpoint")
