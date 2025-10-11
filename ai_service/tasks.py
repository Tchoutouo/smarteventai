# ai_service/tasks.py
from celery import shared_task
from event_service.models import Event
from .utils import update_event_embedding

@shared_task
def update_all_embeddings():
    for event in Event.objects.all():
        update_event_embedding(event)