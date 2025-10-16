import io
import os
import qrcode, base64
from io import BytesIO
from django.template.loader import render_to_string
from django.core.mail import send_mail

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from datetime import datetime, timedelta, date
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.http import JsonResponse, HttpResponseForbidden, FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Sum, F, Count, ExpressionWrapper, DecimalField
from django.core.paginator import Paginator
from django.conf import settings
from decimal import Decimal
from django.urls import reverse
from user_service.models import UserProfile
from django.contrib.auth.models import User
from event_service.models import Event, Reservation
from ticket_service.models import Ticket
from payment_service.models import PaymentCard
from complaint_service.forms import ComplaintForm

from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, Spacer, Image, PageTemplate, Frame
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as canvas_module
from ai_service.recommender import get_recommendations_for_event
from ai_service.utils import update_event_embedding
from ai_service.email_utils import send_recommendation_email_to_user

import logging

logger = logging.getLogger("django")

def home_view(request):
    events = Event.objects.order_by('-created_at')
    return render(request, 'home.html', {'events': events})


# @login_required
def event_detail_view(request, event_id):
    print("event_detail_view")
    # if not hasattr(request.user, 'userprofile') or request.user.userprofile.role != 'attendee':
    #     return render(request, 'access_denied.html')
    event = get_object_or_404(Event, id=event_id)
    ref_id = request.GET.get('ref')
    return render(request, 'event_detail.html', {'event': event, "ref_ambassador": ref_id})


def login_view(request):
    return render(request, 'login.html')


def about_view(request):
    return render(request, 'about.html')



@login_required
def organizer_dashboard_view(request, secure_token):
    profile = get_object_or_404(UserProfile, secure_token=secure_token)


    if request.user != profile.user:
        return render(request, 'access_denied.html')

    events = Event.objects.filter(organizer=request.user, is_deleted=False).order_by('-date')

    ambassadors = UserProfile.objects.filter(role="ambassador")

    # print(ambassadors)

    total_events = events.count()
    total_tickets = 0
    active_tickets = 0
    sold_out_tickets = 0
    revenue = Decimal('0.00')

    for event in events:
        ticket_data = Reservation.objects.filter(event=event).aggregate(
            total_quantity=Sum('quantity'),
            total_price=Sum('total_price')
        )
        event.ticket_count = ticket_data['total_quantity'] or 0
        event.event_revenue = ticket_data['total_price'] or Decimal('0.00')
        total_tickets += event.ticket_count
        revenue += event.event_revenue

        if event.available_tickets > 0:
            active_tickets += 1
        else:
            sold_out_tickets += 1

    commission = revenue * Decimal('0.10')
    net_sales = revenue - commission
    today = date.today()
    max_date = today + timedelta(days=3 * 365)


    name = request.user.first_name or request.user.username
    current_hour = datetime.now().hour
    is_morning = current_hour < 12
    greeting_message = f"Good Morning, {name}!" if is_morning else f"Good Evening, {name}!"

    context = {
        'events': events,
        'secure_token': secure_token,
        'total_events': total_events,
        'total_tickets': total_tickets,
        'active_tickets': active_tickets,
        'sold_out_tickets': sold_out_tickets,
        'revenue': revenue,
        'commission': commission,
        'net_sales': net_sales,
        'today': today.isoformat(),
        'max_date': max_date.isoformat(),
       'greeting_message': greeting_message,
        'is_morning': is_morning,
        "eligible_ambassadors": ambassadors,
    }
    return render(request, 'organizer_dashboard.html', context)


@login_required
def ambassador_dashboard_view(request, secure_token):
    profile = get_object_or_404(UserProfile, secure_token=secure_token)

    if request.user != profile.user:
        return render(request, 'access_denied.html', status=403)

    # utiliser 'ambassadors' (nom du champ ManyToMany)
    events = Event.objects.filter(
        ambassadors=request.user,
        is_deleted=False
    ).order_by('-date')

    total_events = events.count()
    total_tickets = 0
    active_tickets = 0
    sold_out_tickets = 0
    revenue = Decimal('0.00')

    for event in events:
        ticket_data = Reservation.objects.filter(event=event).aggregate(
            total_quantity=Sum('quantity'),
            total_price=Sum('total_price')
        )
        event.ticket_count = ticket_data['total_quantity'] or 0
        event.event_revenue = ticket_data['total_price'] or Decimal('0.00')
        total_tickets += event.ticket_count
        revenue += event.event_revenue

        if event.available_tickets > 0:
            active_tickets += 1
        else:
            sold_out_tickets += 1

    # Récupère toutes les ventes attribuées à l'ambassadeur
    sales = Reservation.objects.filter(
        ambassador=request.user
    ).select_related('event')
    # Calcule le total gagné
    total_earned = Decimal('0.00')
    for sale in sales:
        print(sale, sale.event.commission_rate, sale.event.ticket_price)
        commission = sale.total_price * (sale.event.commission_rate / Decimal('100.00'))
        total_earned += commission

    # print("total_earned", total_earned)

    commission = revenue * Decimal('0.10')
    net_sales = revenue - commission
    today = date.today()
    max_date = today + timedelta(days=3 * 365)

    name = request.user.first_name or request.user.username
    current_hour = datetime.now().hour
    is_morning = current_hour < 12
    greeting_message = f"Bonjour, {name}!" if is_morning else f"Bonsoir, {name}!"

    context = {
        'events': events,
        'secure_token': secure_token,
        'total_events': total_events,
        'total_tickets': total_tickets,
        'active_tickets': active_tickets,
        'sold_out_tickets': sold_out_tickets,
        'revenue': revenue,
        'commission': commission,
        'net_sales': net_sales,
        'today': today.isoformat(),
        'max_date': max_date.isoformat(),
        'greeting_message': greeting_message,
        'is_morning': is_morning,
        "total_earned": total_earned
    }
    return render(request, 'ambassador_dashboard.html', context)


