# ai_service/utils.py
from .embedding import generate_embedding
from .models import EventEmbedding
from event_service.models import Event

def update_event_embedding(event: Event):
    text = f"{event.title}. {event.description}"
    vector = generate_embedding(text)
    obj, created = EventEmbedding.objects.update_or_create(
        event=event,
        defaults={'vector': vector}
    )
    return obj