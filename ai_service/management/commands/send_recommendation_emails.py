# ai_service/management/commands/send_recommendation_emails.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
from user_service.models import UserProfile
from event_service.models import Reservation
from ai_service.recommender import get_recommendations_for_event
from ai_service.utils import update_event_embedding

class Command(BaseCommand):
    help = "Envoie des emails personnalisés avec recommandations d'événements"

    def handle(self, *args, **options):
        # Cible : attendees avec consentement et au moins 1 réservation
        attendees = User.objects.filter(
            userprofile__role='attendee',
            userprofile__email_consent=True,
            reservation__isnull=False
        ).distinct()

        sent_count = 0
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

            # Générer le message
            name = user.first_name or user.username
            event_list = "\n".join([f"• {e.title} ({e.date}) – {e.location}" for e in recommendations])
            subject = "🎯 Découvrez des événements qui vous plairont !"
            message = f"""
Bonjour {name},

Merci d’avoir participé à « {event.title} » !

Voici des événements similaires que vous pourriez aimer :

{event_list}

👉 Réservez vite : les places sont limitées !
{settings.IP_ADDRESS}:8000

À bientôt !
L’équipe EventTicket
            """.strip()

            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                sent_count += 1
                self.stdout.write(f"✅ Email envoyé à {user.email}")
            except Exception as e:
                self.stdout.write(f"❌ Erreur pour {user.email}: {e}")

        self.stdout.write(
            self.style.SUCCESS(f'✅ {sent_count} emails de recommandation envoyés.')
        )