"""Minimal Django settings for local test execution."""

SECRET_KEY = "example-test-secret-key"
DEBUG = True
USE_TZ = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Cache en memoria para rate limiting en tests (sin dependencias externas)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
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

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
ROOT_URLCONF = "tests_urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ──────────────────────────────────────────────────────────────────────────────
# Perfiles de webhook para tests de v2.0.0
# ──────────────────────────────────────────────────────────────────────────────
WEBHOOK_PROFILES = {
    "default": {
        "timeout": 10,
    },
    "billing": {
        "timeout": 30,
        "secret": "whsec_billing_test_secret",
        "headers": {"X-Source": "billing-service"},
        "rate_limit": {"limit": 3, "window": 60},
    },
    "fast": {
        "timeout": 2,
    },
}
