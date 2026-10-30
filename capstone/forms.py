from django import forms
from django.utils import timezone

from capstone.models import CapstoneMessage, CapstoneRequest


class CapstoneRequestForm(forms.ModelForm):
    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.fields["request_title"].required = project is None
        self.fields["project_type"].required = project is None
        self.fields["client_type"].required = False
        self.fields["client_type"].initial = CapstoneRequest.ClientType.STUDENT

    def clean(self):
        data = super().clean()
        data["client_type"] = data.get("client_type") or CapstoneRequest.ClientType.STUDENT
        if self.project:
            data["request_title"] = data.get("request_title") or self.project.title
            data["project_type"] = data.get("project_type") or self.project.field
        if data["client_type"] == CapstoneRequest.ClientType.STUDENT and not data.get("program"):
            self.add_error("program", "Enter your course or program for a student capstone project.")
        return data

    class Meta:
        model = CapstoneRequest
        fields = ("client_type", "request_title", "project_type", "school_name", "program", "group_members",
                  "customization_notes", "preferred_deadline")
        widgets = {
            "group_members": forms.Textarea(attrs={"rows": 3, "placeholder": "Juan Dela Cruz\nMaria Santos"}),
            "customization_notes": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Tell us what you need to build, who will use it, the features you need "
                    "and any school, department or business requirements.",
                }
            ),
            "preferred_deadline": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_preferred_deadline(self):
        deadline = self.cleaned_data.get("preferred_deadline")
        if deadline and deadline <= timezone.localdate():
            raise forms.ValidationError("Choose a date in the future.")
        return deadline


class CapstoneMessageForm(forms.ModelForm):
    class Meta:
        model = CapstoneMessage
        fields = ("body",)
        labels = {"body": "Your message"}
        widgets = {"body": forms.Textarea(attrs={"rows": 3, "placeholder": "Write a message…"})}
