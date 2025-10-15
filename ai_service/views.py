from django.shortcuts import render

# ai_service/views.py
from django.shortcuts import render, get_object_or_404
from event_service.models import Event
from .recommender import get_recommendations_for_event
from .utils import update_event_embedding

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
from .chatbot import generate_response
from .chatbot import get_llm
from django.views.decorators.http import require_GET

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

@csrf_exempt
@require_POST
def chat_view(request):
    try:
        data = json.loads(request.body)
        question = data.get("question", "").strip()
        if not question:
            return JsonResponse({"error": "Question manquante"}, status=400)

        # Récupérer ou initialiser l'historique
        history = request.session.get('chat_history', [])
        history.append({"role": "user", "content": question})

        # Générer contexte avec historique (optionnel)
        answer = generate_response(question)

        # Sauvegarder la réponse dans l'historique
        history.append({"role": "assistant", "content": answer})

        # Garder seulement les 10 derniers messages (5 tours)
        if len(history) > 10:
            history = history[-10:]

        request.session['chat_history'] = history

        return JsonResponse({"answer": answer})
    
    except Exception as e:
    # Log l'erreur dans la console pour déboguer
        print(f"❌ Erreur dans chat_view : {e}")
        return JsonResponse({
            "answer": "Désolé, une erreur est survenue. Réessayez plus tard.",
            "error": str(e)  # Pour debug
        })



def chat_health_view(request):
    try:
        llm = get_llm()
        # Test simple : générer un token
        test = llm("Bonjour", max_tokens=1, echo=False)
        return JsonResponse({
            "status": "ok",
            "model_loaded": True,
            "message": "Phi-3-mini is ready."
        })
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "model_loaded": False,
            "error": str(e)
        }, status=500)

@require_GET
def chat_history_view(request):
    history = request.session.get('chat_history', [])
    return JsonResponse({"history": history})