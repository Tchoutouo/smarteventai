# ai_service/chatbot.py
import os
from pathlib import Path
from llama_cpp import Llama
from django.conf import settings
from event_service.models import Event
from ai_service.models import EventEmbedding
from ai_service.embedding import cosine_similarity, generate_embedding

# Charger le modèle une seule fois
_model = None

def get_llm():
    global _model
    if _model is None:
        model_path = Path(settings.BASE_DIR) / "ai_service" / "models" / "Phi-3-mini-4k-instruct-q4.gguf"
        if not model_path.exists():
            raise FileNotFoundError(f"Modèle non trouvé : {model_path}")
        _model = Llama(
            model_path=str(model_path),
            n_ctx=4096,
            n_threads=4,
            n_gpu_layers=0,
            verbose=False
        )
    return _model

def get_platform_context():
    return """
    - Les utilisateurs peuvent réserver via la page publique d'un événement (/event/<id>/).
    - Les ambassadeurs ont un lien de partage avec ?ref=id.
    - Les organisateurs gèrent leurs événements via /organizer/<token>/dashboard/.
    - Les billets sont dans /attendee-tickets/<token>/
    - Un utilisateur ne peut supprimer une réservation que dans les 3 heures suivant la réservation.
    - Pour contacter le support, aller sur /complaints/new/.
    - La recherche d'événements se fait via la barre de recherche sur la page d'accueil.
    """

def semantic_search_events(query: str, top_k=3):
    """Retourne les événements les plus pertinents via embeddings."""
    try:
        query_vec = generate_embedding(query)
        candidates = EventEmbedding.objects.select_related('event').all()
        scored = []
        for emb in candidates:
            score = cosine_similarity(query_vec, emb.vector)
            scored.append((emb.event, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [event for event, _ in scored[:top_k]]
    except Exception as e:
        print(f"Erreur recherche sémantique : {e}")
        return Event.objects.filter(is_deleted=False)[:top_k]

def get_relevant_events_context(query: str):
    events = semantic_search_events(query)
    if not events:
        return "Aucun événement disponible."
    context = "Événements pertinents :\n"
    for e in events:
        context += f"- {e.title} à {e.location} le {e.date}. Prix: ${e.ticket_price}. Places: {e.available_tickets}\n"
    return context

def generate_response(question: str) -> str:
    llm = get_llm()
    
    platform_ctx = get_platform_context()
    events_ctx = get_relevant_events_context(question)
    
    prompt = f"""<|system|>
Tu es un assistant IA utile de SmartEventAI. Réponds en français, de façon concise et précise.
Utilise uniquement les informations ci-dessous. Si tu ne sais pas, dis "Je ne sais pas".

Informations :
{platform_ctx}

{events_ctx}
<|user|>
{question}
<|end|>
<|assistant|>"""

    try:
        output = llm(
            prompt,
            max_tokens=300,
            temperature=0.3,
            stop=["<|end|>", "<|user|>", "\n\n"],
            echo=False
        )
        response = output["choices"][0]["text"].strip()
        if response.startswith("<|assistant|>"):
            response = response[len("<|assistant|>"):]
        return response or "Je ne peux pas répondre à cette question."
    except Exception as e:
        return "Désolé, une erreur est survenue. Réessayez plus tard."