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
