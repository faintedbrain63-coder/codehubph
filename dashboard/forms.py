from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.forms.formsets import DELETION_FIELD_NAME
from django.forms.models import BaseInlineFormSet
from urllib.parse import urlsplit

from capstone.models import CapstoneMessage, CapstoneProject, CapstoneRequest
from catalog.models import Product, ProductImage
from core.models import PortfolioPresentation, PortfolioProject, PortfolioScreenshot, SiteSettings, Testimonial
from django.utils import timezone
from core.chunked_uploads import ChunkedFileInput, ChunkedUploadFormMixin


def configure_upload_fields(form, private_fields):
    for name in private_fields:
        extensions = (
            settings.ALLOWED_DOCUMENT_EXTENSIONS if name == "documentation"
            else settings.ALLOWED_PRODUCT_FILE_EXTENSIONS
        )
        form.fields[name].widget.attrs["accept"] = ",".join(f".{ext.strip('.')}" for ext in extensions)
        form.fields[name].help_text += f" Maximum upload: {settings.MAX_PRODUCT_FILE_MB} MB."
    form.fields["thumbnail"].widget.attrs["accept"] = ",".join(f".{ext}" for ext in settings.ALLOWED_IMAGE_EXTENSIONS)


class ProductForm(ChunkedUploadFormMixin, forms.ModelForm):
    chunked_fields = ("file",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configure_upload_fields(self, ("file",))

    class Meta:
        model = Product
        fields = (
            "name", "slug", "category", "short_description", "description", "features", "price",
            "version", "tech_stack", "demo_url", "thumbnail", "file", "status", "is_featured",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "features": forms.Textarea(attrs={"rows": 5, "placeholder": "Role-based login\nPDF reports\nDark mode"}),
            "file": ChunkedFileInput,
            "price": forms.NumberInput(attrs={"step": "0.01", "min": "1"}),
        }


ProductImageFormSet = inlineformset_factory(
    Product, ProductImage, fields=("image", "caption", "sort_order"), extra=1, can_delete=True, max_num=12, validate_max=True
)


class CapstoneProjectForm(ChunkedUploadFormMixin, forms.ModelForm):
    chunked_fields = ("source_code", "documentation")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configure_upload_fields(self, ("source_code", "documentation"))
        self.fields["thumbnail"].help_text = (
            "Cover image on the service card and project page. "
            f"JPG, PNG, WEBP, or GIF, up to {settings.MAX_IMAGE_MB} MB."
        )

    class Meta:
        model = CapstoneProject
        fields = (
            "title", "slug", "field", "short_description", "description", "features", "tech_stack",
            "suggested_price", "thumbnail", "source_code", "documentation", "status",
        )
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Barangay Document Request System"}),
            "slug": forms.TextInput(attrs={"placeholder": "barangay-document-request"}),
            "short_description": forms.TextInput(attrs={
                "placeholder": "Online document requests and status tracking for a barangay office.",
            }),
            "description": forms.Textarea(attrs={
                "rows": 6,
                "placeholder": (
                    "Residents file requests online. Staff review each request, and the office "
                    "tracks the document from filing to release."
                ),
            }),
            "features": forms.Textarea(attrs={
                "rows": 5,
                "placeholder": "Online request form\nStaff approval workflow\nDocument status tracking",
            }),
            "tech_stack": forms.TextInput(attrs={"placeholder": "Django, PostgreSQL, Bootstrap"}),
            "source_code": ChunkedFileInput,
            "documentation": ChunkedFileInput,
            "suggested_price": forms.NumberInput(attrs={"step": "0.01", "min": "1", "placeholder": "15000.00"}),
        }
        help_texts = {
            "title": "Public name of this service. It appears as the page title and in search results.",
            "slug": "Web address for this service. Leave blank to create it from the title. Use lowercase words separated by hyphens if you set it yourself.",
            "field": "Kind of system you are offering. Customers see this as a tag and can filter the catalog by it.",
            "short_description": "One sentence under the title and on the service card. Keep it within 220 characters.",
            "description": "Longer explanation under “About this system.” Describe who uses it and what the system does.",
            "features": "One feature or module per line. Each line becomes a checklist item on the public page.",
            "tech_stack": "Comma-separated technologies. They appear as tags on the service page and are included in search.",
            "status": "Draft stays in this workspace. Published appears on the public project services page.",
            "suggested_price": "Starting price in Philippine pesos, shown as “Starting at.” You can quote a different amount after reviewing the customer’s requirements.",
            "source_code": "Optional sample source or installer. Customers can download it only after their request is paid. Upload a custom build on each request when it is ready.",
            "documentation": "Optional manuals or thesis files, such as a PDF or Word document. Customers can download them only after payment.",
        }


