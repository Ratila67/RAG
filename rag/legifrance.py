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

    def _extract_legiarti_ids(self, obj) -> set[str]:
        """Extrait récursivement tous les identifiants `LEGIARTI...` d'un objet JSON."""
        out: set[str] = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in {"id", "articleId"} and isinstance(v, str) and v.startswith("LEGIARTI"):
                    out.add(v)
                out |= self._extract_legiarti_ids(v)
        elif isinstance(obj, list):
            for v in obj:
                out |= self._extract_legiarti_ids(v)
        return out

    def iter_code_article_ids_from_table_matieres(
        self, date: str | None = None, include_all_versions: bool = False
    ) -> set[str]:
        """Récupère les IDs d'articles via la table des matières du code.

        Endpoint Swagger: POST `/consult/legi/tableMatieres` (nature='CODE').
        - Si `include_all_versions=False`, on se limite aux sections/articles directement listés
          dans la table des matières (c'est généralement ce qu'on veut pour un RAG).
        - Si `include_all_versions=True`, on extrait tous les `LEGIARTI` présents dans le JSON,
          ce qui peut inclure beaucoup de versions.
        """
        query_date = date or time.strftime("%Y-%m-%d")
        body = self._post(
            "/consult/legi/tableMatieres",
            {"date": query_date, "nature": "CODE", "textId": self.settings.code_legitext},
        )
        if include_all_versions:
            return self._extract_legiarti_ids(body)
        # Par défaut, on prend les listes au 1er niveau si elles existent.
        ids: set[str] = set()
        if isinstance(body, dict):
            for art in body.get("articles") or []:
                if isinstance(art, dict):
                    aid = art.get("id") or art.get("articleId")
                    if isinstance(aid, str) and aid.startswith("LEGIARTI"):
                        ids.add(aid)
            for sec in body.get("sections") or []:
                ids |= self._extract_legiarti_ids(sec)
        return ids

    def iter_code_article_ids(
        self,
        page_size: int = 100,
        max_pages: int = 5000,
        stagnant_pages_limit: int = 25,
    ) -> Iterator[str]:
        """Itère les LEGIARTI du Code du travail.

        Stratégie:
        1) Essaye la table des matières `/consult/legi/tableMatieres` (exhaustif).
        2) Fallback sur `/search` (peut être très incomplet selon l'API).
        """

        try:
            ids = sorted(self.iter_code_article_ids_from_table_matieres())
            if ids:
                for aid in ids:
                    yield aid
                return
        except Exception:
            # Pas autorisé / endpoint indisponible => on tombera sur /search
            pass

        # 2) Fallback /search (souvent incomplet)
        page = 1
        seen: set[str] = set()
        stagnant_pages = 0

        while page <= max_pages:
            payload = {
                "fond": "CODE_ETAT",
                # IMPORTANT: pagination au niveau racine
                "pageNumber": page,
                "pageSize": page_size,
                "recherche": {
                    "champs": [{
                        "typeChamp": "ALL",
                        "criteres": [{
                            "typeRecherche": "TOUS_LES_MOTS_DANS_UN_CHAMP",
                            "valeur": "*",
                            "operateur": "ET",
                        }],
                        "operateur": "ET",
                    }],
                    # IMPORTANT: facette TEXT_NOM_CODE (pas NOM_CODE)
                    "filtres": [{"facette": "TEXT_NOM_CODE", "valeurs": [self.settings.code_name]}],
                    "operateur": "ET",
                    "sort": "PERTINENCE",
                    "typePagination": "ARTICLE",
                },
            }

            body = self._post("/search", payload)
            results = body.get("results") or []
            if not results:
                break

            new_count = 0
            for item in results:
                # Garde-fou: vérifier que le résultat appartient au bon LEGITEXT
                in_target_code = False
                for t in item.get("titles") or []:
                    if t.get("cid") == self.settings.code_legitext:
                        in_target_code = True
                        break
                    item_id = t.get("id")
                    if isinstance(item_id, str) and item_id.startswith(self.settings.code_legitext):
                        in_target_code = True
                        break
                if not in_target_code:
                    continue

                for section in item.get("sections") or []:
                    for extract in section.get("extracts") or []:
                        aid = extract.get("id")
                        if isinstance(aid, str) and aid.startswith("LEGIARTI") and aid not in seen:
                            seen.add(aid)
                            new_count += 1
                            yield aid

            if new_count == 0:
                stagnant_pages += 1
            else:
                stagnant_pages = 0

            if stagnant_pages >= stagnant_pages_limit:
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