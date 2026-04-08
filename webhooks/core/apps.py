"""Configuración de la app central de django-dumanity-webhooks."""

from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class WebhooksCoreConfig(AppConfig):
    """App central del paquete.

    Auto-descubre módulos ``handlers`` en todas las apps instaladas al
    arrancar Django, y registra las verificaciones de sistema que validan
    la configuración del paquete (WEBHOOK_PROFILES, etc.).
    """

    name = "webhooks.core"
    label = "dumanity_webhooks_core"
    verbose_name = "Dumanity Webhooks Core"

    def ready(self) -> None:
        """Punto de inicialización: auto-discovery + registro de checks."""
        autodiscover_modules("handlers")
        # Importar el módulo de checks para registrarlos con Django
        from webhooks.core import checks  # noqa: F401
