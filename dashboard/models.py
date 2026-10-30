from django.conf import settings
from django.db import models


class AIConnection(models.Model):
    provider = models.CharField(max_length=24, unique=True)
    model_name = models.CharField(max_length=200)
    encrypted_api_key = models.TextField(blank=True, editable=False)
    discovered_models = models.JSONField(default=list, blank=True, editable=False)
    models_refreshed_at = models.DateTimeField(null=True, blank=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.provider

    def set_api_key(self, value):
        from dashboard.ai.credentials import encrypt_key
        self.encrypted_api_key = encrypt_key(value)

    def get_api_key(self):
        from dashboard.ai.credentials import decrypt_key
        return decrypt_key(self.encrypted_api_key)


class AdminAISettings(models.Model):
    active_connection = models.ForeignKey(AIConnection, null=True, blank=True, on_delete=models.SET_NULL)
    is_enabled = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        return cls.objects.select_related("active_connection").get_or_create(pk=1)[0]

    @property
    def is_ready(self):
        return bool(self.is_enabled and self.active_connection and self.active_connection.encrypted_api_key)


class ConceptAnalysis(models.Model):
    """The latest AI reading of a project request's concept file, kept for the admin."""

    request = models.OneToOneField("capstone.CapstoneRequest", on_delete=models.CASCADE, related_name="concept_analysis")
    provider = models.CharField(max_length=24)
    model_name = models.CharField(max_length=200)
    summary = models.TextField()
    algorithms = models.TextField()
    cli_prompt = models.TextField("Claude CLI prompt")
    input_truncated = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    analyzed_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Analysis of {self.request_id}"
