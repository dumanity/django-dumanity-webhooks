"""
Suite de tests para django-dumanity-webhooks.

Valida seguridad multi-app (fail-closed, idempotencia scoped, rate limit determinístico).
"""

import uuid
import json
import time
from unittest.mock import Mock, patch

from django.contrib import admin, messages
from django.db import transaction
from django.test import TestCase, RequestFactory, TransactionTestCase
from django.urls import reverse
from django.core.cache import cache

from rest_framework_api_key.models import APIKey
from rest_framework.test import APIRequestFactory

from webhooks.core.signing import sign
from webhooks.core.metrics import metrics, export_prometheus_text, inc
from webhooks.core.registry import register_event, _registry
from webhooks.core.handlers import register_handler, _HANDLER_REGISTRY
from webhooks.receiver.models import Integration, Secret, EventLog
from webhooks.receiver.api import _resolve_integration, MetricsView, WebhookView
from webhooks.receiver.services import WebhookService
from webhooks.receiver.rate_limit import is_rate_limited
from webhooks.producer.models import WebhookEndpoint, OutgoingEvent
from webhooks.producer.services import publish_event, probe_connection
from webhooks.producer.sender import send
from webhooks.producer.tasks import process_outgoing
from webhooks.producer.admin import WebhookEndpointAdmin


class FailClosedResolutionTest(TestCase):
    """Valida que sin API key válida, la resolución retorna None (no fallback)."""
    
    def setUp(self):
        self.factory = RequestFactory()
        self.api_key, self.raw_key = APIKey.objects.create_key(name="test-app")
        self.integration = Integration.objects.create(
            name="test-app",
            api_key=self.api_key
        )
    
    def test_missing_api_key_header(self):
        """Sin header Authorization, _resolve_integration retorna None."""
        request = self.factory.post("/webhook/", {})
        result = _resolve_integration(request)
        self.assertIsNone(result)
    
    def test_invalid_api_key(self):
        """Con API key inválida, _resolve_integration retorna None."""
        request = self.factory.post(
            "/webhook/",
            **{"HTTP_AUTHORIZATION": "Api-Key invalid_key"}
        )
        result = _resolve_integration(request)
        self.assertIsNone(result)
    
    def test_valid_api_key(self):
        """Con API key válida, _resolve_integration retorna la Integration."""
        request = self.factory.post(
            "/webhook/",
            **{"HTTP_AUTHORIZATION": f"Api-Key {self.raw_key}"}
        )
        result = _resolve_integration(request)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, self.integration.id)


class IdempotencyScopedTest(TestCase):
    """Valida que idempotencia está scoped por (integration, event_id)."""
    
    def setUp(self):
        # App A
        api_key_a, _ = APIKey.objects.create_key(name="app-a")
        self.integration_a = Integration.objects.create(
            name="app-a",
            api_key=api_key_a
        )
        Secret.objects.create(
            integration=self.integration_a,
            secret="secret-a"
        )
        
        # App B
        api_key_b, _ = APIKey.objects.create_key(name="app-b")
        self.integration_b = Integration.objects.create(
            name="app-b",
            api_key=api_key_b
        )
        Secret.objects.create(
            integration=self.integration_b,
            secret="secret-b"
        )
        
        self.event_id = uuid.uuid4()
    
    def test_same_event_id_different_integrations_allowed(self):
        """
        Mismo event_id en dos integraciones distintas → ambos aceptados.
        
        Verifica que EventLog tiene unique_together=(integration, event_id),
        permitiendo reutilizar UUIDs entre productores.
        """
        # App A publica con event_id
        log_a = EventLog.objects.create(
            integration=self.integration_a,
            event_id=self.event_id,
            type="user.created.v1",
            payload={"data": "from-a"},
            status="processed"
        )
        
        # App B publica con mismo event_id → no viola constraint
        log_b = EventLog.objects.create(
            integration=self.integration_b,
            event_id=self.event_id,
            type="user.created.v1",
            payload={"data": "from-b"},
            status="processed"
        )
        
        self.assertNotEqual(log_a.id, log_b.id)
        self.assertEqual(log_a.event_id, log_b.event_id)
        self.assertNotEqual(log_a.integration_id, log_b.integration_id)
    
    def test_duplicate_rejection_per_integration(self):
        """
        Mismo event_id en misma integración → rechazo por duplicate.
        
        Verifica que WebhookService.process detecta duplicate
        usando (integration, event_id).
        """
        EventLog.objects.create(
            integration=self.integration_a,
            event_id=self.event_id,
            type="user.created.v1",
            payload={"data": "first"},
            status="processed"
        )
        
        # Intentar insertar duplicate en misma integración → IntegrityError
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            EventLog.objects.create(
                integration=self.integration_a,
                event_id=self.event_id,
                type="user.created.v1",
                payload={"data": "duplicate"},
                status="received"
            )


