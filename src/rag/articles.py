import os

import requests
from dotenv import load_dotenv
from oauth2 import get_legifrance_token

load_dotenv()

client_id = os.getenv("client_id") or os.getenv("CLIENT_ID")
client_secret = os.getenv("client_secret") or os.getenv("CLIENT_SECRET")
piste_env = (os.getenv("PISTE_ENV") or "prod").lower()


def _base_url() -> str:
    if piste_env == "prod":
        return "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"
    return "https://sandbox-api.piste.gouv.fr/dila/legifrance/lf-engine-app"


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def ping_api(token: str) -> None:
    response = requests.get(f"{_base_url()}/list/ping", headers=_auth_headers(token), timeout=20)
    if response.status_code != 200:
        raise Exception(f"Ping KO HTTP {response.status_code}: {response.text}")


def search_article_id(
    token: str,
    article_num: str = "L36-11",
    code_name: str = "Code des postes et des communications électroniques",
    version_ts: int = 1514802418000,
) -> str:
    # Essaie plusieurs formats de payload /search pour recuperer un identifiant LEGIARTI.
    # Le premier format suit l'exemple officiel du document fourni.
    url = f"{_base_url()}/search"
    headers = _auth_headers(token)
    payloads = [
        {
            "fond": "CODE_DATE",
            "recherche": {
                "champs": [
                    {
                        "typeChamp": "NUM_ARTICLE",
                        "criteres": [
                            {
                                "typeRecherche": "EXACTE",
                                "valeur": article_num,
                                "operateur": "ET",
                            }
                        ],
                        "operateur": "ET",
                    }
                ],
                "filtres": [
                    {"facette": "NOM_CODE", "valeurs": [code_name]},
                    {"facette": "DATE_VERSION", "singleDate": version_ts},
                ],
                "pageNumber": 1,
                "pageSize": 10,
                "operateur": "ET",
                "sort": "PERTINENCE",
                "typePagination": "ARTICLE",
            },
        },
        {
            "fond": "CODE_DATE",
            "recherche": {
                "champs": [
                    {
                        "typeChamp": "ALL",
                        "criteres": [
                            {
                                "typeRecherche": "UN_DES_MOTS",
                                "valeur": article_num,
                                "operateur": "ET",
                                "proximite": 2,
                            }
                        ],
                        "operateur": "ET",
                    }
                ],
                "fromAdvancedRecherche": False,
                "operateur": "ET",
                "pageNumber": 1,
                "pageSize": 10,
                "sort": "PERTINENCE",
                "typePagination": "ARTICLE",
            },
        },
        {
            "fond": "CODE_ETAT",
            "recherche": {
                "champs": [
                    {
                        "typeChamp": "NUM_ARTICLE",
                        "criteres": [
                            {
                                "typeRecherche": "EXACTE",
                                "valeur": article_num,
                                "operateur": "ET",
                            }
                        ],
                        "operateur": "ET",
                    }
                ],
                "filtres": [{"facette": "NOM_CODE", "valeurs": [code_name]}],
                "pageNumber": 1,
                "pageSize": 10,
                "operateur": "ET",
                "sort": "PERTINENCE",
                "typePagination": "ARTICLE",
            },
        },
        {
            "fond": "CODE_DATE",
            "query": {"text": f"article {article_num} {code_name}"},
            "pageNumber": 1,
            "pageSize": 10,
            "sort": "DATE_DESC",
        },
    ]
    errors = []

    for payload in payloads:
        response = requests.post(url, json=payload, headers=headers, timeout=25)
        if response.status_code != 200:
            errors.append(f"/search HTTP {response.status_code} payload={payload} body={response.text}")
            continue

        body = response.json()
        # Selon les versions, les resultats peuvent etre dans 'results' ou 'resultsList'
        candidates = body.get("results") or body.get("resultsList") or []
        for item in candidates:
            article_id = item.get("id") or item.get("articleId")
            if isinstance(article_id, str) and article_id.startswith("LEGIARTI"):
                return article_id
            # Certains formats imbriquent l'id dans un sous-objet
            text_data = item.get("text") or {}
            nested_id = text_data.get("id")
            if isinstance(nested_id, str) and nested_id.startswith("LEGIARTI"):
                return nested_id
            # Le format le plus frequent renvoie l'id d'article dans sections[].extracts[].
            for section in item.get("sections", []):
                for extract in section.get("extracts", []):
                    extract_id = extract.get("id")
                    if isinstance(extract_id, str) and extract_id.startswith("LEGIARTI"):
                        return extract_id
        errors.append(f"/search 200 mais aucun LEGIARTI trouve. Reponse: {body}")

    raise Exception("Echec /search:\n" + "\n".join(errors))


def get_article(token: str, cid_article: str) -> str:
    # Recupere le texte d'un article Legifrance.
    if not token:
        raise ValueError("Token manquant.")
    if not cid_article:
        raise ValueError("Identifiant d'article manquant.")

    api_urls = [f"{_base_url()}/consult/getArticle"]
    headers = _auth_headers(token)
    payload = {"id": cid_article}
    errors = []

    for url in api_urls:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        if response.status_code != 200:
            errors.append(f"{url} -> HTTP {response.status_code}: {response.text}")
            continue

        body = response.json()
        article = body.get("article", {})
        text_plain = article.get("texte") or article.get("text", {}).get("text")
        if text_plain:
            return text_plain
        errors.append(f"{url} -> Reponse inattendue: {body}")

    env_hint = (
        "Verifie que ton token et l'API cible sont dans le meme environnement "
        "(prod ou sandbox) et que ton app PISTE est bien autorisee a l'API Legifrance."
    )
    raise Exception("Echec getArticle sur tous les endpoints:\n" + "\n".join(errors) + "\n" + env_hint)


if __name__ == "__main__":
    try:
        token = get_legifrance_token(client_id, client_secret)
        print("OAuth2 OK")
        ping_api(token)
        print("Ping API OK")

        article_id = search_article_id(token)
        print("Article ID trouve:", article_id)

        article = get_article(token, article_id)
        print("Recuperation article OK")
        print("Debut du texte:", article[:300], "...")
    except Exception as e:
        print("Recuperation article KO:", e)