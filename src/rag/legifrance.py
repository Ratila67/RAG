import time
import requests
from typing import Iterator
from .config import Settings

OAUTH_URLS = {
    "prod": "https://oauth.piste.gouv.fr/api/oauth/token",
    "sandbox": "https://sandbox-oauth.piste.gouv.fr/api/oauth/token",
}
API_URLS = {
    "prod": "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app",
    "sandbox": "https://sandbox-api.piste.gouv.fr/dila/legifrance/lf-engine-app",
}

class LegifranceClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._token: str | None = None
        self._token_exp: float = 0.0
        self._session = requests.Session()
        # On obtient le token UNE FOIS au démarrage.
        self._refresh_token()

    @property
    def base_url(self) -> str:
        return API_URLS.get(self.settings.piste_env, API_URLS["prod"])

    def _oauth_url(self) -> str:
        return OAUTH_URLS.get(self.settings.piste_env, OAUTH_URLS["prod"])

    def _refresh_token(self) -> None:
        resp = self._session.post(
            self._oauth_url(),
            data={"grant_type": "client_credentials", "scope": "openid"},
            auth=(self.settings.client_id, self.settings.client_secret),
            timeout=20,
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        # expires_in en secondes ; petite marge.
        self._token_exp = time.time() + int(body.get("expires_in", 3600)) - 30

    def _headers(self) -> dict:
        if not self._token or time.time() >= self._token_exp:
            self._refresh_token()
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        resp = self._session.post(url, json=payload, headers=self._headers(), timeout=30)
        if resp.status_code == 401:
            # token expiré côté serveur =>refresh et retry une fois
            self._refresh_token()
            resp = self._session.post(url, json=payload, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()

    def ping(self) -> None:
        resp = self._session.get(f"{self.base_url}/list/ping", headers=self._headers(), timeout=20)
        resp.raise_for_status()

    def iter_code_article_ids(self, page_size: int = 100) -> Iterator[str]:
        """Itère tous les LEGIARTI du Code du travail via /search paginé."""
        page = 1
        seen: set[str] = set()
        while True:
            payload = {
                "fond": "CODE_ETAT",
                "recherche": {
                    "champs": [{
                        "typeChamp": "ALL",
                        "criteres": [{"typeRecherche": "TOUS_LES_MOTS_DANS_UN_CHAMP",
                                       "valeur": "*", "operateur": "ET"}],
                        "operateur": "ET",
                    }],
                    "filtres": [{"facette": "NOM_CODE", "valeurs": [self.settings.code_name]}],
                    "pageNumber": page, "pageSize": page_size,
                    "operateur": "ET", "sort": "PERTINENCE",
                    "typePagination": "ARTICLE",
                },
            }
            body = self._post("/search", payload)
            results = body.get("results") or []
            if not results:
                break
            new_count = 0
            for item in results:
                for section in item.get("sections", []):
                    for extract in section.get("extracts", []):
                        aid = extract.get("id")
                        if isinstance(aid, str) and aid.startswith("LEGIARTI") and aid not in seen:
                            seen.add(aid); new_count += 1
                            yield aid
            if new_count == 0:
                break
            page += 1

    def get_article(self, legiarti_id: str) -> dict:
        body = self._post("/consult/getArticle", {"id": legiarti_id})
        article = body.get("article") or {}
        text = article.get("texte") or (article.get("text") or {}).get("text") or ""
        return {
            "id": legiarti_id,
            "num": article.get("num"),
            "title": article.get("titre") or article.get("title"),
            "texte": text,
            "etat": article.get("etat"),
            "date_debut": article.get("dateDebut"),
        }