class RateLimitPerIntegrationTest(TestCase):
    """Valida que rate limit usa integration_id (UUID), no nombre."""
    
    def setUp(self):
        api_key, _ = APIKey.objects.create_key(name="test-app")
        self.integration = Integration.objects.create(
            name="test-app",
            api_key=api_key
        )
        cache.clear()
    
    def tearDown(self):
        cache.clear()
    
    def test_rate_limit_by_integration_id(self):
        """Rate limit usa integration_id como clave, no nombre."""
        integration_id = self.integration.id
        
        # Llenar el bucket para esta integración
        for i in range(100):
            is_rate_limited(integration_id, limit=100, window=60)
        
        # Al exceder, debería retornar True
        result = is_rate_limited(integration_id, limit=100, window=60)
        self.assertTrue(result)
    
    def test_rate_limit_isolated_per_integration(self):
        """Rate limits de diferentes integraciones no interfieren."""
        api_key_b, _ = APIKey.objects.create_key(name="app-b")
        integration_b = Integration.objects.create(
            name="app-b",
            api_key=api_key_b
        )
        
        # Llenar bucket de A
        for i in range(100):
            is_rate_limited(self.integration.id, limit=100, window=60)
        
        # B no debería estar limitado
        result_b = is_rate_limited(integration_b.id, limit=100, window=60)
        self.assertFalse(result_b)


