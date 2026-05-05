import requests
import streamlit as st
from datetime import datetime

class ChorusProAPI:
    """Connector for Chorus Pro Sandbox API via PISTE."""
    
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = "https://sandbox-oauth.piste.gouv.fr/cas/oauth2.0/token"
        self.base_url = "https://sandbox-api.piste.gouv.fr/cpro/factures"
        self.token = None

    def get_token(self):
        """Authenticates and retrieves an OAuth2 token."""
        payload = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': 'openid'
        }
        try:
            response = requests.post(self.token_url, data=payload)
            response.raise_for_status()
            self.token = response.json().get('access_token')
            return self.token
        except Exception as e:
            st.error(f"Erreur d'authentification Chorus Pro : {e}")
            return None

    def fetch_received_invoices(self, siret, date_from="2026-01-01"):
        """Fetches received invoices (Supplier invoices) for a given SIRET."""
        if not self.token and not self.get_token():
            return []

        url = f"{self.base_url}/v1/rechercher/recipiendaire"
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
        
        # Payload based on Chorus Pro documentation
        payload = {
            "idDestinataire": siret,
            "periodeDateEmissionDu": date_from,
            "nbResultatsParPage": 50,
            "pageCourante": 1
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            # In a real scenario, we would parse the list of invoices
            # Here we return a mock list for demonstration in Sandbox mode
            data = response.json()
            return data.get('listeFactures', [])
        except Exception as e:
            st.warning(f"Note: Connexion Sandbox établie mais erreur de récupération : {e}")
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
