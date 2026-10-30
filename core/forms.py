from django import forms

from core.models import ContactMessage, Testimonial


class ContactForm(forms.ModelForm):
    # Hidden honeypot field: real visitors leave it empty, simple bots fill it in.
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = ContactMessage
        fields = ("name", "email", "subject", "message")
        labels = {"name": "Your name", "email": "Email address"}
        widgets = {"message": forms.Textarea(attrs={"rows": 4})}

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam detected.")
        return ""


class TestimonialForm(forms.ModelForm):
    """What a customer fills in to leave a comment. Name and status are set by the view."""

    class Meta:
        model = Testimonial
        fields = ("rating", "message", "role")
        labels = {"rating": "Your rating", "message": "Your comment", "role": "School or company (optional)"}
        widgets = {
            "message": forms.Textarea(
                attrs={
                    "rows": 5,
                    "maxlength": 600,
                    "placeholder": "Tell us about the project, how it helps you, and your experience with our support.",
                }
            ),
        }

    def clean_message(self):
        message = self.cleaned_data["message"].strip()
        if len(message) < 20:
            raise forms.ValidationError("Please write at least 20 characters so other customers find it helpful.")
        return message


class ProjectTestimonialForm(TestimonialForm):
    publication_permission = forms.BooleanField(
        label="I give permission to publish this review, my chosen display name and optional role with this project on the portfolio and home page.",
        error_messages={"required": "Please give publication permission before submitting a public project review."},
    )

    class Meta(TestimonialForm.Meta):
        fields = ("name", "rating", "message", "role")
        labels = {**TestimonialForm.Meta.labels, "name": "Public display name"}
        help_texts = {"name": "Use the name or initials you want shown publicly."}