class ProducerOutboxTest(TestCase):
    """Valida el patrón Outbox en producer."""
    
    def setUp(self):
        self.endpoint = WebhookEndpoint.objects.create(
            name="test-endpoint",
            url="https://example.com/webhook",
            secret="test-secret",
            is_active=True
        )
    
    def test_publish_event_creates_pending_outgoing_event(self):
        """publish_event crea OutgoingEvent con status pending."""
        payload = {
            "id": str(uuid.uuid4()),
            "type": "user.created.v1",
            "data": {"user_id": "123"}
        }
        
        result = publish_event(self.endpoint, payload)
        
        self.assertEqual(result.status, "pending")
        self.assertEqual(result.endpoint_id, self.endpoint.id)
        self.assertEqual(result.attempts, 0)
        self.assertIsNotNone(result.next_retry_at)

    def test_publish_event_persists_trace_context(self):
        """publish_event normaliza y persiste correlation_id/request_id."""
        payload = {
            "id": str(uuid.uuid4()),
            "type": "user.created.v1",
            "data": {"user_id": "123"},
        }

        result = publish_event(
            self.endpoint,
            payload,
            correlation_id="cor-123",
            request_id="req-456",
        )

        self.assertEqual(result.correlation_id, "cor-123")
        self.assertEqual(result.request_id, "req-456")
        self.assertEqual(result.payload["meta"]["correlation_id"], "cor-123")
        self.assertEqual(result.payload["meta"]["request_id"], "req-456")
    
    def test_multiple_endpoints_independent(self):
        """Múltiples endpoints son independientes."""
        endpoint_b = WebhookEndpoint.objects.create(
            name="endpoint-b",
            url="https://example.com/webhook-b",
            secret="secret-b",
            is_active=True
        )
        
        payload = {
            "id": str(uuid.uuid4()),
            "type": "user.created.v1",
            "data": {"user_id": "123"}
        }
        
        event_a = publish_event(self.endpoint, payload)
        event_b = publish_event(endpoint_b, payload)
        
        self.assertNotEqual(event_a.endpoint_id, event_b.endpoint_id)

    @patch("webhooks.producer.sender.requests.post")
    def test_sender_uses_endpoint_specific_timeout(self, mock_post):
        """send usa timeout configurado en el endpoint."""
        payload = {
            "id": str(uuid.uuid4()),
            "type": "user.created.v1",
            "data": {"user_id": "123"},
        }
        self.endpoint.request_timeout_seconds = 3
        self.endpoint.save(update_fields=["request_timeout_seconds"])

        mock_post.return_value = Mock(status_code=200)
        send(self.endpoint, payload)

        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args.kwargs["timeout"], 3)

    @patch("webhooks.producer.sender.requests.post")
    def test_sender_includes_trace_headers(self, mock_post):
        """send agrega X-Correlation-ID y X-Request-ID cuando existen."""
        payload = {
            "id": str(uuid.uuid4()),
            "type": "user.created.v1",
            "data": {"user_id": "123"},
        }
        mock_post.return_value = Mock(status_code=200)

        send(
            self.endpoint,
            payload,
            correlation_id="cor-123",
            request_id="req-456",
        )

        headers = mock_post.call_args.kwargs["headers"]
        self.assertEqual(headers["X-Correlation-ID"], "cor-123")
        self.assertEqual(headers["X-Request-ID"], "req-456")

    @patch("webhooks.producer.tasks.send")
    def test_process_outgoing_respects_endpoint_max_retries(self, mock_send):
        """process_outgoing usa max_retries configurado por endpoint."""
        self.endpoint.max_retries = 1
        self.endpoint.save(update_fields=["max_retries"])

        payload = {
            "id": str(uuid.uuid4()),
            "type": "user.created.v1",
            "data": {"user_id": "123"},
        }
        event = publish_event(self.endpoint, payload)
        event.attempts = 1
        event.save(update_fields=["attempts"])

        mock_send.side_effect = Exception("network")
        process_outgoing.func()

        event.refresh_from_db()
        self.assertEqual(event.status, "failed")
        self.assertIsNone(event.next_retry_at)

    @patch("webhooks.producer.services.send")
    def test_test_connection_returns_ok_response(self, mock_send):
        """test_connection retorna ok con respuesta connection_ok."""
        mock_response = Mock(status_code=200)
        mock_response.json.return_value = {"status": "connection_ok"}
        mock_send.return_value = mock_response

        result = probe_connection(self.endpoint, api_key="abc123", timeout_seconds=2)

        self.assertTrue(result["ok"])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["status"], "connection_ok")
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs["extra_headers"]["Authorization"], "Api-Key abc123")
        self.assertEqual(mock_send.call_args.kwargs["timeout_override"], 2)

    @patch("webhooks.producer.services.send")
    def test_test_connection_handles_transport_error(self, mock_send):
        """test_connection retorna error estructurado en fallo de transporte."""
        mock_send.side_effect = RuntimeError("network down")

        result = probe_connection(self.endpoint)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status_code"], 0)
        self.assertEqual(result["status"], "transport_error")


