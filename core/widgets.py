import os

from django import forms


class PrivateFileInput(forms.ClearableFileInput):
    """File input that shows the current private file's name instead of a (non-existent) public link."""

    template_name = "widgets/private_file_input.html"

    def is_initial(self, value):
        return bool(value and getattr(value, "name", None))

    def format_value(self, value):
        return value if self.is_initial(value) else None

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if self.is_initial(value):
            context["widget"]["filename"] = os.path.basename(value.name)
        return context
