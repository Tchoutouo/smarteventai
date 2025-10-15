# ai_service/management/commands/send_recommendation_emails.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from user_service.models import UserProfile
from event_service.models import Reservation
from ai_service.recommender import get_recommendations_for_event
from ai_service.utils import update_event_embedding


class Command(BaseCommand):
    help = "Envoie des emails personnalisés HTML avec recommandations d'événements"

    def handle(self, *args, **options):
        # Cible : attendees avec consentement et au moins 1 réservation
        attendees = User.objects.filter(
            userprofile__role='attendee',
            userprofile__email_consent=True,
            reservation__isnull=False
        ).distinct()

        sent_count = 0
        base_url = f"http://{settings.IP_ADDRESS}:8000"

        for user in attendees:
            # Récupérer le dernier événement réservé
            last_reservation = Reservation.objects.filter(user=user).order_by('-created_at').first()
            if not last_reservation:
                continue

            event = last_reservation.event

            # Assure-toi que l’embedding existe
            if not hasattr(event, 'embedding'):
                update_event_embedding(event)

            recommendations = get_recommendations_for_event(event, top_k=3)
            if not recommendations:
                continue

            # === Générer le contenu HTML ===
            context = {
                'user': user,
                'last_event': event,
                'recommendations': recommendations,
                'base_url': base_url,
            }
            html_content = render_to_string('email/recommendation_email.html', context)

            # === Générer le contenu texte (sans erreur de f-string) ===
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

            try:
                msg = EmailMultiAlternatives(
                    subject="🎯 Découvrez des événements qui vous plairont !",
                    body=text_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[user.email]
                )
                msg.attach_alternative(html_content, "text/html")
                msg.send()
                sent_count += 1
                self.stdout.write(f"✅ Email envoyé à {user.email}")
            except Exception as e:
                self.stdout.write(f"❌ Erreur pour {user.email}: {e}")

        self.stdout.write(
            self.style.SUCCESS(f'✅ {sent_count} emails de recommandation envoyés.')
        )