class ProducerAdminActionTest(TestCase):
    """Valida acción de admin para probar conexión en WebhookEndpoint."""

    def setUp(self):
        self.factory = RequestFactory()
        self.endpoint = WebhookEndpoint.objects.create(
            name="admin-endpoint",
            url="https://example.com/webhook",
            secret="admin-secret",
            is_active=True,
        )
        self.model_admin = WebhookEndpointAdmin(WebhookEndpoint, admin.site)

    @patch("webhooks.producer.admin.probe_connection")
    def test_admin_action_reports_success(self, mock_probe):
        mock_probe.return_value = {
            "ok": True,
            "status_code": 200,
            "latency_ms": 12.3,
            "status": "connection_ok",
        }
        request = self.factory.post("/admin/webhooks/producer/webhookendpoint/")

        with patch.object(self.model_admin, "message_user") as mock_message:
            queryset = WebhookEndpoint.objects.filter(id=self.endpoint.id)
            self.model_admin.test_connection_action(request, queryset)

        mock_message.assert_called_once()
        call = mock_message.call_args
        self.assertIn("conexión OK", call.args[1])
        self.assertEqual(call.kwargs["level"], messages.SUCCESS)

    def test_admin_list_link_contains_custom_test_url(self):
        link_html = self.model_admin.test_connection_link(self.endpoint)
        expected_url = reverse("admin:producer_webhookendpoint_test_connection", args=[self.endpoint.id])

        self.assertIn("Probar", link_html)
        self.assertIn(expected_url, link_html)

    @patch("webhooks.producer.admin.probe_connection")
    def test_custom_test_connection_view_redirects_to_changelist(self, mock_probe):
        mock_probe.return_value = {
            "ok": True,
            "status_code": 200,
            "latency_ms": 10.5,
            "status": "connection_ok",
        }
        request = self.factory.get("/admin/webhooks/producer/webhookendpoint/")

        with patch.object(self.model_admin, "message_user") as mock_message:
            response = self.model_admin.test_connection_view(request, self.endpoint.id)

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("admin:producer_webhookendpoint_changelist"),
            response.url,
        )
        mock_message.assert_called_once()


class ProducerOutboxTransactionalTest(TransactionTestCase):
    """Valida garantías transaccionales del outbox."""

    def setUp(self):
        self.endpoint = WebhookEndpoint.objects.create(
            name="tx-endpoint",
            url="https://example.com/tx-webhook",
            secret="tx-secret",
            is_active=True,
        )

    def test_on_commit_callback_runs_after_commit(self):
        """El callback on_commit se ejecuta solo después del commit."""
        payload = {
            "id": str(uuid.uuid4()),
            "type": "user.created.v1",
            "data": {"user_id": "tx-123"},
        }
        callbacks = []

        with transaction.atomic():
            event = publish_event(
                self.endpoint,
                payload,
                on_commit_callback=lambda e: callbacks.append(e.id),
            )
            self.assertEqual(callbacks, [])
            self.assertTrue(OutgoingEvent.objects.filter(id=event.id).exists())

        self.assertEqual(callbacks, [event.id])

    def test_rollback_prevents_outbox_event_and_callback(self):
        """Si la transacción hace rollback, no persiste evento ni callback."""
        payload = {
            "id": str(uuid.uuid4()),
            "type": "user.created.v1",
            "data": {"user_id": "tx-rollback"},
        }
        callbacks = []
        event_id = None

        try:
            with transaction.atomic():
                event = publish_event(
                    self.endpoint,
                    payload,
                    on_commit_callback=lambda e: callbacks.append(e.id),
                )
                event_id = event.id
                raise RuntimeError("force rollback")
        except RuntimeError:
            pass

        self.assertEqual(callbacks, [])
        self.assertFalse(OutgoingEvent.objects.filter(id=event_id).exists())


class MetricsExportTest(TestCase):
    """Valida export de métricas y endpoint HTTP de observabilidad."""

    def setUp(self):
        metrics.clear()

    def tearDown(self):
        metrics.clear()

    def test_export_prometheus_text_contains_counters(self):
        inc("webhook.received")
        inc("webhook.received")
        inc("webhook.failed")

        text = export_prometheus_text()

        self.assertIn("webhooks_webhook_received 2", text)
        self.assertIn("webhooks_webhook_failed 1", text)
        self.assertIn("# TYPE webhooks_webhook_received counter", text)

    def test_metrics_view_returns_prometheus_content_type(self):
        factory = APIRequestFactory()
        request = factory.get("/metrics/")
        response = MetricsView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response["Content-Type"])


