# ai_service/recommender.py
from .embedding import cosine_similarity
from .models import EventEmbedding
from event_service.models import Event

def get_recommendations_for_event(event: Event, top_k=5):
    try:
        target_embedding = event.embedding.vector
    except EventEmbedding.DoesNotExist:
        return Event.objects.none()

    candidates = EventEmbedding.objects.exclude(event=event).select_related('event')
    similarities = []

    for emb in candidates:
        score = cosine_similarity(target_embedding, emb.vector)
        similarities.append((emb.event, score))

    # Trier par similarité décroissante
    similarities.sort(key=lambda x: x[1], reverse=True)
    recommended_events = [evt for evt, _ in similarities[:top_k]]
    return recommended_events