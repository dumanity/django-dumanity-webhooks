"""Helper Pydantic para el envelope canónico de eventos.

Requiere Pydantic v2::

    pip install django-dumanity-webhooks[pydantic]

Ejemplo::

    from webhooks.contrib.pydantic import CanonicalEventEnvelope
    from webhooks.producer.dispatch import dispatch_webhook_sync

    envelope = CanonicalEventEnvelope(
        type="orders.created.v1",
        data={"order_id": "ord-123"},
    )
    dispatch_webhook_sync(envelope, "https://partner.example.com/webhooks/")
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

try:
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "webhooks.contrib.pydantic requiere pydantic>=2.0. "
        "Instálalo con: pip install django-dumanity-webhooks[pydantic]"
    ) from exc


class CanonicalEventEnvelope(BaseModel):
    """Envelope canónico para eventos de webhook.

    Args:
        id:          UUID único del evento (generado automáticamente).
        type:        Nombre canónico del evento (ej. ``"orders.created.v1"``).
        trace_id:    ID de traza distribuida (opcional).
        occurred_at: Momento UTC del evento (por defecto: ahora).
        data:        Payload de negocio libre.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str
    trace_id: str | None = None
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    data: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}
