from rest_framework import generics
from django.shortcuts import render, get_object_or_404
from .models import Event, Reservation
from .serializers import EventSerializer
from django.contrib.auth.decorators import login_required
from user_service.models import UserProfile



# API Views

class EventCreateView(generics.CreateAPIView):
    queryset = Event.objects.all()
    serializer_class = EventSerializer

class EventDetailUpdateView(generics.RetrieveUpdateAPIView):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    lookup_field = 'id'

def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    is_organizer = event.organizer == request.user

    total_reservations = Reservation.objects.filter(event=event).count()
    total_revenue = Reservation.objects.filter(event=event).aggregate(
        total=Sum('total_price')
    )['total'] or 0

    # Préparer les stats par ambassadeur
    ambassador_stats = []
    ambassadors = event.ambassadors.all()

    for ambassador in ambassadors:
        reservations = Reservation.objects.filter(event=event, ambassador=ambassador)
        total_reservations_by_amb = reservations.count()
        total_places_by_amb = reservations.aggregate(total=Sum('quantity'))['total'] or 0
        total_revenue_by_amb = reservations.aggregate(total=Sum('total_price'))['total'] or 0

        ambassador_stats.append({
            'user': ambassador,
            'reservations_count': total_reservations_by_amb,
            'places': total_places_by_amb,
            'revenue': total_revenue_by_amb,
        })

    context = {
        'event': event,
        'is_organizer': is_organizer,
        'total_reservations': total_reservations,
        'total_revenue': total_revenue,
        'ambassadors': ambassador_stats,  # ✅ liste de dicts avec stats
    }
    return render(request, 'detail_event.html', context)



