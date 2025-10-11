from django.shortcuts import render

# ai_service/views.py
from django.shortcuts import render, get_object_or_404
from event_service.models import Event
from .recommender import get_recommendations_for_event
from .utils import update_event_embedding

def event_with_recommendations(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    
    # Met à jour l’embedding si absent (en dev seulement – en prod, faire via tâche)
    if not hasattr(event, 'embedding'):
        update_event_embedding(event)

    recommendations = get_recommendations_for_event(event, top_k=4)
    return render(request, 'event_with_reco.html', {
        'event': event,
        'recommendations': recommendations
    })