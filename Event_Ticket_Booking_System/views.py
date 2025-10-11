import io
import os
import qrcode, base64
from io import BytesIO

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
        messages.success(request, "✅ Event deleted successfully!", extra_tags="swal")
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
            messages.error(request, "Invalid date format.")
            return redirect('organizer-dashboard', secure_token=secure_token)

        if not (today <= event_date <= max_date):
            messages.error(request, "Date must be between today and 3 years from now.")
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

        messages.success(request, "✅ Event updated successfully!", extra_tags="swal")
        return redirect('organizer-dashboard', secure_token=secure_token)

    return HttpResponseForbidden("Invalid method.")


def event_public_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    print("event_public_detail")
    ref_id = request.GET.get('ref')
    print(ref_id)

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
    context = {
        'event': event,
        'is_organizer': is_organizer,
        'is_ambassador': is_ambassador,
        'reservations': reservations,
        "secure_token": secure_token
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

        context['ambassador_reservations'] = nb_reservations
        context['ambassador_revenue'] = ambassador_revenue
        context['total_places'] = total_places

    return render(request, 'view_detail_event.html', context)


@login_required
# views.py
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
        messages.error(request, "This user is not an ambassador.")
        return redirect('organizer-dashboard', secure_token=secure_token)

    # Ajoute (ManyToMany ignore les doublons)
    event.ambassadors.add(ambassador_user)
    messages.success(request, f"{ambassador_user.get_full_name() or ambassador_user.username} added as ambassador!")
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
        available_tickets = request.POST.get("available_tickets")

        try:
            event_date = date.fromisoformat(date_str)
            today = date.today()
            max_date = today + timedelta(days=3*365)
            if not (today <= event_date <= max_date):
                messages.error(request, "Invalid event date.")
                return redirect('organizer-dashboard', secure_token=secure_token)
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect('organizer-dashboard', secure_token=secure_token)

        event = Event.objects.create(
            title=title,
            description=description,
            location=location,
            date=event_date,
            ticket_price=ticket_price,
            available_tickets=available_tickets,
            organizer=request.user
        )

        # Ajouter l'image de couverture si fournie
        if 'cover_image' in request.FILES:
            event.cover_image = request.FILES['cover_image']

        event.save()
        messages.success(request, "✅ Event added successfully!", extra_tags="swal")

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
            messages.success(request, "✅ Complaint submitted successfully.")
            return redirect('complaint-form')
        else:
            messages.error(request, "⚠️ Please correct the errors below.")
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
        messages.error(request, "No pending reservation found.")
        return redirect('organizer-dashboard')  # ou autre page

    data = request.session['pending_reservation']
    # print(data)
    event = get_object_or_404(Event, id=data['event_id'])

    # Vérifier que la carte existe maintenant
    if not PaymentCard.objects.filter(user=request.user).exists():
        messages.error(request, "You must add a payment card first.")
        return redirect('add-payment-card', secure_token=request.user.userprofile.secure_token)

    # === Reprendre la réservation ===
    qty = data['quantity']
    if qty > event.available_tickets:
        del request.session['pending_reservation']
        messages.error(request, f"Only {event.available_tickets} tickets left.")
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

    request.session['booking_message'] = f"🎉 Reservation completed! {qty} ticket(s) for \"{event.title}\"."
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
        messages.error(request, "❌ This event is sold out.")
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
            messages.error(request, "❌ First name, last name, and email are required.")
            return redirect('event-public-detail', event_id=event.id)

        if not qty.isdigit() or int(qty) <= 0:
            messages.error(request, "❌ Please enter a valid ticket quantity.")
            return redirect('event-public-detail', event_id=event.id)

        qty = int(qty)
        if qty > event.available_tickets:
            messages.error(request, f"❌ Only {event.available_tickets} tickets available.")
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

            # Mettre à jour le prénom/nom si différent (au cas où)
            if user.first_name != first_name or user.last_name != last_name:
                user.first_name = first_name
                user.last_name = last_name
                user.save()

            # user = authenticate(request, username=email, password=password)
            print(user)

        # if user:
            login(request, user)
        # === 2. Connecter l'utilisateur s'il ne l'est pas déjà ===
        # if not request.user.is_authenticated:
        #     print(user)
        #     print(request)
        #     login(request, user)
        #     request.session.set_expiry(3600)


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
            messages.warning(request, "⚠️ No payment card on file. Payment simulated for demo.")
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

        request.session['reservation_id'] = reservation.id

        # === 8. Rediriger vers succès ===
        request.session['booking_message'] = f"🎉 You booked {qty} ticket(s) for \"{event.title}\"!"
        return redirect('booking-success')

    # Si ce n'est pas POST, rediriger vers la page publique
    return redirect('event-public-detail', event_id=event_id)


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

    print(event)
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
            return JsonResponse({'status': 'error', 'message': 'You cannot delete this reservation after 3 hours.'})

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

    try:
        font_path = os.path.join(settings.BASE_DIR, 'static/fonts/DejaVuSans.ttf')
        pdfmetrics.registerFont(TTFont("DejaVu", font_path))
        font_name = "DejaVu"
    except:
        font_name = "Helvetica"

    doc = SimpleDocTemplate(
        buffer, pagesize=A5,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm
    )

    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        showBoundary=0
    )

    def draw_background_and_footer(canvas, doc):
        width, height = A5
        canvas.setFillColorRGB(0.9, 0.9, 1)
        canvas.rect(0, 0, width, height, stroke=0, fill=1)
        canvas.setFillColorRGB(0.8, 0.8, 1)
        canvas.roundRect(1 * cm, 1 * cm, width - 2 * cm, height - 2 * cm, 10, stroke=0, fill=1)
        canvas.saveState()
        canvas.setFont("Helvetica", 40)
        canvas.setFillColorRGB(0.7, 0.7, 0.7, alpha=0.2)
        canvas.translate(width / 2, height / 2)
        canvas.rotate(45)
        canvas.drawCentredString(0, 0, "EVENT TICKET")
        canvas.restoreState()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        canvas.saveState()
        canvas.setFont(font_name, 8)
        canvas.setFillColor(colors.HexColor("#333"))
        canvas.drawRightString(width - doc.rightMargin, 0.7 * cm, f"Printed: {timestamp}")
        canvas.restoreState()

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
        textColor=colors.HexColor('#333'),
        alignment=1, spaceAfter=0.5 * cm
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
        textColor=colors.HexColor('#B0B0B0'),
        alignment=1, spaceBefore=0.2 * cm
    )

    elements = []

    logo_path = os.path.join(settings.BASE_DIR, 'static/images/logo.png')
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=3 * cm, height=3 * cm)
        logo.hAlign = 'CENTER'
        elements.append(logo)

    elements.append(Spacer(1, 0.5 * cm))

    elements.append(Paragraph(reservation.event.title, title_style))


    elements.append(Paragraph(f"User: {request.user.username}", user_style))

    elements.append(Spacer(1, 0.5 * cm))

    data = [
        ['Location', reservation.event.location],
        ['Date', reservation.event.date.strftime('%B %d, %Y')],
        ['Tickets', str(reservation.quantity)],
        ['Paid', f"${reservation.total_price:.2f}"]
    ]

    if reservation.signature:
        data.append(['Code', reservation.signature])

    table = Table(data, colWidths=[4 * cm, doc.width - 4 * cm])
    table.setStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e0e0e0')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#555')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#aaa')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONT', (0, 0), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333')),
    ])
    elements.append(table)

    elements.append(Spacer(1, 0.7 * cm))

    qr = qrcode.make(f"ID:{reservation.id}|KEY:{reservation.secret_key}|USER:{request.user.username}")

    qr_buf = io.BytesIO()
    qr.save(qr_buf, format='PNG')
    qr_buf.seek(0)
    qr_img = Image(qr_buf, width=5 * cm, height=5 * cm)
    qr_img.hAlign = 'CENTER'
    elements.append(qr_img)

    elements.append(Paragraph(reservation.secret_key, secret_style))

    note = "This ticket grants one entry only. Present it at the entrance."
    elements.append(Paragraph(note, note_style))

    doc.build(elements)
    buffer.seek(0)

    fname = f"{reservation.event.title}_{request.user.username}_ticket.pdf".replace(' ', '_')
    return FileResponse(buffer, as_attachment=True, filename=fname)




def not_found_view(request, exception=None):
    return render(request, '404.html', status=404)
