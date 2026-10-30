from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AdminUserCreationForm, UserCreationForm
from django.utils import timezone
from django.utils.html import format_html
from django.views.decorators.debug import sensitive_variables

from core.legal import CURRENT_VERSIONS, get_document

User = get_user_model()


class SecurityEmailForm(forms.Form):
    email = forms.EmailField(
        label="Email address", max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
    )

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField(help_text="We will send a verification link to this address before you can sign in.")
    phone_number = forms.CharField(max_length=20, required=False, label="Phone number")
    school = forms.CharField(max_length=150, required=False, label="School / organization")
    accept_privacy = forms.BooleanField(
        label="I have read and agree to the Privacy Policy.",
        error_messages={"required": "You must agree to the Privacy Policy before creating an account."},
    )
    accept_license = forms.BooleanField(
        label="I agree to the Software License Agreement and Terms of Service.",
        error_messages={"required": "You must agree to the Software License Agreement before creating an account."},
    )
    privacy_version = forms.CharField(required=False, max_length=32, widget=forms.HiddenInput)
    license_version = forms.CharField(required=False, max_length=32, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone_number"].widget.attrs.update({
            "autocomplete": "tel",
            "placeholder": "+63 917 000 0000",
            "inputmode": "tel",
        })
        self.fields["school"].widget.attrs.update({
            "autocomplete": "organization",
            "placeholder": "University or school name",
        })
        self.fields["privacy_version"].initial = CURRENT_VERSIONS["privacy"]
        self.fields["license_version"].initial = CURRENT_VERSIONS["license"]
        self.fields["accept_privacy"].label = format_html(
            'I have read and agree to the <button type="button" class="legal-link" '
            'data-bs-toggle="modal" data-bs-target="#legal-privacy">Privacy Policy</button>. '
            'I explicitly consent to the use of any school or academic details I choose to provide '
            'for my account and requested project services.',
        )
        self.fields["accept_license"].label = format_html(
            'I have read and agree to the <button type="button" class="legal-link" data-bs-toggle="modal" '
            'data-bs-target="#legal-license">{}</button>. I confirm I have legal capacity and authority '
            'to accept these terms for the named client.', get_document("license")["title"],
        )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("first_name", "last_name", "email", "phone_number", "school")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Try signing in instead.")
        return email

    def clean(self):
        data = super().clean()
        if (data.get("privacy_version") != CURRENT_VERSIONS["privacy"]
                or data.get("license_version") != CURRENT_VERSIONS["license"]):
            raise forms.ValidationError(
                "The policy versions changed or this registration page has expired. "
                "Reload the page, review the documents and agree again."
            )
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = False
        user.email_verification_required = True
        user.legal_accepted_at = timezone.now()
        user.privacy_policy_version = CURRENT_VERSIONS["privacy"]
        user.license_agreement_version = CURRENT_VERSIONS["license"]
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    email = forms.EmailField(
        label="Email address", max_length=254,
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )
    password = forms.CharField(
        label="Password", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    @sensitive_variables("password")
    def clean(self):
        data = super().clean()
        email, password = data.get("email"), data.get("password")
        if email and password:
            self.user_cache = authenticate(self.request, email=email.strip().lower(), password=password)
            if self.user_cache is None or not self.user_cache.is_active:
                raise forms.ValidationError("Please enter a correct email address and password.", code="invalid_login")
        return data

    def get_user(self):
        return self.user_cache


class EmailAdminUserCreationForm(AdminUserCreationForm):
    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("email", "first_name", "last_name", "phone_number", "school")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone_number", "school")
        labels = {"phone_number": "Phone number", "school": "School / organization"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.email_verification_required:
            self.fields["email"].disabled = True
            self.fields["email"].help_text = "Your verified sign-in address. Contact support if you need to change it."
        self.fields["phone_number"].widget.attrs.update({
            "autocomplete": "tel",
            "placeholder": "+63 917 000 0000",
            "inputmode": "tel",
        })
        self.fields["school"].widget.attrs.update({
            "autocomplete": "organization",
            "placeholder": "University or school name",
        })

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This email is already used by another account.")
        return email
