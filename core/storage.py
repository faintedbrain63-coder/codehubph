"""Private file storage for files that must never be reachable by a public URL."""

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.functional import cached_property


class PrivateFileURLError(AttributeError):
    """Raised instead of returning a URL. Subclassing AttributeError lets Django's file widgets
    (which call getattr(file, "url", False)) treat private files as having no public link."""

    silent_variable_failure = True


class PrivateMediaStorage(FileSystemStorage):
    """Stores files under PRIVATE_MEDIA_ROOT and refuses to build URLs for them."""

    def __init__(self):
        super().__init__(base_url=None)

    @cached_property
    def base_location(self):
        return self._value_or_setting(self._location, settings.PRIVATE_MEDIA_ROOT)

    @cached_property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        raise PrivateFileURLError("Private files are served only through permission-checked views.")

    def _clear_cached_properties(self, setting, **kwargs):
        if setting == "PRIVATE_MEDIA_ROOT":
            self.__dict__.pop("base_location", None)
            self.__dict__.pop("location", None)
        super()._clear_cached_properties(setting, **kwargs)


private_storage = PrivateMediaStorage()


def get_private_storage():
    """Callable used by FileField(storage=...) so migrations stay environment-independent."""
    return private_storage
