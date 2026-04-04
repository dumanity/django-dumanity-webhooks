from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules

class WebhooksCoreConfig(AppConfig):
    """
    Auto-descubre handlers en todas las apps instaladas.
    """
    name = "webhooks.core"

    def ready(self):
        autodiscover_modules("handlers")