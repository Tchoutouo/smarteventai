# ai_service/download_model.py
import os
import sys
from pathlib import Path
import urllib.request
import tarfile
import zipfile

def download_phi3_model():
    BASE_DIR = Path(__file__).resolve().parent.parent
    MODEL_DIR = BASE_DIR / "ai_service" / "models"
    MODEL_PATH = MODEL_DIR / "Phi-3-mini-4k-instruct-q4.gguf"

    if MODEL_PATH.exists():
        print("✅ Modèle déjà présent.")
        return

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    url = "https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf"
    print("📥 Téléchargement du modèle Phi-3-mini (2.3 Go)...")
    print("⚠️ Cela peut prendre plusieurs minutes.")

    def progress_hook(count, block_size, total_size):
        percent = int(count * block_size * 100 / total_size)
        sys.stdout.write(f"\rProgress: {percent}%")
        sys.stdout.flush()

    try:
        urllib.request.urlretrieve(url, MODEL_PATH, reporthook=progress_hook)
        print("\n✅ Modèle téléchargé avec succès !")
    except Exception as e:
        print(f"\n❌ Erreur : {e}")
        if MODEL_PATH.exists():
            MODEL_PATH.unlink()

if __name__ == "__main__":
    download_phi3_model()