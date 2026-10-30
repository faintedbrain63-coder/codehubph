import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class AIError(Exception):
    """Safe, user-facing error; never include provider response bodies or keys."""


def _cipher():
    key = settings.AI_CREDENTIAL_ENCRYPTION_KEY or base64.urlsafe_b64encode(
        hashlib.sha256(("codehubph/admin-ai/credentials/v1:" + settings.SECRET_KEY).encode()).digest()
    )
    try:
        return Fernet(key)
    except (ValueError, TypeError):
        raise AIError("The server's AI credential encryption key is invalid. Contact the site administrator.") from None


def encrypt_key(value):
    return _cipher().encrypt(value.encode()).decode() if value else ""


def decrypt_key(value):
    if not value:
        return ""
    try:
        return _cipher().decrypt(value.encode()).decode()
    except (InvalidToken, UnicodeError):
        raise AIError("This API key cannot be decrypted. Re-enter it in AI connection settings.") from None
