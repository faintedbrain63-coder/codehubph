"""
Django settings for codehubph.

Every value that differs between environments is read from the `.env` file
(next to manage.py) through python-decouple. Do not hard-code secrets here.
"""

from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
SECRET_KEY = config("SECRET_KEY")
# Optional dedicated Fernet key. Otherwise AI credentials use a purpose-specific
# key derived from SECRET_KEY. Keep the chosen key with database backups.
AI_CREDENTIAL_ENCRYPTION_KEY = config("AI_CREDENTIAL_ENCRYPTION_KEY", default="")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

SITE_NAME = config("SITE_NAME", default="CodehubPh")
# Ready-made product sales are retired. Keep historical orders and downloads available.
PRODUCT_SALES_ENABLED = False
LEGAL_OWNER_NAME = config("LEGAL_OWNER_NAME", default="")
LEGAL_CONTACT_ADDRESS = config("LEGAL_CONTACT_ADDRESS", default="")
PRIVACY_CONTACT_EMAIL = config("PRIVACY_CONTACT_EMAIL", default="")
SITE_URL = config("SITE_URL", default="http://127.0.0.1:8000").rstrip("/")  # used in email links
CURRENCY = config("CURRENCY", default="PHP")
CURRENCY_SYMBOL = config("CURRENCY_SYMBOL", default="₱")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "axes",
    # Project apps
    "core",
    "accounts",
    "catalog",
    "capstone",
    "orders",
    "payments",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.visitors.VisitorCounterMiddleware",
    # Must be last: locks out repeated failed logins.
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "codehubph.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site",
                "orders.context_processors.cart",
                "dashboard.context_processors.workspace",
            ],
        },
    },
]

WSGI_APPLICATION = "codehubph.wsgi.application"

# --------------------------------------------------------------------------
# Database (PostgreSQL only)
# --------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="codehubph_db"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=60, cast=int),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "accounts.backends.EmailBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "core:home"

# django-axes: lock an account/IP pair after 5 failed logins for 30 minutes.
AXES_FAILURE_LIMIT = config("AXES_FAILURE_LIMIT", default=5, cast=int)
AXES_COOLOFF_TIME = 0.5  # hours
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_USERNAME_CALLABLE = "accounts.backends.lockout_email"
AXES_RESET_ON_SUCCESS = True
# Behind Nginx/Cloudflare Tunnel all requests come from 127.0.0.1; read the real visitor IP from X-Real-IP.
BEHIND_PROXY = config("BEHIND_PROXY", default=False, cast=bool)
AXES_CLIENT_IP_CALLABLE = "core.network.client_ip"
AXES_LOCKOUT_TEMPLATE = "accounts/locked_out.html"

# --------------------------------------------------------------------------
# Internationalization
# --------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = config("TIME_ZONE", default="Asia/Manila")
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------
# Static and media files
# --------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Public uploads: thumbnails, screenshots, GCash QR code.
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Private uploads: product files, capstone deliverables, payment proofs.
# This folder is never served by a URL; files go through permission-checked views.
PRIVATE_MEDIA_ROOT = Path(config("PRIVATE_MEDIA_ROOT", default=str(BASE_DIR / "private_media")))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

# Upload rules (sizes in megabytes)
MAX_PRODUCT_FILE_MB = config("MAX_PRODUCT_FILE_MB", default=500, cast=int)
MAX_IMAGE_MB = config("MAX_IMAGE_MB", default=5, cast=int)
ALLOWED_PRODUCT_FILE_EXTENSIONS = config(
    "ALLOWED_PRODUCT_FILE_EXTENSIONS",
    default="zip,rar,7z,tar,gz,apk,aab,ipa,exe,msi,dmg,pkg,deb,rpm,jar,pdf,docx",
    cast=Csv(),
)
ALLOWED_DOCUMENT_EXTENSIONS = config(
    "ALLOWED_DOCUMENT_EXTENSIONS", default="pdf,docx,doc,zip,pptx", cast=Csv()
)
ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "gif"]
# Concept / algorithm file a customer may attach to a project request.
MAX_CONCEPT_FILE_MB = config("MAX_CONCEPT_FILE_MB", default=20, cast=int)
ALLOWED_CONCEPT_FILE_EXTENSIONS = ["pdf", "doc", "docx", "ppt", "pptx"]
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
# Large private files (products, capstone source/docs) are sent in chunks so no single request exceeds
# proxy limits (Cloudflare: 100 MB per request). Keep Nginx client_max_body_size above this value.
UPLOAD_CHUNK_MB = config("UPLOAD_CHUNK_MB", default=8, cast=int)
UPLOAD_SESSION_HOURS = config("UPLOAD_SESSION_HOURS", default=24, cast=int)  # unfinished uploads expire
UPLOAD_MAX_ACTIVE_SESSIONS = 6  # per staff user, limits disk use by abandoned uploads

# Download access for purchased products
DOWNLOAD_LIMIT = config("DOWNLOAD_LIMIT", default=10, cast=int)  # 0 = unlimited
DOWNLOAD_EXPIRY_DAYS = config("DOWNLOAD_EXPIRY_DAYS", default=30, cast=int)  # 0 = never

# --------------------------------------------------------------------------
# Payments
# --------------------------------------------------------------------------
PAYPAL_ME_URL = config("PAYPAL_ME_URL", default="https://paypal.me/faintedbrain63")
PAYPAL_MODE = config("PAYPAL_MODE", default="manual")  # manual | automated
PAYPAL_ENV = config("PAYPAL_ENV", default="sandbox")  # sandbox | live
PAYPAL_CLIENT_ID = config("PAYPAL_CLIENT_ID", default="")
PAYPAL_SECRET = config("PAYPAL_SECRET", default="")
PAYPAL_WEBHOOK_ID = config("PAYPAL_WEBHOOK_ID", default="")
GCASH_PROVIDER = config("GCASH_PROVIDER", default="manual")  # manual | paymongo (stub)
CARD_PROVIDER = config("CARD_PROVIDER", default="paypal")  # paypal | paymongo | stripe (stubs)

# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=False, cast=bool)
EMAIL_TIMEOUT = config("EMAIL_TIMEOUT", default=15, cast=int)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default=f"{SITE_NAME} <no-reply@localhost>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
PASSWORD_RESET_TIMEOUT = config("PASSWORD_RESET_TIMEOUT", default=3600, cast=int)
EMAIL_VERIFICATION_TIMEOUT = config("EMAIL_VERIFICATION_TIMEOUT", default=86400, cast=int)
# New jobs receive an automatic background attempt after their transaction commits.
# "worker" keeps fully external delivery for installations with a supervised worker.
AUTH_EMAIL_DELIVERY_MODE = config("AUTH_EMAIL_DELIVERY_MODE", default="background")
AUTH_EMAIL_WINDOW_SECONDS = 900
AUTH_EMAIL_PER_ADDRESS = 3
AUTH_EMAIL_PER_IP = 15

# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # checkout.js reads the token for JSON POSTs
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"  # PayPal popups
X_FRAME_OPTIONS = "DENY"

if not DEBUG:
    SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=31536000, cast=int)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

MESSAGE_TAGS = {40: "danger"}  # map Django "error" to Bootstrap "danger"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO" if not DEBUG else "WARNING"},
    "loggers": {
        "payments": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
