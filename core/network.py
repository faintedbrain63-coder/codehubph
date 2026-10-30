"""Client IP resolution shared by login lockouts (django-axes) and rate limits."""

import ipaddress

from django.conf import settings


def client_ip(request):
    """The visitor's IP address.

    Behind Nginx (and Cloudflare Tunnel) every request reaches Gunicorn from 127.0.0.1, so with
    BEHIND_PROXY=True the address Nginx resolved from CF-Connecting-IP is read from X-Real-IP.
    Only enable it when Gunicorn is reachable solely through that proxy; otherwise clients could
    spoof the header.
    """
    remote = request.META.get("REMOTE_ADDR", "")
    if settings.BEHIND_PROXY:
        forwarded = request.META.get("HTTP_X_REAL_IP", "").strip()
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return remote
