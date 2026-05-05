import requests
import streamlit as st
import base64
from datetime import datetime


class ChorusProAPI:
    """Connector for Chorus Pro API via PISTE."""

    SANDBOX_TOKEN_URL = "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"
    PROD_TOKEN_URL    = "https://oauth.piste.gouv.fr/api/oauth/token"
    SANDBOX_BASE_URL  = "https://sandbox-api.piste.gouv.fr/cpro/factures/v1"
    PROD_BASE_URL     = "https://api.piste.gouv.fr/cpro/factures/v1"

    def __init__(self, client_id: str, client_secret: str,
                 cpro_login: str = "", cpro_password: str = "",
                 mode: str = "sandbox"):
        self.client_id     = client_id.strip()
        self.client_secret = client_secret.strip()
        self.mode          = mode

        if cpro_login and cpro_password:
            auth_str = f"{cpro_login.strip()}:{cpro_password.strip()}"
            self.cpro_account = base64.b64encode(auth_str.encode()).decode()
        else:
            self.cpro_account = None

        if mode == "production":
            self.token_url = self.PROD_TOKEN_URL
            self.base_url  = self.PROD_BASE_URL
        else:
            self.token_url = self.SANDBOX_TOKEN_URL
            self.base_url  = self.SANDBOX_BASE_URL

        self.token = None

    # ── Auth ──────────────────────────────────────────────────────────────────

    def get_token(self) -> str | None:
        """
        Obtient un token OAuth2 PISTE via client_credentials.
        Essaie plusieurs combinaisons de scope selon la configuration de l'app.
        """
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept":       "application/json",
        }
        base_payload = {
            "grant_type":    "client_credentials",
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
        }
        # Sans scope d'abord (app sans scope configuré), puis avec openid
        scope_attempts = [None, "openid", "openid profile"]

        try:
            for scope in scope_attempts:
                payload = dict(base_payload)
                if scope:
                    payload["scope"] = scope

                resp = requests.post(
                    self.token_url, headers=headers, data=payload, timeout=15
                )

                if resp.status_code == 200:
                    data = resp.json()
                    self.token = data.get("access_token")
                    if self.token:
                        return self.token

                # 400 on token = bad request (wrong params), stop trying this scope
                if resp.status_code == 400:
                    try:
                        err_body = resp.json()
                    except Exception:
                        err_body = resp.text
                    st.error(
                        f"❌ **400 - Requête token invalide** (scope={scope!r})\n\n"
                        f"**Réponse PISTE :** `{err_body}`\n\n"
                        "**Cause probable :** L'application PISTE n'a pas de scope configuré.\n"
                        "**Solution :** Sur piste.gouv.fr → votre app → Modifier → "
                        "onglet **Authentification** → section **Scopes** → "
                        "ajouter `openid` → Sauvegarder."
                    )
                    return None

            # All attempts failed with non-400 codes
            st.error(
                "❌ Authentification PISTE échouée après plusieurs tentatives. "
                "Vérifiez vos identifiants."
            )
            return None

        except requests.exceptions.ConnectionError:
            st.error("🔌 Impossible de joindre le serveur PISTE. Vérifiez votre connexion internet.")
            return None
        except Exception as exc:
            st.error(f"Erreur inattendue lors de l'authentification : {exc}")
            return None

    def _ensure_token(self) -> bool:
        if not self.token:
            return bool(self.get_token())
        return True

    def _headers(self) -> dict:
        h = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }
        if self.cpro_account:
            h["cpro-account"] = self.cpro_account
        return h

    # ── Connection test ───────────────────────────────────────────────────────

    def test_connection(self) -> dict:
        token = self.get_token()
        if token:
            return {"ok": True, "message": "Connexion PISTE réussie — token OAuth2 obtenu."}
        return {"ok": False, "message": "Échec de connexion PISTE."}

    # ── Invoice submission ────────────────────────────────────────────────────

    def submit_invoice(self, invoice_data: dict) -> dict:
        if not self._ensure_token():
            return {"status": "error", "message": "Authentification échouée."}

        if self.mode == "sandbox":
            return {
                "status":  "success",
                "message": "Soumission simulée (Sandbox)",
                "id":      f"SANDBOX-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            }

        url = f"{self.base_url}/soumettre"
        payload = {
            "idStructureFournisseur":  invoice_data.get("issuer_siret", ""),
            "idStructureDestinataire": invoice_data.get("recipient_siret", ""),
            "codeServiceDestinataire": invoice_data.get("service_code", ""),
            "devise":                  invoice_data.get("currency", "EUR"),
            "montantTTC":              invoice_data.get("amount", 0),
            "dateFacture":             invoice_data.get("date", ""),
            "numeroFacture":           invoice_data.get("number", ""),
            "cadreFacturation":        "A1_FACTURE_FOURNISSEUR",
        }
        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
            resp.raise_for_status()
            return {"status": "success", "data": resp.json()}
        except requests.exceptions.HTTPError as exc:
            return {
                "status":  "error",
                "message": f"HTTP {exc.response.status_code} : {exc.response.text[:300]}",
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    # ── Fetch received invoices ───────────────────────────────────────────────

    def fetch_received_invoices(self, siret: str, date_from: str = "2026-01-01") -> list:
        if not self._ensure_token():
            return []

        url = f"{self.base_url}/rechercher/recipiendaire"
        payload = {
            "idDestinataire":        siret,
            "periodeDateEmissionDu": date_from,
            "nbResultatsParPage":    50,
            "pageCourante":          1,
        }

        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)

            if resp.status_code == 200:
                return resp.json().get("listeFactures", [])

            # Afficher le corps complet pour le diagnostic
            try:
                err_body = resp.json()
            except Exception:
                err_body = resp.text

            if resp.status_code == 400:
                st.error(
                    f"❌ **400 - Requête API Factures invalide**\n\n"
                    f"**URL appelée :** `{url}`\n\n"
                    f"**Corps envoyé :** `{payload}`\n\n"
                    f"**Réponse Chorus :** `{err_body}`"
                )
            elif resp.status_code == 404:
                st.info("Aucune facture trouvée pour ce SIRET dans la période indiquée.")
            elif resp.status_code == 403:
                st.error(
                    "🛑 **403 - Accès refusé à l'API Factures.**\n\n"
                    "Vérifiez que l'API **Factures v1.0.0** est bien souscrite "
                    "et raccordée à votre application SANDBOX dans PISTE."
                )
            else:
                st.warning(f"Erreur Chorus Pro {resp.status_code} : `{err_body}`")

            return []

        except requests.exceptions.ConnectionError:
            st.error("🔌 Impossible de joindre le serveur PISTE.")
            return []
        except Exception as exc:
            st.warning(f"Erreur lors de l'appel Chorus : {exc}")
            return []

    # ── Mock data ─────────────────────────────────────────────────────────────

    def fetch_mock_data(self) -> list:
        return [
            {
                "invoice_number":    "CHORUS-2026-001",
                "invoice_type":      "SUPPLIER",
                "counterparty_name": "Orange Business",
                "amount_ttc":        149.99,
                "currency":          "EUR",
                "issue_date":        "2026-05-01",
                "due_date":          "2026-05-31",
                "product":           "Abonnement Fibre Pro",
                "quantity":          1,
                "note":              "Importé via Chorus Pro API (démo)",
            },
            {
                "invoice_number":    "CHORUS-2026-002",
                "invoice_type":      "SUPPLIER",
                "counterparty_name": "EDF Entreprises",
                "amount_ttc":        850.00,
                "currency":          "EUR",
                "issue_date":        "2026-05-05",
                "due_date":          "2026-06-05",
                "product":           "Consommation Électrique Mai",
                "quantity":          1,
                "note":              "Importé via Chorus Pro API (démo)",
            },
            {
                "invoice_number":    "CHORUS-2026-003",
                "invoice_type":      "CUSTOMER",
                "counterparty_name": "Ministère de l'Économie",
                "amount_ttc":        12500.00,
                "currency":          "EUR",
                "issue_date":        "2026-04-15",
                "due_date":          "2026-05-15",
                "product":           "Prestation de conseil",
                "quantity":          5,
                "note":              "Facture publique — Chorus Pro (démo)",
            },
        ]