@login_required
def delete_event_view(request, secure_token, event_id):
    profile = get_object_or_404(UserProfile, secure_token=secure_token)
    if request.user != profile.user or profile.role != "organizer":
        return render(request, 'access_denied.html')

    event = get_object_or_404(Event, id=event_id, organizer=request.user)

    if request.method == "POST":
        event.delete()
        messages.success(request, "✅ Événement supprimé avec succès !", extra_tags="swal")
        return redirect('organizer-dashboard', secure_token=secure_token)

    return HttpResponseForbidden("Invalid request.")


@csrf_exempt
@login_required
def edit_event_view(request, secure_token, event_id):
    profile = get_object_or_404(UserProfile, secure_token=secure_token)
    if request.user != profile.user or profile.role != "organizer":
        return render(request, 'access_denied.html')

    event = get_object_or_404(Event, id=event_id, organizer=request.user)
    today = date.today()
    max_date = today + timedelta(days=3*365)

    if request.method == "POST":
        title = request.POST.get("title")
        description = request.POST.get("description")
        date_str = request.POST.get("date")
        location = request.POST.get("location")
        ticket_price = request.POST.get("ticket_price")
        available_tickets = request.POST.get("available_tickets")

        try:
            event_date = date.fromisoformat(date_str)
        except ValueError:
            messages.error(request, "Format de date invalide.")
            return redirect('organizer-dashboard', secure_token=secure_token)

        if not (today <= event_date <= max_date):
            messages.error(request, "La date doit être comprise entre aujourd'hui et 3 ans à partir de maintenant.")
            return redirect('organizer-dashboard', secure_token=secure_token)

        event.title = title
        event.description = description
        event.date = event_date
        event.location = location
        event.ticket_price = ticket_price
        event.available_tickets = available_tickets

        # Ajouter l'image de couverture si fournie
        if 'cover_image' in request.FILES:
            event.cover_image = request.FILES['cover_image']

        event.save()

        messages.success(request, "✅ Événement mis à jour avec succès !", extra_tags="swal")
        return redirect('organizer-dashboard', secure_token=secure_token)

    return HttpResponseForbidden("Méthode invalide.")


def event_public_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    print("event_public_detail")
    ref_id = request.GET.get('ref')
    # print(ref_id)

    # print(ref_id)
    return render(request, 'event_public.html',
                {'event': event, "ref_ambassador": ref_id}

                )

#def event_public_detail(request, event_id):
#    event = get_object_or_404(Event, id=event_id)
#    ref_id = request.GET.get('ref')
#
#    # Générer l’embedding si absent (en dev)
#    if not hasattr(event, 'embedding'):
#        update_event_embedding(event)
#
#    recommendations = get_recommendations_for_event(event, top_k=4)
#
#    return render(request, 'event_public.html', {
#        'event': event,
#        'ref_ambassador': ref_id,
#        'recommendations': recommendations
#    })

