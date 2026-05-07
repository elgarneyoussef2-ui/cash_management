import requests
import json
import base64
import os

# =========================================
# OAUTH TOKEN (PISTE)
# =========================================

CLIENT_ID = os.environ.get("PISTE_CLIENT_ID", "a42ee586-cdae-49b5-b395-c288ba46aeb7")
CLIENT_SECRET = os.environ.get("PISTE_CLIENT_SECRET", "de098e2c-d342-475b-80c8-05e5bd75ca59")

# Identifiants du COMPTE TECHNIQUE Chorus Pro (≠ compte personnel)
# À créer sur : https://chorus-pro.gouv.fr > Mon compte > Comptes techniques
CHORUS_LOGIN = os.environ.get("CHORUS_LOGIN", "")
CHORUS_PASSWORD = os.environ.get("CHORUS_PASSWORD", "")

oauth_url = "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"

payload = {
    "grant_type": "client_credentials",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET
}

headers = {
    "Content-Type": "application/x-www-form-urlencoded"
}

response = requests.post(oauth_url, data=payload, headers=headers)

print("STATUS TOKEN:", response.status_code)

if response.status_code != 200:
    print(response.text)
    exit()

token = response.json()["access_token"]

# =========================================
# API FACTURES CHORUS
# =========================================

api_url = "https://sandbox-api.piste.gouv.fr/cpro/factures/v1/rechercher/fournisseur"

cpro_account = base64.b64encode(f"{CHORUS_LOGIN}:{CHORUS_PASSWORD}".encode()).decode()

api_headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "cpro-account": cpro_account
}

# =========================================
# PAYLOAD MINIMAL (VALIDÉ)
# =========================================

search_payload = {
    "cadreFacturation": "A1_FACTURE_FOURNISSEUR",
    "modeDepot": "SAISIE_WEB",
    "typeFacture": "FACTURE",
    
    "periodeDateDepotDu": "2025-01-01",
    "periodeDateDepotAu": "2026-12-31",

    "rechercheFactureParFournisseur": {
        "pageResultatDemandee": 1,
        "nbResultatsParPage": 10
    }
}

# =========================================
# APPEL API
# =========================================

facture_response = requests.post(
    api_url,
    headers=api_headers,
    json=search_payload
)

print("\nSTATUS FACTURES:", facture_response.status_code)

try:
    print(json.dumps(facture_response.json(), indent=2, ensure_ascii=False))
except:
    print(facture_response.text)