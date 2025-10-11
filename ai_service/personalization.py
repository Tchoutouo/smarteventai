# ai_service/personalization.py
from django.contrib.auth.models import User
from event_service.models import Reservation

def generate_personalized_message(user: User) -> str:
    name = user.first_name or user.username
    recent_reservations = Reservation.objects.filter(
        user=user
    ).select_related('event').order_by('-created_at')[:3]

    if not recent_reservations:
        return f"👋 Bonjour {name} ! Découvrez nos événements populaires."

    titles = ", ".join([r.event.title for r in recent_reservations])
    return f"✨ Salut {name} ! Tu as récemment réservé : {titles}. Voici des événements similaires !"