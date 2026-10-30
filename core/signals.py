"""Remove portfolio image files only after a successful database deletion/replacement."""
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from core.models import PortfolioScreenshot


def delete_unused_image(storage, name):
    if name and not PortfolioScreenshot.objects.filter(image=name).exists():
        storage.delete(name)


@receiver(pre_save, sender=PortfolioScreenshot)
def remember_previous_image(sender, instance, **kwargs):
    instance._previous_image = sender.objects.filter(pk=instance.pk).values_list("image", flat=True).first() if instance.pk else None


@receiver(post_save, sender=PortfolioScreenshot)
def remove_replaced_image(sender, instance, **kwargs):
    previous = getattr(instance, "_previous_image", None)
    if previous and previous != instance.image.name:
        transaction.on_commit(lambda: delete_unused_image(instance.image.storage, previous))


@receiver(post_delete, sender=PortfolioScreenshot)
def remove_deleted_image(sender, instance, **kwargs):
    storage, name = instance.image.storage, instance.image.name
    transaction.on_commit(lambda: delete_unused_image(storage, name))
