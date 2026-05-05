import streamlit as st  # type: ignore
import pandas as pd  # type: ignore
import plotly.express as px  # type: ignore
from datetime import datetime, date, timedelta

import openpyxl  # type: ignore

from db.database import get_db, get_table
from utils.config import BLUE, GREEN, RED, AMBER, apply_chart_theme
from utils.chorus_api import ChorusProAPI
from components.navbar import page_header

_EXCEL_PATH = "treasury_master.xlsx"
_CCY_OPTIONS = ["EUR", "SEK", "PLN", "USD"]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _calculate_bfr_metrics():
    fx = {
        "EUR": 1.0,
        "SEK": 1.0 / st.session_state.get("fx_eur_sek", 11.5),
        "PLN": 1.0 / st.session_state.get("fx_eur_pln", 4.15),
        "USD": 1.0 / st.session_state.get("fx_eur_usd", 1.09),
    }
    inv = get_table("invoices")
    if inv.empty:
        return {"creances": 0.0, "dettes": 0.0, "bfr": 0.0, "dso": 0.0, "dpo": 0.0}
    df_inv = inv[inv["status"] == "PENDING"].copy()
    df_inv["eur"] = df_inv.apply(
        lambda r: float(r["amount_ttc"] or 0) * fx.get(str(r["currency"]), 1.0), axis=1
    )
    creances = float(df_inv[df_inv["invoice_type"] == "CUSTOMER"]["eur"].sum())
    dettes   = float(df_inv[df_inv["invoice_type"] == "SUPPLIER"]["eur"].sum())

    tx = get_table("transactions")
    if not tx.empty:
        curr_month = datetime.now().strftime("%Y-%m")
        df_ca  = tx[(tx["category"] == "REVENUE") & (tx["type"] == "IN")
                    & (tx["date"].astype(str).str.startswith(curr_month))]
        df_ach = tx[(tx["type"] == "OUT") & (tx["date"].astype(str).str.startswith(curr_month))]
        ca_mois    = max(float(df_ca["amount_eur"].sum()), 1.0)
        achats_mois = max(float(df_ach["amount_eur"].sum()), 1.0)
    else:
        ca_mois = achats_mois = 1.0

    return {
        "creances": creances,
        "dettes":   dettes,
        "bfr":      creances - dettes,
        "dso":      round(creances * 30 / ca_mois, 1),
        "dpo":      round(dettes   * 30 / achats_mois, 1),
    }


def _next_invoice_number(inv_type: str) -> str:
    """Calculates the next invoice number based on existing records."""
    df = get_table("invoices")
    prefix = "INV" if inv_type == "CUSTOMER" else "BILL"
    year = date.today().year
    
    # Filter by prefix and year
    mask = df["invoice_number"].str.startswith(f"{prefix}-{year}")
    if mask.any():
        nums = df.loc[mask, "invoice_number"].str.extract(r"-(\d+)$").astype(int)
        nxt = int(nums.max().iloc[0]) + 1
    else:
        nxt = 1
    return f"{prefix}-{year}-{nxt:03d}"


def _save_invoice(number, inv_type, counterparty, amount, currency, issue_dt, due_dt, product="", quantity=0, note="") -> None:
    """Appends a new invoice row to the Excel file and invalidates the cache."""
    wb = openpyxl.load_workbook(_EXCEL_PATH)
    ws = wb["invoices"]
    max_id = max(
        (row[0] for row in ws.iter_rows(min_row=2, values_only=True) if row[0] is not None),
        default=0,
    )
    ws.append([
        max_id + 1,
        number,
        inv_type,
        counterparty,
        int(amount),
        currency,
        str(issue_dt),
        str(due_dt),
        "PENDING",
        str(date.today()),
        product,
        quantity,
        note
    ])
    wb.save(_EXCEL_PATH)
    get_db.clear()  # Invalidate Streamlit cache so the new row is visible immediately


