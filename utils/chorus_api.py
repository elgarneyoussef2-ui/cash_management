import requests
import streamlit as st
import base64
from datetime import datetime

class ChorusProAPI:
    """Connector for Chorus Pro API via PISTE."""
    
    def __init__(self, client_id, client_secret, cpro_login, cpro_password, mode="sandbox"):
        # Strip potential spaces from IDs
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.mode = mode
        
        # CPRO-ACCOUNT Header: base64('login:password')
        auth_str = f"{cpro_login.strip()}:{cpro_password.strip()}"
        self.cpro_account = base64.b64encode(auth_str.encode()).decode()
        
        if mode == "production":
            self.token_url = "https://oauth.piste.gouv.fr/cas/oauth2.0/token"
            self.base_url = "https://api.piste.gouv.fr/cpro/factures"
        else:
            self.token_url = "https://sandbox-oauth.piste.gouv.fr/cas/oauth2.0/token"
            self.base_url = "https://sandbox-api.piste.gouv.fr/cpro/factures"
            
        self.token = None

    def _get_headers(self):
        """Returns standard headers including OAuth2 and CPRO-ACCOUNT."""
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
            'cpro-account': self.cpro_account,
            'User-Agent': 'TreasuryDashboard/1.0'
        }

    def get_token(self):
        """Ultra-simplified authentication for PISTE."""
        # We send EVERYTHING in the body, which is the most compatible mode for PISTE Sandbox
        payload = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': 'openid' # Try with openid first
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        try:
            # First attempt: standard body-only
            response = requests.post(self.token_url, headers=headers, data=payload, timeout=15)
            
            if response.status_code != 200:
                # Second attempt: remove scope (sometimes problematic)
                payload.pop('scope', None)
                response = requests.post(self.token_url, headers=headers, data=payload, timeout=15)

            if response.status_code == 403:
                st.error("🛑 **Access Denied persistante**")
                st.info("💡 **Dernier recours** : Vérifiez que l'état de votre application sur PISTE est bien **'Activée'** (pas seulement 'Validée').")
                return None

            response.raise_for_status()
            self.token = response.json().get('access_token')
            return self.token
        except Exception as e:
            st.error(f"Erreur d'authentification Chorus Pro : {e}")
            return None

    def submit_invoice(self, invoice_data):
        if not self.token and not self.get_token():
            return {"status": "error", "message": "Auth failed"}

        url = f"{self.base_url}/v1/soumettre"
        headers = self._get_headers()
        
        payload = {
            "idStructureFournisseur": invoice_data.get('issuer_siret'),
            "idStructureDestinataire": invoice_data.get('recipient_siret'),
            "codeServiceDestinataire": invoice_data.get('service_code'),
            "devise": invoice_data.get('currency', 'EUR'),
            "montantTTC": invoice_data.get('amount'),
            "dateFacture": invoice_data.get('date'),
            "numeroFacture": invoice_data.get('number'),
            "cadreFacturation": "A1_FACTURE_FOURNISSEUR"
        }
        
        if self.mode == "sandbox":
            return {"status": "success", "message": "Soumission simulée réussie", "id": "MOCK-ID-123"}
            
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return {"status": "success", "data": response.json()}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def fetch_received_invoices(self, siret, date_from="2026-01-01"):
        if not self.token and not self.get_token():
            return []

        url = f"{self.base_url}/v1/rechercher/recipiendaire"
        headers = self._get_headers()
        
        payload = {
            "idDestinataire": siret,
            "periodeDateEmissionDu": date_from,
            "nbResultatsParPage": 50,
            "pageCourante": 1
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json().get('listeFactures', [])
        except Exception as e:
            st.warning(f"Note: Erreur lors de l'appel Chorus : {e}")
            return []

    def fetch_mock_data(self):
        """Returns mock data for demonstration purposes if Sandbox is empty."""
        return [
            {
                "invoice_number": "CHORUS-2026-001",
                "invoice_type": "SUPPLIER",
                "counterparty_name": "Orange Business",
                "amount_ttc": 149.99,
                "currency": "EUR",
                "issue_date": "2026-05-01",
                "due_date": "2026-05-31",
                "product": "Abonnement Fibre Pro",
                "quantity": 1,
                "note": "Importé via Chorus Pro API"
            },
            {
                "invoice_number": "CHORUS-2026-002",
                "invoice_type": "SUPPLIER",
                "counterparty_name": "EDF Entreprises",
                "amount_ttc": 850.00,
                "currency": "EUR",
                "issue_date": "2026-05-05",
                "due_date": "2026-06-05",
                "product": "Consommation Électrique Mai",
                "quantity": 1,
                "note": "Importé via Chorus Pro API"
            }
        ]