@login_required
def event_secure_detail(request, secure_token, event_id):
    profile = get_object_or_404(UserProfile, secure_token=secure_token)

    # 🔒 Vérification CRITIQUE : l'utilisateur connecté doit être le propriétaire du profil
    if request.user != profile.user:
        print("event_secure_detail")
        return render(request, 'access_denied.html', status=403)

    event = get_object_or_404(Event, id=event_id)
    user = request.user

    # Vérifier si l'utilisateur a accès
    is_organizer = profile.role == 'organizer'
    is_ambassador = profile.role == 'ambassador'

    if not (is_organizer or is_ambassador):
        return render(request, 'access_denied.html', status=403)

    # Réservations liées à cet utilisateur
    if is_organizer:
        reservations = event.reservation_set.all()
    elif is_ambassador:
        reservations = event.reservation_set.filter(ambassador=user)
    else:
        reservations = Reservation.objects.none()

    # Préparer les données selon le rôle

    total_tickets = reservations.aggregate(total=Sum('quantity'))['total'] or 0

    context = {
        'event': event,
        'is_organizer': is_organizer,
        'is_ambassador': is_ambassador,
        'reservations': reservations,
        "secure_token": secure_token,
        "total_tickets": total_tickets,

    }

    # Si organisateur : ajouter les données pour les modals
    if is_organizer:
        ambassadors = event.ambassadors.all()

        eligible_ambassadors = User.objects.filter(
            userprofile__role="ambassador"
        ).exclude(
            id__in=ambassadors.values_list('id', flat=True)
        )

        # 🔥 Calcul des statistiques par ambassadeur
        ambassador_stats = []
        for ambassador in ambassadors:
            ambassador_reservations = Reservation.objects.filter(
                event=event,
                ambassador=ambassador
            )
            count = ambassador_reservations.count()
            total_places = ambassador_reservations.aggregate(total=Sum('quantity'))['total'] or 0
            total_revenue = ambassador_reservations.aggregate(total=Sum('total_price'))['total'] or 0

            ambassador_stats.append({
                'user': ambassador,
                'reservations_count': count,
                'places': total_places,
                'revenue': total_revenue,
            })

        ambassador_stats.sort(key=lambda x: x['places'], reverse=True)
        # Calculs globaux
        total_reservations = Reservation.objects.filter(event=event).count()
        total_revenue = Reservation.objects.filter(event=event).aggregate(
            total=Sum('total_price')
        )['total'] or 0

        context.update({
            'ambassadors': ambassador_stats,  # ✅ maintenant avec stats
            'eligible_ambassadors': eligible_ambassadors,
            'today': date.today().isoformat(),
            'max_date': (date.today() + timedelta(days=3 * 365)).isoformat(),
            'total_reservations': total_reservations,
            'total_revenue': total_revenue,
        })

    if is_ambassador:
        # URL publique avec tracking
        local_ip = settings.IP_ADDRESS  # ← à remplacer par ton IP !
        public_url = f"http://{local_ip}:8000/event/{event.id}/?ref={user.id}"

        # public_url = request.build_absolute_uri(
        #     f"/event/{event.id}/?ref={user.id}"
        # )

        # Générer le QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(public_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        # Convertir en base64 pour l'embed dans le HTML
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_str = base64.b64encode(buffer.getvalue()).decode()

        context['qr_code_base64'] = img_str
        context['shareable_url'] = public_url


        ambassador_reservations = event.reservation_set.filter(ambassador=user)
        # print(ambassador_reservations)

        nb_reservations = ambassador_reservations.count()

        total_places = event.reservation_set.filter(ambassador=user).aggregate(
            total=Sum('quantity')
        )['total'] or 0

        ambassador_revenue = ambassador_reservations.aggregate(total=Sum('total_price'))['total'] or 0
        # print(ambassador_revenue)

        total_commission = Decimal('0.00')
        for reservation in ambassador_reservations:
            commission = reservation.total_price * (event.commission_rate / Decimal('100.00'))
            total_commission += commission


        context['ambassador_reservations'] = nb_reservations
        context['ambassador_revenue'] = ambassador_revenue
        context['total_places'] = total_places
        context['total_commission'] = total_commission

    return render(request, 'view_detail_event.html', context)


@login_required
def add_ambassador_to_event(request, secure_token, event_id, user_id):
    profile = get_object_or_404(UserProfile, secure_token=secure_token)
    if request.user != profile.user or profile.role != "organizer":
        return render(request, 'access_denied.html', status=403)

    event = get_object_or_404(Event, id=event_id, organizer=request.user)
    ambassador_profile = get_object_or_404(UserProfile, id=user_id)
    ambassador_user = get_object_or_404(User, id=ambassador_profile.user.id)

    # Vérifie que cet utilisateur est bien un ambassador (optionnel mais recommandé)
    ambassador_profile = get_object_or_404(UserProfile, user=ambassador_user)
    if ambassador_profile.role != "ambassador":
        messages.error(request, "Cet utilisateur n'est pas un ambassadeur.")
        return redirect('organizer-dashboard', secure_token=secure_token)

    # Ajoute (ManyToMany ignore les doublons)
    event.ambassadors.add(ambassador_user)
    messages.success(request, f"{ambassador_user.get_full_name() or ambassador_user.username} ajouté en tant qu'ambassadeur !")
    return redirect('organizer-dashboard', secure_token=secure_token)



@login_required
def event_create_view(request, secure_token):
    profile = get_object_or_404(UserProfile, secure_token=secure_token)
    if request.user != profile.user or profile.role != 'organizer':
        return render(request, 'access_denied.html')

    if request.method == "POST":
        title = request.POST.get("title")
        description = request.POST.get("description")
        location = request.POST.get("location")
        date_str = request.POST.get("date")
        ticket_price = request.POST.get("ticket_price")
        commission = request.POST.get("commission")
        available_tickets = request.POST.get("available_tickets")

        try:
            event_date = date.fromisoformat(date_str)
            today = date.today()
            max_date = today + timedelta(days=3*365)
            if not (today <= event_date <= max_date):
                messages.error(request, "Date d'événement non valide.")
                return redirect('organizer-dashboard', secure_token=secure_token)
        except ValueError:
            messages.error(request, "Format de date invalide.")
            return redirect('organizer-dashboard', secure_token=secure_token)

        event = Event.objects.create(
            title=title,
            description=description,
            location=location,
            date=event_date,
            ticket_price=ticket_price,
            available_tickets=available_tickets,
            organizer=request.user,
            commission_rate=commission,
        )

        # Ajouter l'image de couverture si fournie
        if 'cover_image' in request.FILES:
            event.cover_image = request.FILES['cover_image']

        event.save()
        messages.success(request, "✅ Événement ajouté avec succès !", extra_tags="swal")

    return redirect('organizer-dashboard', secure_token=secure_token)



@login_required
def supervisor_panel_view(request):
    if not request.user.is_superuser:
        return redirect('home')
    return render(request, 'supervisor_panel.html')





def complaint_form_view(request):
    if request.method == 'POST':
        form = ComplaintForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "✅ Réclamation soumise avec succès.")
            return redirect('complaint-form')
        else:
            messages.error(request, "⚠️ Veuillez corriger les erreurs ci-dessous.")
    else:
        form = ComplaintForm(user=request.user)

    return render(request, 'complaint_form.html', {
        'form': form
    })