class QuoteForm(forms.ModelForm):
    class Meta:
        model = CapstoneRequest
        fields = ("agreed_price", "quote_notes")
        labels = {"agreed_price": "Quoted price", "quote_notes": "What the quote includes"}
        widgets = {
            "agreed_price": forms.NumberInput(attrs={"step": "0.01", "min": "1"}),
            "quote_notes": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Included customisations, delivery timeline, number of revisions…"}
            ),
        }

    def clean_agreed_price(self):
        price = self.cleaned_data.get("agreed_price")
        if not price:
            raise forms.ValidationError("Enter the price you are quoting.")
        return price


class DeliverablesForm(ChunkedUploadFormMixin, forms.ModelForm):
    chunked_fields = ("delivered_source", "delivered_documentation")

    class Meta:
        model = CapstoneRequest
        fields = ("delivered_source", "delivered_documentation")
        widgets = {"delivered_source": ChunkedFileInput, "delivered_documentation": ChunkedFileInput}


class AdminMessageForm(forms.ModelForm):
    class Meta:
        model = CapstoneMessage
        fields = ("body",)
        labels = {"body": "Reply to customer"}
        widgets = {"body": forms.Textarea(attrs={"rows": 3})}


class RejectPaymentForm(forms.Form):
    reason = forms.CharField(
        label="Reason (shown to the customer)",
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "e.g. The reference number does not match any GCash transaction."}),
    )


class TestimonialAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.user_id and self.instance.portfolio_project_id:
            for field in ("name", "role", "rating", "message", "portfolio_project"):
                self.fields[field].disabled = True

    class Meta:
        model = Testimonial
        fields = ("name", "role", "rating", "message", "portfolio_project", "status", "is_featured")
        labels = {"name": "Customer name"}
        widgets = {"message": forms.Textarea(attrs={"rows": 5, "maxlength": 600})}


class PortfolioPresentationForm(forms.ModelForm):
    class Meta:
        model = PortfolioPresentation
        fields = ("is_visible", "eyebrow", "heading", "introduction", "display_name", "professional_title",
                  "about", "skills", "location", "github_url", "linkedin_url")
        widgets = {"introduction": forms.Textarea(attrs={"rows": 3}), "about": forms.Textarea(attrs={"rows": 5})}

    def clean(self):
        data = super().clean()
        for name in ("github_url", "linkedin_url"):
            value = data.get(name)
            parts = urlsplit(value or "")
            if value and (parts.scheme not in {"http", "https"} or parts.username or parts.password):
                self.add_error(name, "Enter an http:// or https:// link without embedded credentials.")
        return data


class PortfolioProjectForm(forms.ModelForm):
    class Meta:
        model = PortfolioProject
        fields = ("title", "slug", "project_type", "stage", "summary", "description", "industry", "contribution",
                  "project_year", "challenge", "solution", "outcome", "tech_stack", "project_url",
                  "customer", "request", "is_published", "is_featured")
        widgets = {"description": forms.Textarea(attrs={"rows": 5}),
                   "challenge": forms.Textarea(attrs={"rows": 3}), "solution": forms.Textarea(attrs={"rows": 3}),
                   "outcome": forms.Textarea(attrs={"rows": 3})}
        help_texts = {
            "slug": "Leave blank to generate from the title.",
            "project_url": "Optional for every project type, including web apps. Add a live or demo address when you have one. Use http:// or https://.",
            "is_published": "Only publish descriptions, links and screenshots you have permission to share.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = get_user_model().objects.filter(is_staff=False).order_by("email")
        self.fields["request"].queryset = CapstoneRequest.objects.filter(customer__is_staff=False).select_related("customer", "project")
        self.fields["request"].label_from_instance = lambda item: f"{item.reference} — {item.title} ({item.customer.email})"

    def clean_project_url(self):
        url = self.cleaned_data["project_url"]
        parts = urlsplit(url)
        if url and (parts.scheme not in {"https", "http"} or parts.username or parts.password):
            raise forms.ValidationError("Enter an http:// or https:// web address without embedded credentials.")
        return url

    def clean_project_year(self):
        year = self.cleaned_data.get("project_year")
        if year and year > timezone.localdate().year + 1:
            raise forms.ValidationError("Enter a past year, the current year, or next year for a planned delivery.")
        return year

    def clean(self):
        data = super().clean()
        project_request, customer = data.get("request"), data.get("customer")
        if project_request:
            if customer and customer.pk != project_request.customer_id:
                self.add_error("customer", "The selected customer must match the linked project request.")
            else:
                data["customer"] = project_request.customer
        return data


class PortfolioScreenshotForm(forms.ModelForm):
    class Meta:
        model = PortfolioScreenshot
        fields = ("image", "caption", "sort_order")
        widgets = {"image": forms.FileInput}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].widget.attrs["accept"] = ",".join(f".{ext}" for ext in settings.ALLOWED_IMAGE_EXTENSIONS)


