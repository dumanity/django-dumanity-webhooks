"""
Procesamiento asíncrono de eventos salientes (retry con backoff).

Implementa la garantía de "entrega eventual" del patrón Outbox.
Los eventos se procesan en lotes, sin bloqueos de red.
"""
from datetime import timedelta

from django.db.models import Q
from django.tasks import task
from django.utils.timezone import now

from .models import OutgoingEvent
from .sender import send

@task
def process_outgoing():
    """
    Procesa lote de eventos salientes pendientes con retry automático.
    
    Busca eventos con status="pending" y next_retry_at <= now(),
    intenta enviar a cada endpoint, y programa reintentos con backoff
    exponencial si fallan.
    
    Algoritmo:
        1. Busca hasta 50 eventos pendientes elegibles por timestamp
        2. Para cada evento:
           a. Intenta enviar HTTP POST firmado
           b. Si 2xx → status="delivered", next_retry_at=NULL
           c. Si error → incrementa attempts
        3. Si attempts > MAX_ATTEMPTS → status="failed" (sin reintento)
        4. Si error y attempts <= MAX_ATTEMPTS → programa retry
           - delay = 2 ** attempts segundos (1, 2, 4, 8, 16, ...)
           - next_retry_at = now() + delay

    Backoff schedule:
        Attempt 1: 2^1 = 2s
        Attempt 2: 2^2 = 4s
        Attempt 3: 2^3 = 8s
        Attempt 4: 2^4 = 16s
        Attempt 5: 2^5 = 32s
        Attempt 6: FAILED (no más reintentos)

    Guarantees:
        - No bloquea: usa timestamps, no sleep
        - Eventual delivery para eventos no fallidos
        - Exponential backoff para evitar sobrecarga
        - Escalable: procesa en lotes de 50

    Operation:
        Scheduler externo debe ejecutar esta tarea periodicamente:
        - Celery beat, APScheduler, Django management command, etc.
        - Recomendado: cada 1-5 minutos

    Example:
        # En settings.py con Celery
        from celery.schedules import schedule
        app.conf.beat_schedule = {
            'process-outgoing': {
                'task': 'webhooks.producer.tasks.process_outgoing',
                'schedule': schedule(run_every=timedelta(minutes=1)),
            },
        }
    """
    events = OutgoingEvent.objects.filter(
        status="pending"
    ).filter(
        Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now())
    )[:50]

    for e in events:
        try:
            res = send(e.endpoint, e.payload)

            if res.status_code < 300:
                e.status = "delivered"
                e.next_retry_at = None
            else:
                raise Exception()

        except Exception:
            e.attempts += 1

            if e.attempts > e.endpoint.max_retries:
                e.status = "failed"
                e.next_retry_at = None
            else:
                delay = 2 ** e.attempts
                e.next_retry_at = now() + timedelta(seconds=delay)

        e.save()