def search_view(request):
    query = request.GET.get('q', '')
    events = []
    if query:
        events = Event.objects.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        ).order_by('-created_at')
    return render(request, 'home.html', {
        'events': events,
        'search_query': query
    })


# views.py
@login_required
def complete_pending_reservation(request):
    print("complete_pending_reservation")
    if 'pending_reservation' not in request.session:
        messages.error(request, "Aucune réservation en attente trouvée.")
        return redirect('organizer-dashboard')  # ou autre page

    data = request.session['pending_reservation']
    # print(data)
    event = get_object_or_404(Event, id=data['event_id'])

    # Vérifier que la carte existe maintenant
    if not PaymentCard.objects.filter(user=request.user).exists():
        messages.error(request, "Vous devez d'abord ajouter une carte de paiement.")
        return redirect('add-payment-card', secure_token=request.user.userprofile.secure_token)

    # === Reprendre la réservation ===
    qty = data['quantity']
    if qty > event.available_tickets:
        del request.session['pending_reservation']
        messages.error(request, f"Il ne reste que {event.available_tickets} billets.")
        return redirect('event-public-detail', event_id=event.id)

    # Ambassador
    ambassador = None
    ref_id = data.get('ref_id')
    if ref_id and ref_id.isdigit():
        if event.ambassadors.filter(id=ref_id).exists():
            ambassador = get_object_or_404(User, id=ref_id)

    # Créer la réservation
    total = qty * event.ticket_price
    reservation = Reservation.objects.create(
        user=request.user,
        event=event,
        quantity=qty,
        total_price=total,
        ambassador=ambassador,
        signature=f"{request.user.id}-{timezone.now().timestamp()}"
    )

    # Mettre à jour
    event.available_tickets -= qty
    event.save()

    profile = request.user.userprofile
    profile.total_tickets_reserved += qty
    profile.save()

    # Nettoyer la session
    del request.session['pending_reservation']

    request.session['reservation_id'] = reservation.id

    request.session['booking_message'] = f"🎉 Réservation terminée ! {qty} billet(s) pour \"{event.title}\"."
    return redirect('booking-success')


# @login_required

# def book_ticket_view(request, event_id):
#
#     # try:
#     #     profile = UserProfile.objects.get(secure_token=secure_token)
#     # except UserProfile.DoesNotExist:
#     #     return HttpResponseForbidden("Access denied")
#
#     # if request.user != profile.user or profile.role != "attendee":
#     #     return HttpResponseForbidden("Access denied")
#
#     event = get_object_or_404(Event, id=event_id)
#
#     if request.user and not PaymentCard.objects.filter(user=request.user).exists():
#         profile = UserProfile.objects.get(user=request.user)
#
#         messages.warning(request, "⚠️ No payment card on file. Redirecting...")
#         return render(request, 'redirect_to_payment.html', {
#             'secure_token': profile.secure_token,
#         })
#
#     if request.method == 'POST':
#         # === 🔑 Récupérer et valider l'ambassador via ?ref=... ===
#         ambassador = None
#         ref_id = request.POST.get('ref')  # ou request.POST.get si tu passes en POST
#         print(ref_id)
#
#         if ref_id and ref_id.isdigit():
#             ref_id = int(ref_id)
#             # Vérifie que cet utilisateur est bien un ambassador de cet événement
#             if event.ambassadors.filter(id=ref_id).exists():
#                 ambassador = get_object_or_404(User, id=ref_id)
#
#         qty = int(request.POST.get('quantity', 0))
#         if qty <= 0:
#             messages.error(request, "❌ Enter valid ticket quantity")
#             return redirect('event-detail', event_id=event_id)
#         if qty > event.available_tickets:
#             messages.error(request, f"❌ Only {event.available_tickets} left")
#             return redirect('event-detail', event_id=event_id)
#
#         total = qty * event.ticket_price
#
#         reservation = Reservation.objects.create(
#             user=request.user,
#             event=event,
#             quantity=qty,
#             total_price=total,
#             ambassador=ambassador,
#             signature=f"{request.user.id}-{timezone.now().timestamp()}"
#         )
#         request.session['reservation_id'] = reservation.id
#
#         event.available_tickets -= qty
#         event.save()
#         profile.total_tickets_reserved += reservation.quantity
#         profile.save()
#
#         request.session['reservation_id'] = reservation.id
#         request.session['booking_message'] = f"🎉 You booked {reservation.quantity} for \"{event.title}\"!"
#         return redirect('booking-success')
#
#     return redirect('event-detail', event_id=event_id)
#

