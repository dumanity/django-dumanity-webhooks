"""Minimal Django settings for local test execution."""

SECRET_KEY = "test-secret-key"
DEBUG = True
USE_TZ = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "rest_framework",
    "rest_framework_api_key",
    "webhooks.core",
    "webhooks.producer",
    "webhooks.receiver",
]

MIDDLEWARE = []
ROOT_URLCONF = "tests_urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
