# ai_service/embedding.py
import numpy as np
from sentence_transformers import SentenceTransformer

# Charger le modèle une seule fois (au démarrage)
_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer('all-MiniLM-L6-v2')  # léger, rapide, bon pour du contenu court
    return _model

def generate_embedding(text: str) -> list:
    model = get_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()  # JSON serializable

def cosine_similarity(vec1: list, vec2: list) -> float:
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))