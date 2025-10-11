# ai_service/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from event_service.models import Event
from .utils import update_event_embedding

@receiver(post_save, sender=Event)
def auto_update_embedding(sender, instance, created, **kwargs):
    """
    Met à jour l'embedding de l'événement après chaque sauvegarde.
    """
    # On met à jour même si c'est une modification
    update_event_embedding(instance)