def book_ticket_view(request, event_id):
    print("book_ticket_view")
    event = get_object_or_404(Event, id=event_id, is_deleted=False)

    if event.available_tickets <= 0:
        messages.error(request, "❌ Cet événement est complet.")
        return redirect('event-public-detail', event_id=event.id)

    if request.method == 'POST':
        # Récupérer les données du formulaire
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        qty = request.POST.get('quantity', '0')
        ref_id = request.POST.get('ref', '').strip()

        # Validation basique
        if not (first_name and last_name and email):
            messages.error(request, "❌ Le prénom, le nom et l'email sont requis.")
            return redirect('event-public-detail', event_id=event.id)

        if not qty.isdigit() or int(qty) <= 0:
            messages.error(request, "❌ Veuillez entrer une quantité de billets valide.")
            return redirect('event-public-detail', event_id=event.id)

        qty = int(qty)
        if qty > event.available_tickets:
            messages.error(request, f"❌ Il ne reste que {event.available_tickets} billets.")
            return redirect('event-public-detail', event_id=event.id)

        # === 1. Gérer l'utilisateur (existant ou nouveau) ===
        user = None
        password = None
        if request.user.is_authenticated:
            # Cas : utilisateur déjà connecté
            user = request.user
        else:
            # Cas : utilisateur non connecté → chercher ou créer
            try:
                # Chercher un utilisateur avec cet email
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                try:
                    user = User.objects.get(username=email)
                except User.DoesNotExist:
                    user = None
                    # Créer un nouveau compte
                    password = User.objects.make_random_password()
                    user = User.objects.create_user(
                        username=email,
                        email=email,
                        password=password,
                        first_name=first_name,
                        last_name=last_name
                    )
                    # Créer le profil
                    UserProfile.objects.create(user=user, role='attendee')

                    try:
                        """Send verification mail"""
                        from_email = settings.DEFAULT_FROM_EMAIL
                        mail_subject = "Account Registration Confirmation"
                        to_email = user.email

                        server_ip = settings.IP_ADDRESS
                        port = "8000"
                        login_url = f"http://{server_ip}:{port}/login/"

                        msge = render_to_string(
                            "email/confirm_mail_attendee.txt",
                            {
                                "username": user.email,
                                "login_url": login_url,
                                "password": password,
                                "first_name": first_name,
                                "last_name": last_name
                            },
                        )

                        msge_html = render_to_string(
                            "email/confirm_mail_attendee.html",
                            {
                                "username": user.email,
                                "login_url": login_url,
                                "password": password,
                                "first_name": first_name,
                                "last_name": last_name
                            },
                        )
                        send_mail(
                            mail_subject,
                            msge,
                            from_email,
                            [to_email, ],
                            fail_silently=False,
                            html_message=msge_html,
                        )
                        logger.info(f"Send verification email for {user.email}")
                        logger.info(f"Send New User {user.email} notification to Project...")

                        messages.success(request, 'Your account has been  registered successfully!')

                    except Exception as e:
                        print(e)
                        msg = "Error sending the verification message"
                        messages.error(request, msg)
                        logger.error(f"Error sending the verification message: {e}")

            # Mettre à jour le prénom/nom si différent (au cas où)
            if user.first_name != first_name or user.last_name != last_name:
                user.first_name = first_name
                user.last_name = last_name
                user.save()

        # if user:
            login(request, user)

        # === 3. Récupérer ou créer le profil ===
        profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={'role': 'attendee'}
        )
        if created:
            profile.role = 'attendee'
            profile.save()

        # === 4. Vérifier la carte de paiement (optionnel) ===
        if not PaymentCard.objects.filter(user=user).exists():
            messages.warning(request, "⚠️ Aucune carte de paiement enregistrée. Paiement simulé pour la démo.")
            # Sauvegarder les données de réservation dans la session
            request.session['pending_reservation'] = {
                'event_id': event.id,
                'quantity': qty,
                'ref_id': ref_id,
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
            }
            return render(request, 'redirect_to_payment.html', {
                'secure_token': profile.secure_token,
            })

        # === 5. Gérer l'ambassador ===
        ambassador = None
        if ref_id and ref_id.isdigit():
            ref_id = int(ref_id)
            if event.ambassadors.filter(id=ref_id).exists():
                ambassador = get_object_or_404(User, id=ref_id)

        # === 6. Créer la réservation ===
        total = qty * event.ticket_price
        reservation = Reservation.objects.create(
            user=user,
            event=event,
            quantity=qty,
            total_price=total,
            ambassador=ambassador,
            signature=f"{user.id}-{timezone.now().timestamp()}"
        )

        # === 7. Mettre à jour les stocks et stats ===
        event.available_tickets -= qty
        event.save()

        profile.total_tickets_reserved += qty
        profile.save()

        # print(event)

        request.session['reservation_id'] = reservation.id

        # Send verification mail. Handle any exception that could occur.
        try:
            """Send reservation confirmation mail"""
            from_email = settings.DEFAULT_FROM_EMAIL
            mail_subject = "Reservation Confirmation"
            to_email = user.email

            msge = render_to_string(
                "email/confirm_book_email.txt",
                {
                    "user": user.email,
                    "event": event,
                    "quantity": qty,
                    "total_price": total,
                    "title": event.title,
                    "location": event.location,
                    "date": event.date,
                    "price": event.ticket_price,
                },
            )

            msge_html = render_to_string(
                "email/confirm_book_email.html",
                {
                    "user": user.email,
                    "event": event,
                    "quantity": qty,
                    "total_price": total,
                    "title": event.title,
                    "location": event.location,
                    "date": event.date,
                    "price": event.ticket_price,
                },
            )
            send_mail(
                mail_subject,
                msge,
                from_email,
                [to_email, ],
                fail_silently=False,
                html_message=msge_html,
            )
            logger.info(f"Reservation Confirmation for {to_email}")

        except Exception as e:
            print(e)
            msg = "Error sending the confirmation message"
            messages.error(request, msg)
            logger.error(f"Error sending the confirmation message: {e}")

        try:
            send_recommendation_email_to_user(request.user, event)
        except Exception as e:
            # Ne pas bloquer la réservation si l’email échoue
            print(f"Erreur envoi email recommandation : {e}")
        # === 8. Rediriger vers succès ===

        title = event.title

        request.session['booking_message'] = f"🎉 Vous avez réservé {qty} billet(s) pour {title} !"
        return redirect('booking-success')

    # Si ce n'est pas POST, rediriger vers la page publique
    return redirect('event_public_detail', event_id=event_id)