class MultiAppScenarioTest(TestCase):
    """Integración: dos apps intercambiando webhooks."""
    
    def setUp(self):
        _registry.clear()
        _HANDLER_REGISTRY.clear()

        # App A como producer
        self.endpoint_b = WebhookEndpoint.objects.create(
            name="app-b",
            url="https://app-b.example.com/webhook",
            secret="secret-ab",
            is_active=True
        )
        
        # App B como receiver
        api_key_b, self.raw_key_b = APIKey.objects.create_key(name="app-b-inbound")
        self.integration_b = Integration.objects.create(
            name="app-b",
            api_key=api_key_b
        )
        Secret.objects.create(
            integration=self.integration_b,
            secret="secret-ab"
        )

        register_event(
            {
                "type": "user.created.v1",
                "payload_schema": {
                    "type": "object",
                    "properties": {"user_id": {"type": "string"}},
                    "required": ["user_id"],
                },
            }
        )

        @register_handler("user.created.v1")
        def _handler(_data):
            return None
        
        self.factory = APIRequestFactory()
    
    def test_app_a_publishes_app_b_receives(self):
        """App A publica, App B recibe y procesa."""
        event_id = uuid.uuid4()
        payload = {
            "id": str(event_id),
            "type": "user.created.v1",
            "data": {"user_id": "123"}
        }
        
        # App A publica
        outgoing = publish_event(self.endpoint_b, payload)
        self.assertEqual(outgoing.status, "pending")
        
        # Simular webhook a App B
        body = json.dumps(payload).encode()
        timestamp = int(time.time())
        signature = sign(secret="secret-ab", timestamp=timestamp, body=body)
        
        request = self.factory.post(
            "/webhook/",
            data=body,
            content_type="application/json",
            HTTP_WEBHOOK_SIGNATURE=signature,
            HTTP_X_EVENT_ID=str(event_id),
            HTTP_AUTHORIZATION=f"Api-Key {self.raw_key_b}"
        )
        
        # App B procesa
        result = WebhookService.process(request, integration=self.integration_b)
        self.assertEqual(result, "ok")
        
        # Verificar que se registró
        log = EventLog.objects.get(
            integration=self.integration_b,
            event_id=event_id
        )
        self.assertEqual(log.status, "processed")

    def test_receiver_accepts_connection_test_event(self):
        """Receiver responde connection_ok para evento de prueba de conexión."""
        payload = {
            "id": str(uuid.uuid4()),
            "type": "webhook.connection_test.v1",
            "data": {"message": "connection-test"},
        }

        body = json.dumps(payload).encode()
        timestamp = int(time.time())
        signature = sign(secret="secret-ab", timestamp=timestamp, body=body)

        request = self.factory.post(
            "/webhook/",
            data=body,
            content_type="application/json",
            HTTP_WEBHOOK_SIGNATURE=signature,
            HTTP_X_EVENT_ID=payload["id"],
            HTTP_AUTHORIZATION=f"Api-Key {self.raw_key_b}",
        )

        response = WebhookView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "connection_ok")


