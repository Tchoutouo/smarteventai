# ai_service/models.py
from django.db import models
from event_service.models import Event

class EventEmbedding(models.Model):
    event = models.OneToOneField(Event, on_delete=models.CASCADE, related_name='embedding')
    vector = models.JSONField()  # Stocke le vecteur comme liste de floats
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Embedding for {self.event.title}"