@login_required
def booking_success_view(request):
    reservation_id = request.session.pop('reservation_id', None)
    if not reservation_id:
        return redirect('home')
    reservation = get_object_or_404(Reservation, id=reservation_id, user=request.user)
    event = reservation.event
    #event_id = event.id
    ref_id = request.GET.get('ref')
        # Générer l’embedding si absent (en dev)
    if not hasattr(event, 'embedding'):
        update_event_embedding(event)

    recommendations = get_recommendations_for_event(event, top_k=4)

    # print(event)
    return render(request, 'booking_success.html', {
        'reservation': reservation,
        'event': event,
        'ref_ambassador': ref_id,
        'recommendations': recommendations
    })



@login_required
def redirect_to_payment_view(request, secure_token):
    return render(request, 'redirect_to_payment.html', {'secure_token': secure_token})





@login_required
def my_tickets_attendee(request, secure_token):
    try:
        profile = UserProfile.objects.get(secure_token=secure_token)
    except UserProfile.DoesNotExist:
        return render(request, 'access_denied.html')

    if request.user != profile.user or profile.role != "attendee":
        return render(request, 'access_denied.html')

    reservations = Reservation.objects.filter(user=request.user).select_related('event').order_by('-created_at')
    active_reservations = [r for r in reservations if not r.event.is_deleted]

    total_booked_events = len(active_reservations)
    total_deleted_events = len([r for r in reservations if r.event.is_deleted])
    today = timezone.now().date()
    total_active_events = len([r for r in active_reservations if r.event.date >= today])
    total_expired_events = len([r for r in active_reservations if r.event.date < today])
    total_payment = sum(r.total_price for r in active_reservations)

    context = {
        'reservations': reservations,
        'total_booked': total_booked_events,
        'total_deleted': total_deleted_events,
        'total_active': total_active_events,
        'total_expired': total_expired_events,
        'total_paid': total_payment,
        'total_tickets_reserved': profile.total_tickets_reserved,
        'deleted_events_count': profile.deleted_events_count,
    }
    return render(request, 'my_tickets.html', context)




@login_required
def delete_reservation(request, reservation_id):
    if request.method == 'POST':
        reservation = get_object_or_404(Reservation, id=reservation_id, user=request.user)
        time_difference = timezone.now() - reservation.created_at

        if time_difference.total_seconds() > 10800:
            return JsonResponse({'status': 'error', 'message': 'Vous ne pouvez pas annuler cette réservation après 3 heures.'})

        event = reservation.event
        event.available_tickets += reservation.quantity
        event.save()

        try:
            profile = UserProfile.objects.get(user=request.user)


            profile.total_tickets_reserved -= reservation.quantity
            if profile.total_tickets_reserved < 0:
                profile.total_tickets_reserved = 0


            profile.deleted_events_count += 1

            profile.save()

        except UserProfile.DoesNotExist:
            pass

        reservation.delete()
        return JsonResponse({'status': 'success'})


    return render(request, '404.html', status=404)