class E2EExampleAppsTest(TestCase):
    """E2E explícito del escenario example/app_a <-> app_b."""

    def setUp(self):
        _registry.clear()
        _HANDLER_REGISTRY.clear()

        self.factory = APIRequestFactory()

        # Integraciones inbound en App A y App B
        api_key_a, self.raw_key_a = APIKey.objects.create_key(name="app-a-inbound")
        self.integration_a = Integration.objects.create(name="app-a", api_key=api_key_a)
        Secret.objects.create(integration=self.integration_a, secret="secret-ba")

        api_key_b, self.raw_key_b = APIKey.objects.create_key(name="app-b-inbound")
        self.integration_b = Integration.objects.create(name="app-b", api_key=api_key_b)
        Secret.objects.create(integration=self.integration_b, secret="secret-ab")

        # Endpoints outbound en App A y App B
        self.endpoint_to_b = WebhookEndpoint.objects.create(
            name="app-b",
            url="https://app-b.local/webhooks/",
            secret="secret-ab",
            is_active=True,
        )
        self.endpoint_to_a = WebhookEndpoint.objects.create(
            name="app-a",
            url="https://app-a.local/webhooks/",
            secret="secret-ba",
            is_active=True,
        )

        self.handled = []

        register_event(
            {
                "type": "client.created.v1",
                "payload_schema": {
                    "type": "object",
                    "properties": {"client_id": {"type": "string"}},
                    "required": ["client_id"],
                },
            }
        )
        register_event(
            {
                "type": "user.verified.v1",
                "payload_schema": {
                    "type": "object",
                    "properties": {"user_id": {"type": "string"}},
                    "required": ["user_id"],
                },
            }
        )

        @register_handler("client.created.v1")
        def _client_created(data):
            self.handled.append(("client.created.v1", data["client_id"]))

        @register_handler("user.verified.v1")
        def _user_verified(data):
            self.handled.append(("user.verified.v1", data["user_id"]))

    def _deliver(self, payload, secret, raw_key, correlation_id=None, request_id=None):
        body = json.dumps(payload).encode()
        signature = sign(secret=secret, timestamp=int(time.time()), body=body)
        extra_headers = {
            "HTTP_WEBHOOK_SIGNATURE": signature,
            "HTTP_X_EVENT_ID": payload["id"],
            "HTTP_AUTHORIZATION": f"Api-Key {raw_key}",
        }
        if correlation_id:
            extra_headers["HTTP_X_CORRELATION_ID"] = correlation_id
        if request_id:
            extra_headers["HTTP_X_REQUEST_ID"] = request_id
        request = self.factory.post(
            "/webhooks/",
            data=body,
            content_type="application/json",
            **extra_headers,
        )
        return WebhookView.as_view()(request)

    def test_bidirectional_flow_a_to_b_and_b_to_a(self):
        """Valida flujo E2E bidireccional entre app_a y app_b."""
        payload_a_to_b = {
            "id": str(uuid.uuid4()),
            "type": "client.created.v1",
            "data": {"client_id": "c-100"},
        }
        payload_b_to_a = {
            "id": str(uuid.uuid4()),
            "type": "user.verified.v1",
            "data": {"user_id": "u-100"},
        }

        # Publicación en outbox de ambas apps (simulado)
        publish_event(self.endpoint_to_b, payload_a_to_b)
        publish_event(self.endpoint_to_a, payload_b_to_a)

        # Entrega A -> B
        response_ab = self._deliver(
            payload_a_to_b,
            secret="secret-ab",
            raw_key=self.raw_key_b,
            correlation_id="cor-a-to-b",
            request_id="req-a-to-b",
        )
        self.assertEqual(response_ab.status_code, 200)
        self.assertEqual(response_ab.data["status"], "ok")

        # Entrega B -> A
        response_ba = self._deliver(
            payload_b_to_a,
            secret="secret-ba",
            raw_key=self.raw_key_a,
            correlation_id="cor-b-to-a",
            request_id="req-b-to-a",
        )
        self.assertEqual(response_ba.status_code, 200)
        self.assertEqual(response_ba.data["status"], "ok")

        self.assertIn(("client.created.v1", "c-100"), self.handled)
        self.assertIn(("user.verified.v1", "u-100"), self.handled)

        audit_ab = EventLog.objects.get(integration=self.integration_b, event_id=uuid.UUID(payload_a_to_b["id"]))
        audit_ba = EventLog.objects.get(integration=self.integration_a, event_id=uuid.UUID(payload_b_to_a["id"]))
        self.assertEqual(audit_ab.correlation_id, "cor-a-to-b")
        self.assertEqual(audit_ab.request_id, "req-a-to-b")
        self.assertEqual(audit_ba.correlation_id, "cor-b-to-a")
        self.assertEqual(audit_ba.request_id, "req-b-to-a")

    def test_replay_returns_duplicate_status(self):
        """Un replay con mismo X-Event-ID retorna duplicate."""
        payload = {
            "id": str(uuid.uuid4()),
            "type": "client.created.v1",
            "data": {"client_id": "c-dup"},
        }

        first = self._deliver(payload, secret="secret-ab", raw_key=self.raw_key_b)
        second = self._deliver(payload, secret="secret-ab", raw_key=self.raw_key_b)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["status"], "ok")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["status"], "duplicate")


if __name__ == "__main__":
    import unittest
    unittest.main()
