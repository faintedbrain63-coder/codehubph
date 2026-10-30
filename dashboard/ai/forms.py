from django import forms

from dashboard.ai.providers import PROVIDERS, endpoint_for_model


class AIConnectionForm(forms.Form):
    provider = forms.ChoiceField(label="AI provider", choices=[(key, item["label"]) for key, item in PROVIDERS.items()])
    endpoint = forms.CharField(label="API endpoint", required=False, disabled=True)
    model_name = forms.RegexField(label="Model", max_length=200,
        regex=r"\A[A-Za-z0-9][A-Za-z0-9._:/+\-]*\Z",
        widget=forms.TextInput(attrs={"autocomplete": "off", "spellcheck": "false", "autocapitalize": "none"}),
        error_messages={"invalid": "Enter a model ID using letters, numbers, dots, hyphens, underscores, slashes, colons or plus signs."},
        help_text="Enter the exact API model ID. You can use the frontier default or any model your API account supports.")
    api_key = forms.CharField(label="API key", required=False, max_length=2000,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "spellcheck": "false"}),
        help_text="Stored encrypted. Leave blank to keep this provider's saved key.")
    is_enabled = forms.BooleanField(label="Use this connection for the admin chatbot", required=False)

    def __init__(self, *args, provider, connection=None, active=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.connection = connection
        model = connection.model_name if connection else PROVIDERS[provider]["default_model"]
        self.initial.update(provider=provider, endpoint=endpoint_for_model(provider, model),
                            model_name=model,
                            is_enabled=active)

    def clean_api_key(self):
        value = self.cleaned_data.get("api_key", "").strip()
        if value and (any(c.isspace() for c in value) or not value.isascii() or len(value) < 10):
            raise forms.ValidationError("Enter a valid API key without spaces or line breaks.")
        return value

    def clean(self):
        data = super().clean()
        if data.get("is_enabled") and not data.get("api_key") and not (self.connection and self.connection.encrypted_api_key):
            self.add_error("api_key", "Enter an API key to enable this connection.")
        return data
