# ai_service/email_utils.py
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from .recommender import get_recommendations_for_event
from .utils import update_event_embedding

def send_recommendation_email_to_user(user, event):
    """
    Envoie un email de recommandation personnalisé à un utilisateur après sa réservation.
    """
    if not hasattr(user, 'userprofile') or not user.userprofile.email_consent:
        return  # Ne pas envoyer si pas de consentement

    # Assure-toi que l’embedding existe
    if not hasattr(event, 'embedding'):
        update_event_embedding(event)

    recommendations = get_recommendations_for_event(event, top_k=3)
    if not recommendations:
        return

    base_url = f"http://{settings.IP_ADDRESS}:8000"
    context = {
        'user': user,
        'last_event': event,
        'recommendations': recommendations,
        'base_url': base_url,
    }

    # Contenu HTML
    html_content = render_to_string('email/recommendation_email.html', context)

    # Contenu texte (fallback)
    event_lines = []
    for e in recommendations:
        event_lines.append(f"• {e.title} ({e.date}) – {e.location}")
        event_lines.append(f"  {base_url}/event/{e.id}/")
    event_block = "\n".join(event_lines)

    text_content = f"""Bonjour {user.first_name or user.username},

Merci d’avoir participé à « {event.title} » !

Voici des événements similaires que vous pourriez aimer :

{event_block}

👉 Réservez vite : les places sont limitées !
{base_url}

À bientôt !
L’équipe SmartEventAI""".strip()

    # Envoi
    msg = EmailMultiAlternatives(
        subject="🎯 Découvrez des événements qui vous plairont !",
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email]
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send()