class BasePortfolioScreenshotFormSet(BaseInlineFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        delete_field = form.fields.get(DELETION_FIELD_NAME)
        if delete_field is not None:
            delete_field.label = "Delete this picture"
            delete_field.help_text = "The image file is removed from the server when you save."

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        if self.instance.is_published and self.instance.project_type != PortfolioProject.ProjectType.WEB:
            if not any(form.cleaned_data.get("image") and not form.cleaned_data.get("DELETE") for form in self.forms):
                raise forms.ValidationError("Upload at least one screenshot before publishing a software or mobile project.")


PortfolioScreenshotFormSet = inlineformset_factory(
    PortfolioProject, PortfolioScreenshot, form=PortfolioScreenshotForm, formset=BasePortfolioScreenshotFormSet,
    extra=1, can_delete=True, max_num=12, validate_max=True,
)


class CustomerAdminForm(forms.ModelForm):
    """Staff-managed customer account. Never grants staff or superuser access."""

    password1 = forms.CharField(
        label="Password",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = get_user_model()
        fields = ("first_name", "last_name", "email", "phone_number", "school", "is_active")
        labels = {
            "phone_number": "Phone number",
            "school": "School / university",
            "is_active": "Account can sign in",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.creating = self.instance.pk is None
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["phone_number"].required = False
        self.fields["school"].required = False
        self.fields["phone_number"].widget.attrs.update({
            "autocomplete": "tel",
            "placeholder": "+63 917 000 0000",
            "inputmode": "tel",
        })
        self.fields["school"].widget.attrs.update({
            "autocomplete": "organization",
            "placeholder": "University or school name",
        })
        self.fields["is_active"].help_text = "Turn this off to block sign-in without deleting orders or project requests."
        if self.creating:
            self.fields["password1"].required = True
            self.fields["password2"].required = True
            self.fields["password1"].help_text = "At least 8 characters. Share it with the customer through a private channel."
        else:
            self.fields["password1"].help_text = "Leave blank to keep the current password."

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        taken = get_user_model().objects.filter(email__iexact=email)
        if self.instance.pk:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        data = super().clean()
        password = data.get("password1") or ""
        confirm = data.get("password2") or ""
        if self.creating or password or confirm:
            if password != confirm:
                self.add_error("password2", "The two passwords do not match.")
            elif password:
                self.instance.email = (data.get("email") or "").strip().lower()
                self.instance.first_name = data.get("first_name") or ""
                self.instance.last_name = data.get("last_name") or ""
                try:
                    validate_password(password, self.instance)
                except ValidationError as exc:
                    self.add_error("password1", exc)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = False
        user.is_superuser = False
        if user.is_active and user.email_verification_required and user.email_verified_at is None:
            user.email_verified_at = timezone.now()
        password = self.cleaned_data.get("password1")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user


class SiteSettingsForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.site_name:
            self.initial["site_name"] = self.instance.name
        self.fields["site_name"].help_text = (
            "Shown on your storefront, account pages, receipts and emails. "
            "Leave blank to use the default store name."
        )

    class Meta:
        model = SiteSettings
        fields = (
            "site_name", "tagline", "contact_email", "contact_phone", "paypal_me_url",
            "gcash_account_name", "gcash_number", "gcash_qr", "payment_instructions",
        )
        widgets = {"payment_instructions": forms.Textarea(attrs={"rows": 3})}
        labels = {"site_name": "Store name", "paypal_me_url": "PayPal.me link", "gcash_qr": "GCash QR code image"}
