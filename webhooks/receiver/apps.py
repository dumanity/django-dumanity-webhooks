from django.apps import AppConfig


class WebhooksReceiverConfig(AppConfig):
    name = "webhooks.receiver"
    label = "dumanity_webhooks_receiver"
    verbose_name = "Webhooks Receiver"
