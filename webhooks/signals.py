"""Señales de ciclo de vida para django-dumanity-webhooks.

Emitidas en los puntos clave del pipeline de webhooks para que el proyecto
anfitrión pueda conectarse sin acoplarse a los internos del paquete.
Los secretos nunca se incluyen en los kwargs.

Señales disponibles
--------------------
``webhook_received``
    Webhook entrante procesado con éxito.
    kwargs: ``event_id`` (str), ``event_type`` (str), ``integration_name`` (str),
            ``trace_id`` (str|None)

``webhook_dispatched``
    Webhook saliente entregado con código 2xx.
    kwargs: ``target_url`` (str), ``event_id`` (str), ``event_type`` (str),
            ``profile`` (str), ``status_code`` (int), ``latency_ms`` (float)

``webhook_failed``
    Despacho fallido o handler entrante que lanzó excepción.
    kwargs: ``target_url`` (str|None), ``event_id`` (str), ``event_type`` (str),
            ``profile`` (str|None), ``error`` (str)

``webhook_replayed``
    Dead-letter reencolado exitosamente en el outbox.
    kwargs: ``dead_letter_id`` (int), ``replay_event_id`` (str),
            ``endpoint_name`` (str)

Uso típico::

    from django.dispatch import receiver
    from webhooks.signals import webhook_dispatched, webhook_failed

    @receiver(webhook_dispatched)
    def on_dispatched(sender, *, target_url, event_id, event_type,
                      profile, status_code, latency_ms, **kwargs):
        logger.info("Webhook despachado", extra={"status": status_code})

    @receiver(webhook_received)
    def on_received(sender, *, event_id, event_type, integration_name,
                    trace_id, **kwargs):
        logger.info("Webhook recibido", extra={"trace_id": trace_id})
"""

from django.dispatch import Signal

#: Webhook entrante procesado con éxito.
webhook_received = Signal()

#: Webhook saliente entregado con respuesta 2xx.
webhook_dispatched = Signal()

#: Fallo de despacho o error en handler entrante.
webhook_failed = Signal()

#: Dead-letter reencolado en el outbox del producer.
webhook_replayed = Signal()

__all__ = [
    "webhook_received",
    "webhook_dispatched",
    "webhook_failed",
    "webhook_replayed",
]
