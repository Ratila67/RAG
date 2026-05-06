import os

import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("client_id") or os.getenv("CLIENT_ID")
client_secret = os.getenv("client_secret") or os.getenv("CLIENT_SECRET")


def get_legifrance_token(client_id: str, client_secret: str) -> str:
    # Obtient un token d'acces OAuth2 pour l'API Legifrance.
    if not client_id or not client_secret:
        raise ValueError("Variables client_id/client_secret manquantes.")

    token_urls = [
        "https://oauth.piste.gouv.fr/api/oauth/token",  # production
        "https://sandbox-oauth.piste.gouv.fr/api/oauth/token",  # sandbox
    ]
    errors = []

    for url in token_urls:
        payload = {"grant_type": "client_credentials", "scope": "openid"}

        # 1) Methode recommandee OAuth2: client auth via HTTP Basic.
        response = requests.post(url, data=payload, auth=(client_id, client_secret), timeout=20)
        if response.status_code == 200:
            return response.json()["access_token"]
        errors.append(f"{url} | Basic auth -> HTTP {response.status_code}: {response.text}")

        # 2) Fallback: certains serveurs acceptent aussi les identifiants dans le body.
        fallback_payload = {
            "grant_type": "client_credentials",
            "scope": "openid",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        fallback_response = requests.post(url, data=fallback_payload, timeout=20)
        if fallback_response.status_code == 200:
            return fallback_response.json()["access_token"]
        errors.append(
            f"{url} | Body auth  -> HTTP {fallback_response.status_code}: {fallback_response.text}"
        )

    raise Exception("Echec OAuth2 sur tous les endpoints:\n" + "\n".join(errors))


if __name__ == "__main__":
    try:
        token = get_legifrance_token(client_id, client_secret)
        print("Connexion OAuth2 OK")
        print("Token recu (debut):", token[:20], "...")
    except Exception as e:
        print("Connexion OAuth2 KO:", e)