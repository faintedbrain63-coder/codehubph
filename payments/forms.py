from django import forms
from django.core.validators import RegexValidator

from core.validators import IMAGE_VALIDATORS

reference_validator = RegexValidator(
    r"^[A-Za-z0-9\- ]{6,40}$", "Use only letters, numbers and dashes (6 to 40 characters)."
)


class ManualPaymentForm(forms.Form):
    provider_reference = forms.CharField(max_length=40, validators=[reference_validator])
    proof_image = forms.ImageField(required=False, validators=IMAGE_VALIDATORS)
    confirm = forms.BooleanField(
        label="I sent the exact amount and included the reference in my payment notes.", required=True
    )

    def __init__(self, *args, provider, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider = provider
        self.fields["provider_reference"].label = provider.reference_label
        self.fields["provider_reference"].help_text = provider.reference_help
        self.fields["proof_image"].label = provider.proof_label + ("" if provider.requires_proof else " (optional)")
        self.fields["proof_image"].required = provider.requires_proof
        self.fields["proof_image"].widget.attrs["accept"] = "image/png,image/jpeg,image/webp"
        self.prefix = provider.method

    def clean_provider_reference(self):
        reference = self.cleaned_data["provider_reference"].strip().upper()
        if self.provider.method == "gcash" and (len(reference) != 13 or not reference.isascii() or not reference.isdigit()):
            raise forms.ValidationError("Enter the 13-digit reference number shown on your GCash receipt.")
        return reference