@login_required
def download_ticket_pdf(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id, user=request.user)
    buffer = io.BytesIO()

    # === Police ===
    font_name = "Helvetica"
    try:
        font_path = os.path.join(settings.BASE_DIR, 'static/fonts/DejaVuSans.ttf')
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont("DejaVu", font_path))
            font_name = "DejaVu"
    except:
        pass

    doc = SimpleDocTemplate(
        buffer, pagesize=A5,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm
    )

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, showBoundary=0)

    def draw_background_and_footer(canvas, doc):
        width, height = A5
        canvas.setFillColorRGB(0.98, 0.98, 0.98)
        canvas.rect(0, 0, width, height, stroke=0, fill=1)
        canvas.setFillColorRGB(0.95, 0.95, 1)
        canvas.roundRect(1 * cm, 1 * cm, width - 2 * cm, height - 2 * cm, 10, stroke=0, fill=1)
        canvas.saveState()
        canvas.setFont("Helvetica", 36)
        canvas.setFillColorRGB(0.85, 0.85, 0.95)
        canvas.translate(width / 2, height / 2)
        canvas.rotate(45)
        canvas.drawCentredString(0, 0, "TICKET")
        canvas.restoreState()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        canvas.setFont(font_name, 8)
        canvas.setFillColor(colors.HexColor("#666"))
        canvas.drawRightString(width - doc.rightMargin, 0.7 * cm, f"Printed: {timestamp}")

    template = PageTemplate(id='TicketTemplate', frames=[frame], onPage=draw_background_and_footer)
    doc.addPageTemplates([template])

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'Title', parent=styles['Heading1'],
        fontName=font_name, fontSize=20,
        textColor=colors.HexColor('#1a237e'),
        alignment=1, spaceAfter=0.3 * cm
    )
    user_style = ParagraphStyle(
        'User', parent=styles['Normal'],
        fontName=font_name, fontSize=12,
        textColor=colors.HexColor('#222'),
        alignment=1, spaceAfter=0.4 * cm
    )
    note_style = ParagraphStyle(
        'Note', parent=styles['Normal'],
        fontName=font_name, fontSize=9,
        textColor=colors.HexColor('#555'),
        alignment=1, spaceBefore=0.5 * cm
    )
    secret_style = ParagraphStyle(
        'Secret', parent=styles['Normal'],
        fontName=font_name, fontSize=8,
        textColor=colors.HexColor('#888'),
        alignment=1, spaceBefore=0.2 * cm
    )

    elements = []

    # === 1. Titre "SmartEventAI" au lieu du logo ===
    smart_title = ParagraphStyle(
        'SmartTitle', parent=styles['Heading2'],
        fontName=font_name, fontSize=16,
        textColor=colors.HexColor('#1a237e'),
        alignment=1, spaceAfter=0.3 * cm
    )
    elements.append(Paragraph("SmartEventAI", smart_title))
    elements.append(Spacer(1, 0.2 * cm))

    # === 2. Image de couverture (réduite) ===
    if reservation.event.cover_image:
        cover_path = reservation.event.cover_image.path
        if os.path.exists(cover_path):
            try:
                # Hauteur réduite à 3 cm pour tenir sur une page
                cover_img = Image(cover_path, width=doc.width, height=3 * cm)
                cover_img.hAlign = 'CENTER'
                elements.append(cover_img)
                elements.append(Spacer(1, 0.3 * cm))
            except:
                pass

    # === 3. Titre de l'événement ===
    elements.append(Paragraph(reservation.event.title, title_style))

    # === 4. Infos utilisateur ===
    user = request.user
    full_name = f"{user.first_name} {user.last_name}".strip()
    display_name = full_name if full_name != "" else user.username
    elements.append(Paragraph(f"Participant: {display_name}", user_style))
    if user.email:
        elements.append(Paragraph(f"Email: {user.email}", user_style))

    elements.append(Spacer(1, 0.3 * cm))

    # === 5. Tableau ===
    data = [
        ['Lieu', str(reservation.event.location)],
        ['Date', reservation.event.date.strftime('%A, %B %d, %Y')],
        ['Billets', str(reservation.quantity)],
        ['Total', f"${reservation.total_price:.2f}"]
    ]

    if reservation.ambassador:
        data.append(['Ambassadeur', reservation.ambassador.get_full_name() or reservation.ambassador.username])

    table = Table(data, colWidths=[4 * cm, doc.width - 4 * cm])
    table.setStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.white),
        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#4a5568')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2d3748')),
    ])
    elements.append(table)

    elements.append(Spacer(1, 0.5 * cm))

    # === 6. QR Code avec URL locale ===
    server_ip = settings.IP_ADDRESS
    port = "8000"
    verify_url = f"http://{server_ip}:{port}{reverse('verify-ticket', kwargs={'secret_key': reservation.secret_key})}"

    qr = qrcode.make(verify_url)
    qr_buf = io.BytesIO()
    qr.save(qr_buf, format='PNG')
    qr_buf.seek(0)
    qr_img = Image(qr_buf, width=4 * cm, height=4 * cm)  # un peu plus petit
    qr_img.hAlign = 'CENTER'
    elements.append(qr_img)

    elements.append(Paragraph(f"Clé : {reservation.secret_key}", secret_style))

    # === Générer ===
    doc.build(elements)
    buffer.seek(0)

    event_title = "".join(c for c in reservation.event.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
    fname = f"ticket_{event_title}_{user.username}.pdf".replace(' ', '_')
    return FileResponse(buffer, as_attachment=True, filename=fname)


# @login_required
# def download_ticket_pdf(request, reservation_id):
#     reservation = get_object_or_404(Reservation, id=reservation_id, user=request.user)
#     buffer = io.BytesIO()
#
#     try:
#         font_path = os.path.join(settings.BASE_DIR, 'static/fonts/DejaVuSans.ttf')
#         pdfmetrics.registerFont(TTFont("DejaVu", font_path))
#         font_name = "DejaVu"
#     except:
#         font_name = "Helvetica"
#
#     doc = SimpleDocTemplate(
#         buffer, pagesize=A5,
#         leftMargin=1.5 * cm, rightMargin=1.5 * cm,
#         topMargin=2 * cm, bottomMargin=2 * cm
#     )
#
#     frame = Frame(
#         doc.leftMargin, doc.bottomMargin,
#         doc.width, doc.height,
#         showBoundary=0
#     )
#
#     def draw_background_and_footer(canvas, doc):
#         width, height = A5
#         canvas.setFillColorRGB(0.9, 0.9, 1)
#         canvas.rect(0, 0, width, height, stroke=0, fill=1)
#         canvas.setFillColorRGB(0.8, 0.8, 1)
#         canvas.roundRect(1 * cm, 1 * cm, width - 2 * cm, height - 2 * cm, 10, stroke=0, fill=1)
#         canvas.saveState()
#         canvas.setFont("Helvetica", 40)
#         canvas.setFillColorRGB(0.7, 0.7, 0.7, alpha=0.2)
#         canvas.translate(width / 2, height / 2)
#         canvas.rotate(45)
#         canvas.drawCentredString(0, 0, "EVENT TICKET")
#         canvas.restoreState()
#         timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         canvas.saveState()
#         canvas.setFont(font_name, 8)
#         canvas.setFillColor(colors.HexColor("#333"))
#         canvas.drawRightString(width - doc.rightMargin, 0.7 * cm, f"Printed: {timestamp}")
#         canvas.restoreState()
#
#     template = PageTemplate(id='TicketTemplate', frames=[frame], onPage=draw_background_and_footer)
#     doc.addPageTemplates([template])
#
#     styles = getSampleStyleSheet()
#
#     title_style = ParagraphStyle(
#         'Title', parent=styles['Heading1'],
#         fontName=font_name, fontSize=20,
#         textColor=colors.HexColor('#1a237e'),
#         alignment=1, spaceAfter=0.3 * cm
#     )
#
#     user_style = ParagraphStyle(
#         'User', parent=styles['Normal'],
#         fontName=font_name, fontSize=12,
#         textColor=colors.HexColor('#333'),
#         alignment=1, spaceAfter=0.5 * cm
#     )
#
#     note_style = ParagraphStyle(
#         'Note', parent=styles['Normal'],
#         fontName=font_name, fontSize=9,
#         textColor=colors.HexColor('#555'),
#         alignment=1, spaceBefore=0.5 * cm
#     )
#
#     secret_style = ParagraphStyle(
#         'Secret', parent=styles['Normal'],
#         fontName=font_name, fontSize=8,
#         textColor=colors.HexColor('#B0B0B0'),
#         alignment=1, spaceBefore=0.2 * cm
#     )
#
#     elements = []
#
#     logo_path = os.path.join(settings.BASE_DIR, 'static/images/logo.png')
#     if os.path.exists(logo_path):
#         logo = Image(logo_path, width=3 * cm, height=3 * cm)
#         logo.hAlign = 'CENTER'
#         elements.append(logo)
#
#     elements.append(Spacer(1, 0.5 * cm))
#
#     elements.append(Paragraph(reservation.event.title, title_style))
#
#
#     elements.append(Paragraph(f"User: {request.user.username}", user_style))
#
#     elements.append(Spacer(1, 0.5 * cm))
#
#     data = [
#         ['Lieu', reservation.event.location],
#         ['Date', reservation.event.date.strftime('%B %d, %Y')],
#         ['Billets', str(reservation.quantity)],
#         ['Payé', f"${reservation.total_price:.2f}"]
#     ]
#
#     if reservation.signature:
#         data.append(['Code', reservation.signature])
#
#     table = Table(data, colWidths=[4 * cm, doc.width - 4 * cm])
#     table.setStyle([
#         ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ffffff')),
#         ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#555')),
#         ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#aaa')),
#         ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
#         ('FONT', (0, 0), (-1, -1), font_name),
#         ('FONTSIZE', (0, 0), (-1, -1), 11),
#         ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333')),
#     ])
#     elements.append(table)
#
#     elements.append(Spacer(1, 0.7 * cm))
#
#     qr = qrcode.make(f"ID:{reservation.id}|KEY:{reservation.secret_key}|USER:{request.user.username}")
#
#     qr_buf = io.BytesIO()
#     qr.save(qr_buf, format='PNG')
#     qr_buf.seek(0)
#     qr_img = Image(qr_buf, width=5 * cm, height=5 * cm)
#     qr_img.hAlign = 'CENTER'
#     elements.append(qr_img)
#
#     elements.append(Paragraph(reservation.secret_key, secret_style))
#
#     note = "Ce billet ne donne droit qu'à une seule entrée. Présentez-le à l'entrée."
#     elements.append(Paragraph(note, note_style))
#
#     doc.build(elements)
#     buffer.seek(0)
#
#     fname = f"{reservation.event.title}_{request.user.username}_ticket.pdf".replace(' ', '_')
#     return FileResponse(buffer, as_attachment=True, filename=fname)
#

import csv
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required

@login_required
def export_reservations_csv(request, secure_token, event_id):
    # Vérifier les droits (même logique que event_secure_detail)
    profile = get_object_or_404(UserProfile, secure_token=secure_token)
    if request.user != profile.user or profile.role != 'organizer':
        return render(request, 'access_denied.html', status=403)

    event = get_object_or_404(Event, id=event_id, organizer=request.user)

    # Récupérer toutes les réservations
    reservations = event.reservation_set.select_related('user', 'ambassador').all()

    # Créer la réponse CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="reservations_{event.title.replace(" ", "_")}_{event.id}.csv"'

    writer = csv.writer(response)
    # En-têtes
    writer.writerow([
        'Nom complet',
        'Email',
        'Username',
        'Nombre de billets',
        'Total payé ($)',
        'Date de réservation',
        'Ambassador',
        'ID réservation',
        'Clé secrète'
    ])

    # Données
    for r in reservations:
        ambassador = r.ambassador.get_full_name() if r.ambassador else '—'
        writer.writerow([
            r.user.get_full_name() or f"{r.user.first_name} {r.user.last_name}".strip() or r.user.username,
            r.user.email,
            r.user.username,
            r.quantity,
            f"{r.total_price:.2f}",
            r.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            ambassador,
            r.id,
            r.secret_key
        ])

    return response


def verify_ticket_view(request, secret_key):
    reservation = get_object_or_404(Reservation, secret_key=secret_key)

    context = {
        'reservation': reservation,
        'event': reservation.event,
        'user': reservation.user,
    }
    return render(request, 'verify_ticket.html', context)




def not_found_view(request, exception=None):
    return render(request, '404.html', status=404)
