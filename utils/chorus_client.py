import requests
import base64

_PISTE_ID     = "a42ee586-cdae-49b5-b395-c288ba46aeb7"
_PISTE_SECRET = "de098e2c-d342-475b-80c8-05e5bd75ca59"
_SANDBOX      = True


def _endpoints(sandbox):
    if sandbox:
        return (
            "https://sandbox-oauth.piste.gouv.fr/api/oauth/token",
            "https://sandbox-api.piste.gouv.fr/cpro/factures/v1",
        )
    return (
        "https://oauth.piste.gouv.fr/api/oauth/token",
        "https://api.piste.gouv.fr/cpro/factures/v1",
    )


def get_token(sandbox=_SANDBOX):
    oauth_url, _ = _endpoints(sandbox)
    r = requests.post(
        oauth_url,
        data={"grant_type": "client_credentials",
              "client_id": _PISTE_ID, "client_secret": _PISTE_SECRET},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _headers(token, login, password):
    cpro = base64.b64encode(f"{login}:{password}".encode()).decode()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "cpro-account":  cpro,
    }


def fetch_factures_fournisseur(login, password, date_du, date_au, sandbox=_SANDBOX, token=None):
    """Factures émises par le fournisseur connecté → créances clients."""
    token = token or get_token(sandbox)
    _, base = _endpoints(sandbox)
    r = requests.post(
        f"{base}/rechercher/fournisseur",
        headers=_headers(token, login, password),
        json={
            "periodeDateDepotDu": str(date_du),
            "periodeDateDepotAu": str(date_au),
            "rechercheFactureParFournisseur": {
                "pageResultatDemandee": 1,
                "nbResultatsParPage":   50,
            },
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("listeFactures", [])


def fetch_factures_recipiendaire(login, password, date_du, date_au, sandbox=_SANDBOX, token=None):
    """Factures reçues par le destinataire connecté → dettes fournisseurs."""
    token = token or get_token(sandbox)
    _, base = _endpoints(sandbox)
    r = requests.post(
        f"{base}/rechercher/recipiendaire",
        headers=_headers(token, login, password),
        json={
            "periodeDateDepotDu": str(date_du),
            "periodeDateDepotAu": str(date_au),
            "paramRecherche": {
                "pageResultatDemandee": 1,
                "nbResultatsParPage":   50,
            },
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("listeFactures", [])