def _process_and_save_invoices(invoices):
    """Processes a list of invoice dictionaries and saves them to the DB."""
    saved = 0
    for inv_data in invoices:
        try:
            from datetime import datetime
            _save_invoice(
                number      = inv_data["invoice_number"],
                inv_type    = inv_data["invoice_type"],
                counterparty= inv_data["counterparty_name"],
                amount      = inv_data["amount_ttc"],
                currency    = inv_data["currency"],
                issue_dt    = datetime.strptime(inv_data["issue_date"], "%Y-%m-%d").date(),
                due_dt      = datetime.strptime(inv_data["due_date"], "%Y-%m-%d").date(),
                product     = inv_data["product"],
                quantity    = inv_data["quantity"],
                note        = inv_data["note"]
            )
            saved += 1
        except Exception:
            pass
    if saved:
        st.success(f"✅ {saved} facture(s) ajoutée(s) à la base de données.")
    else:
        st.warning("Aucune nouvelle facture à ajouter (déjà existantes).")


# ── Page ─────────────────────────────────────────────────────────────────────

def render(now: datetime) -> None:
    page_header()

    # ── KPI row ──────────────────────────────────────────────────────────────
    m = _calculate_bfr_metrics()
    style = "background:#fff;border-radius:12px;padding:16px 18px;box-shadow:0 1px 4px rgba(0,0,0,0.06);margin-bottom:12px"
    k1, k2, k3, k4, k5 = st.columns(5)
    # Carte : CRÉANCES CLIENTS
    k1.markdown(
        f'<div style="{style};border-top:3px solid {GREEN}"><div style="font-size:.72rem;color:#64748B">CRÉANCES CLIENTS</div>'
        f'<div style="font-size:1.35rem;font-weight:800;color:{GREEN}">{m["creances"]:,.0f} €</div></div>',
        unsafe_allow_html=True,
    )
    # Carte : DETTES FOURNISSEURS
    k2.markdown(
        f'<div style="{style};border-top:3px solid {RED}"><div style="font-size:.72rem;color:#64748B">DETTES FOURNISSEURS</div>'
        f'<div style="font-size:1.35rem;font-weight:800;color:{RED}">{m["dettes"]:,.0f} €</div></div>',
        unsafe_allow_html=True,
    )
    bfr_c = RED if m["bfr"] > 0 else GREEN
    # Carte : BFR NET
    k3.markdown(
        f'<div style="{style};border-top:3px solid {bfr_c}"><div style="font-size:.72rem;color:#64748B">BFR NET</div>'
        f'<div style="font-size:1.35rem;font-weight:800;color:{bfr_c}">{m["bfr"]:,.0f} €</div></div>',
        unsafe_allow_html=True,
    )
    # Carte : DSO (jours)
    k4.markdown(
        f'<div style="{style};border-top:3px solid {AMBER}"><div style="font-size:.72rem;color:#64748B">DSO (jours)</div>'
        f'<div style="font-size:1.35rem;font-weight:800;color:{AMBER}">{m["dso"]}</div></div>',
        unsafe_allow_html=True,
    )
    # Carte : DPO (jours)
    k5.markdown(
        f'<div style="{style};border-top:3px solid {BLUE}"><div style="font-size:.72rem;color:#64748B">DPO (jours)</div>'
        f'<div style="font-size:1.35rem;font-weight:800;color:{BLUE}">{m["dpo"]}</div></div>',
        unsafe_allow_html=True,
    )

    # ── Invoice creation ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### ➕ Ajouter des Factures")

    tab_manuel, tab_fichier, tab_api = st.tabs(["✏️ Saisie manuelle", "📁 Importation fichier", "🔗 API / ERP"])

    # ── Tab 1 : manual entry ──────────────────────────────────────────────────
    with tab_manuel:
        with st.form("inv_form_manual", clear_on_submit=True):
            r1c1, r1c2 = st.columns(2)
            inv_type     = r1c1.selectbox("Type *", ["CUSTOMER", "SUPPLIER"],
                                          format_func=lambda x: "Client" if x == "CUSTOMER" else "Fournisseur")
            counterparty = r1c2.text_input("Tiers (raison sociale) *")

            r2c1, r2c2, r2c3 = st.columns(3)
            amount     = r2c1.number_input("Montant TTC *", min_value=0.0, step=1000.0, format="%.2f")
            currency   = r2c2.selectbox("Devise", _CCY_OPTIONS)
            inv_number = r2c3.text_input(
                "N° Facture",
                placeholder="Auto-généré si vide",
                help="Laissez vide → numéro automatique INV-YYYY-NNN / FOU-YYYY-NNN",
            )

            r3c1, r3c2 = st.columns(2)
            issue_dt = r3c1.date_input("Date d'émission", value=date.today(), key="man_issue")
            due_dt   = r3c2.date_input("Date d'échéance",
                                       value=date.today() + timedelta(days=30), key="man_due")

            st.markdown("---")
            r4c1, r4c2 = st.columns([2, 1])
            product_val = r4c1.text_input("Produit / Service")
            quantity_val = r4c2.number_input("Quantité", min_value=0, step=1)
            note_val = st.text_area("Note libre", height=80)

            st.markdown("---")
            do_chorus = st.checkbox("🚀 Soumettre également à Chorus Pro", help="Envoie cette facture sur le portail Chorus Pro (Sandbox)")
            if do_chorus:
                sc1, sc2 = st.columns(2)
                recipient_siret = sc1.text_input("SIRET Client (Public)", placeholder="12345678900010")
                service_code = sc2.text_input("Code Service", placeholder="SERVICES_FACT")

            submitted = st.form_submit_button("💾 Enregistrer", use_container_width=True)

        if submitted:
            errs = []
            if not counterparty.strip():
                errs.append("Le champ **Tiers** est obligatoire.")
            if amount <= 0:
                errs.append("Le montant doit être supérieur à 0.")
            if due_dt < issue_dt:
                errs.append("L'échéance ne peut pas être antérieure à l'émission.")
            if do_chorus and not recipient_siret.strip():
                errs.append("Le **SIRET Client** est obligatoire pour l'envoi Chorus.")
            
            if errs:
                for e in errs:
                    st.error(e)
            else:
                final_number = inv_number.strip() or _next_invoice_number(inv_type)
                try:
                    # 1. Local Save
                    _save_invoice(final_number, inv_type, counterparty.strip(),
                                  amount, currency, issue_dt, due_dt,
                                  product=product_val.strip(),
                                  quantity=int(quantity_val),
                                  note=note_val.strip())
                    
                    # 2. Optional Chorus Submission
                    if do_chorus:
                        c_id     = st.session_state.get("chorus_id", "")
                        c_secret = st.session_state.get("chorus_secret", "")
                        c_login  = st.session_state.get("chorus_login", "")
                        c_pass   = st.session_state.get("chorus_pass", "")

                        if not c_id or not c_secret:
                            st.warning("⚠️ Identifiants Chorus manquants dans l'onglet 'API / ERP'. Facture enregistrée localement uniquement.")
                        else:
                            chorus = ChorusProAPI(c_id, c_secret, c_login, c_pass)
                            res = chorus.submit_invoice({
                                "number": final_number,
                                "amount": amount,
                                "currency": currency,
                                "date": str(issue_dt),
                                "recipient_siret": recipient_siret,
                                "service_code": service_code
                            })
                            if res["status"] == "success":
                                st.success(f"🚀 Facture **{final_number}** soumise à Chorus Pro !")
                            else:
                                st.error(f"❌ Échec de l'envoi Chorus : {res['message']}")

                    st.success(
                        f"✅ **{final_number}** enregistrée localement — "
                        f"{amount:,.0f} {currency} · échéance {due_dt.strftime('%d/%m/%Y')}"
                    )
                except Exception as exc:
                    st.error(f"Erreur lors de l'enregistrement : {exc}")

    # ── Tab 2 : file import (CSV / Excel) ─────────────────────────────────────
    with tab_fichier:
        st.markdown(
            '<p style="font-size:.82rem;color:#64748B;margin-bottom:10px">'
            "Importez un fichier CSV ou Excel contenant vos factures. "
            "Les colonnes doivent correspondre au modèle ci-dessous.</p>",
            unsafe_allow_html=True,
        )

        # Download template
        template_df = pd.DataFrame(columns=[
            "invoice_number", "invoice_type", "counterparty_name",
            "amount_ttc", "currency", "issue_date", "due_date",
        ])
        template_df.loc[0] = ["INV-2026-099", "CUSTOMER", "Exemple SA", 12000, "EUR",
                               str(date.today()), str(date.today() + timedelta(days=30))]
        template_df.loc[1] = ["FOU-2026-099", "SUPPLIER", "Fournisseur SRL", 8500, "EUR",
                               str(date.today()), str(date.today() + timedelta(days=15))]
        csv_template = template_df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇ Télécharger le modèle CSV", csv_template,
                           "modele_factures.csv", "text/csv")

        uploaded = st.file_uploader(
            "Glissez-déposez votre fichier (CSV ou Excel)",
            type=["csv", "xlsx", "xls"],
            key="inv_upload",
        )

        if uploaded is not None:
            try:
                if uploaded.name.endswith(".csv"):
                    df_up = pd.read_csv(uploaded)
                else:
                    df_up = pd.read_excel(uploaded)

                required = {"invoice_type", "counterparty_name", "amount_ttc",
                            "currency", "issue_date", "due_date"}
                missing_cols = required - set(df_up.columns.str.lower())
                if missing_cols:
                    st.error(f"Colonnes manquantes : {', '.join(missing_cols)}")
                else:
                    df_up.columns = df_up.columns.str.lower()
                    st.markdown(f"**{len(df_up)} facture(s) détectée(s)** — aperçu :")
                    st.dataframe(df_up.head(10), use_container_width=True, hide_index=True)

                    if st.button("✅ Importer toutes les factures", key="btn_import_file"):
                        saved, errors_imp = 0, []
                        for _, row in df_up.iterrows():
                            try:
                                num = str(row.get("invoice_number", "")).strip() or \
                                      _next_invoice_number(str(row["invoice_type"]))
                                _save_invoice(
                                    number      = num,
                                    inv_type    = str(row["invoice_type"]).upper(),
                                    counterparty= str(row["counterparty_name"]),
                                    amount      = float(row["amount_ttc"]),
                                    currency    = str(row["currency"]).upper(),
                                    issue_dt    = pd.to_datetime(row["issue_date"]).date(),
                                    due_dt      = pd.to_datetime(row["due_date"]).date(),
                                    product     = str(row.get("product", "")),
                                    quantity    = int(row.get("quantity", 0)),
                                    note        = str(row.get("note", "")),
                                )
                                saved += 1
                            except Exception as exc:
                                errors_imp.append(f"Ligne {_ + 2} : {exc}")
                        if saved:
                            st.success(f"✅ {saved} facture(s) importée(s) avec succès.")
                        for e in errors_imp:
                            st.warning(e)
            except Exception as exc:
                st.error(f"Impossible de lire le fichier : {exc}")

    # ── Tab 3 : API / ERP ─────────────────────────────────────────────────────
    with tab_api:
        # Load PISTE credentials from secrets (pre-fill if available)
        _secrets = st.secrets.get("chorus", {}) if hasattr(st, "secrets") else {}
        _default_id     = _secrets.get("client_id", "")
        _default_secret = _secrets.get("client_secret", "")
        _default_mode   = _secrets.get("mode", "sandbox")

        st.markdown(
            '<p style="font-size:.82rem;color:#64748B;margin-bottom:14px">'
            "Synchronisez les factures depuis <b>Chorus Pro</b> via l'API PISTE. "
            "Vos identifiants sandbox sont pré-configurés dans <code>secrets.toml</code>.</p>",
            unsafe_allow_html=True,
        )

        api_src = st.radio(
            "Source",
            ["Chorus Pro (PISTE)", "API personnalisée"],
            horizontal=True,
            key="api_src",
        )

        if api_src == "Chorus Pro (PISTE)":
            # Status banner
            st.markdown(
                '<div style="background:#EFF6FF;border-left:4px solid #1A56DB;'
                'border-radius:6px;padding:10px 14px;font-size:.82rem;margin-bottom:12px">'
                '🔐 <b>Application PISTE</b> : APP_SANDBOX_youssefelgarne906@gmail.com &nbsp;|&nbsp; '
                '<b>Environnement</b> : SANDBOX &nbsp;|&nbsp; '
                '<b>API souscrite</b> : Factures v1.0.0</div>',
                unsafe_allow_html=True,
            )

            # ── Credentials PISTE ──
            st.markdown("**Identifiants OAuth2 PISTE**")
            c1, c2 = st.columns(2)
            c_id     = c1.text_input("Client ID", value=_default_id, key="chorus_id")
            c_secret = c2.text_input("Client Secret", value=_default_secret,
                                     type="password", key="chorus_secret")

            # ── Compte Technique Chorus (optionnel pour rechercher/recipiendaire) ──
            with st.expander("Compte Technique Chorus Pro (optionnel)", expanded=False):
                st.caption("Nécessaire uniquement pour les API qui requièrent le header `cpro-account`.")
                c3, c4 = st.columns(2)
                cp_login = c3.text_input("Login technique", placeholder="login_tech", key="chorus_login")
                cp_pass  = c4.text_input("Mot de passe technique", type="password", key="chorus_pass")

            siret = st.text_input(
                "SIRET Destinataire",
                placeholder="12345678900010",
                key="chorus_siret",
                help="SIRET de votre structure pour récupérer les factures reçues.",
            )

            # ── Connection status display ──
            if "chorus_conn_status" in st.session_state:
                s = st.session_state["chorus_conn_status"]
                if s["ok"]:
                    st.success(f"✅ {s['message']}")
                else:
                    st.error(f"❌ {s['message']}")

            # ── Action buttons ──
            b1, b2, b3 = st.columns(3)
            btn_test  = b1.button("🔌 Tester la connexion", use_container_width=True)
            btn_sync  = b2.button("🔄 Synchroniser les factures", use_container_width=True)
            btn_demo  = b3.button("🧪 Mode Démo", use_container_width=True,
                                  help="Importe des factures fictives sans appel API")

            if btn_test:
                if not c_id or not c_secret:
                    st.warning("Renseignez le Client ID et le Client Secret.")
                else:
                    with st.spinner("Test de connexion PISTE..."):
                        chorus = ChorusProAPI(c_id, c_secret,
                                             cp_login if cp_login else "",
                                             cp_pass  if cp_pass  else "",
                                             mode=_default_mode)
                        result = chorus.test_connection()
                    st.session_state["chorus_conn_status"] = result
                    st.rerun()

            if btn_sync:
                if not c_id or not c_secret:
                    st.warning("Renseignez au minimum le Client ID et le Client Secret.")
                elif not siret.strip():
                    st.warning("Le SIRET Destinataire est requis pour la synchronisation.")
                else:
                    chorus = ChorusProAPI(c_id, c_secret,
                                         cp_login if cp_login else "",
                                         cp_pass  if cp_pass  else "",
                                         mode=_default_mode)
                    with st.spinner("Connexion à Chorus Pro Sandbox..."):
                        token = chorus.get_token()
                    if token:
                        st.session_state["chorus_conn_status"] = {"ok": True, "message": "Token PISTE obtenu."}
                        with st.spinner("Récupération des factures..."):
                            invoices = chorus.fetch_received_invoices(siret.strip())
                        if not invoices:
                            st.info("Aucune facture trouvée dans le Sandbox. "
                                    "Utilisez **Mode Démo** pour tester l'affichage.")
                        else:
                            _process_and_save_invoices(invoices)
                    else:
                        st.session_state["chorus_conn_status"] = {"ok": False, "message": "Échec d'authentification PISTE."}
                        st.rerun()

            if btn_demo:
                chorus = ChorusProAPI("demo", "demo")
                invoices = chorus.fetch_mock_data()
                _process_and_save_invoices(invoices)

        elif api_src == "API personnalisée":
            api_url = st.text_input("URL endpoint (GET)",
                                    placeholder="https://erp.exemple.com/api/invoices",
                                    key="custom_api_url")
            api_bearer = st.text_input("API Key / Bearer Token", type="password",
                                       placeholder="sk-…", key="custom_api_key")
            if st.button("📥 Récupérer les factures", key="btn_custom_api"):
                if not api_url.strip():
                    st.warning("Renseignez l'URL de l'endpoint.")
                else:
                    try:
                        hdrs = {"Accept": "application/json"}
                        if api_bearer.strip():
                            hdrs["Authorization"] = f"Bearer {api_bearer.strip()}"
                        import requests as _req
                        resp = _req.get(api_url.strip(), headers=hdrs, timeout=15)
                        resp.raise_for_status()
                        records = resp.json()
                        if isinstance(records, dict):
                            records = records.get("data", records.get("invoices", [records]))
                        st.success(f"{len(records)} enregistrement(s) reçu(s).")
                        st.json(records[:3])
                    except Exception as exc:
                        st.error(f"Erreur API : {exc}")

        st.markdown("**Ou collez une réponse JSON** (tableau de factures) :")
        json_raw = st.text_area("JSON", height=140, placeholder='[{"invoice_type":"CUSTOMER", ...}]',
                                key="api_json")

        if st.button("🔄 Importer depuis JSON", key="btn_import_json"):
            if not json_raw.strip():
                st.warning("Collez un JSON valide.")
            else:
                try:
                    import json
                    records = json.loads(json_raw)
                    if isinstance(records, dict):
                        records = [records]
                    saved, errors_api = 0, []
                    for i, rec in enumerate(records):
                        try:
                            num = str(rec.get("invoice_number", "")).strip() or \
                                  _next_invoice_number(str(rec.get("invoice_type", "CUSTOMER")))
                            _save_invoice(
                                number      = num,
                                inv_type    = str(rec.get("invoice_type", "CUSTOMER")).upper(),
                                counterparty= str(rec.get("counterparty_name", rec.get("tiers", ""))),
                                amount      = float(rec.get("amount_ttc", rec.get("amount", 0))),
                                currency    = str(rec.get("currency", "EUR")).upper(),
                                issue_dt    = pd.to_datetime(rec.get("issue_date", str(date.today()))).date(),
                                due_dt      = pd.to_datetime(rec.get("due_date", str(date.today()))).date(),
                                product     = str(rec.get("product", "")),
                                quantity    = int(rec.get("quantity", 0)),
                                note        = str(rec.get("note", "")),
                            )
                            saved += 1
                        except Exception as exc:
                            errors_api.append(f"Enregistrement {i + 1} : {exc}")
                    if saved:
                        st.success(f"✅ {saved} facture(s) importée(s) depuis le JSON.")
                    for e in errors_api:
                        st.warning(e)
                except Exception as exc:
                    st.error(f"JSON invalide : {exc}")

    # ── Invoice schedule ──────────────────────────────────────────────────────
    st.markdown("---")
    # Carte : Échéancier des Factures en Attente
    st.markdown("#### 🗓️ Échéancier des Factures en Attente")

    inv = get_table("invoices")
    if not inv.empty:
        df = inv[inv["status"] == "PENDING"].sort_values("due_date").copy()
        
        # Ensure new columns exist in the dataframe to avoid KeyError
        for col in ["product", "quantity", "note"]:
            if col not in df.columns:
                df[col] = "" if col != "quantity" else 0
        
        df = df[["invoice_number", "invoice_type", "counterparty_name",
                 "product", "quantity", "due_date", "amount_ttc", "currency", "note"]]
        df = df.rename(columns={
            "invoice_number":   "N° Facture",
            "invoice_type":     "Type",
            "counterparty_name":"Tiers",
            "product":          "Produit",
            "quantity":         "Qté",
            "due_date":         "Échéance",
            "amount_ttc":       "Montant TTC",
            "currency":         "Devise",
            "note":             "Note",
        })
        df["Type"] = df["Type"].map({"CUSTOMER": "Client", "SUPPLIER": "Fournisseur"})

        def _color_due(val):
            try:
                due = datetime.strptime(str(val), "%Y-%m-%d").date()
                if due < date.today():
                    return "color:#E02424;font-weight:700"
                if due <= date.today() + timedelta(days=7):
                    return "color:#FF8000;font-weight:600"
            except Exception:
                pass
            return ""

        st.dataframe(
            df.style.map(_color_due, subset=["Échéance"]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Aucune facture en attente.")

    # ── Cash flow forecast chart ──────────────────────────────────────────────
    st.markdown("---")
    # Graphe : Cash Flow Prévisionnel — Mai 2026
    st.markdown("#### 📈 Cash Flow Prévisionnel — Mai 2026")

    fcasts = get_table("forecasts")
    if not fcasts.empty:
        df_fc = (
            fcasts.groupby(["forecast_date", "type"])["amount"]
            .sum()
            .reset_index()
            .sort_values("forecast_date")
            .rename(columns={"amount": "Montant"})
        )
        # Keep only May 2026 for clarity
        df_fc["forecast_date"] = pd.to_datetime(df_fc["forecast_date"])
        df_may = df_fc[df_fc["forecast_date"].dt.strftime("%Y-%m") == "2026-05"]

        if not df_may.empty:
            fig = px.bar(
                df_may,
                x="forecast_date",
                y="Montant",
                color="type",
                barmode="group",
                color_discrete_map={"IN": GREEN, "OUT": RED},
                labels={"forecast_date": "Date", "type": "Flux"},
            )
            apply_chart_theme(fig, "Flux prévisionnels Mai 2026")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Aucune prévision disponible.")
