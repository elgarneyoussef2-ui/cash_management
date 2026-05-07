import streamlit as st  # type: ignore
import pandas as pd  # type: ignore
import plotly.express as px  # type: ignore
from datetime import datetime, date, timedelta

import openpyxl  # type: ignore

from db.database import get_db, get_table
from utils.config import BLUE, GREEN, RED, AMBER, apply_chart_theme
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

            submitted = st.form_submit_button("💾 Enregistrer", use_container_width=True)

        if submitted:
            errs = []
            if not counterparty.strip():
                errs.append("Le champ **Tiers** est obligatoire.")
            if amount <= 0:
                errs.append("Le montant doit être supérieur à 0.")
            if due_dt < issue_dt:
                errs.append("L'échéance ne peut pas être antérieure à l'émission.")
            
            if errs:
                for e in errs:
                    st.error(e)
            else:
                final_number = inv_number.strip() or _next_invoice_number(inv_type)
                try:
                    # Local Save
                    _save_invoice(final_number, inv_type, counterparty.strip(),
                                  amount, currency, issue_dt, due_dt,
                                  product=product_val.strip(),
                                  quantity=int(quantity_val),
                                  note=note_val.strip())
                    
                    st.success(
                        f"✅ **{final_number}** enregistrée — "
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

    # ── Tab 3 : Chorus Pro ────────────────────────────────────────────────────
    with tab_api:
        import requests as _req
        import base64, json as _json

        st.markdown(
            '<p style="font-size:.82rem;color:#64748B;margin-bottom:4px">'
            "Connectez-vous à <b>Chorus Pro</b> via la plateforme PISTE pour synchroniser "
            "automatiquement vos factures fournisseurs.</p>",
            unsafe_allow_html=True,
        )

        with st.expander("ℹ️ Comment obtenir mes identifiants Chorus Pro ?", expanded=False):
            st.markdown(
                """
**Compte technique Chorus Pro** (`chorus-pro.gouv.fr`)

1. Connectez-vous au portail Chorus Pro
2. Depuis l'accueil : **Raccordement** → **Compte technique** → *Création d'un compte technique*
3. Sélectionnez votre structure via le champ **"Choisir la structure"**
4. Cliquez sur **Soumettre** — le compte est créé sous 30 minutes
5. Utilisez le **login** et **mot de passe** reçus dans le formulaire ci-dessous

> Pour l'environnement de qualification (sandbox), utilisez `qualif.chorus-pro.gouv.fr`
                """
            )

        st.markdown("#### 🔐 Connexion Chorus Pro")

        piste_cfg    = st.secrets.get("piste", {})
        piste_id     = piste_cfg.get("client_id", "")
        piste_secret = piste_cfg.get("client_secret", "")
        is_sandbox   = piste_cfg.get("mode", "sandbox") != "production"

        col1, col2 = st.columns(2)
        with col1:
            chorus_login = st.text_input("Login compte technique Chorus Pro",
                                         key="chorus_login",
                                         placeholder="ex : CPT_MON_COMPTE")
        with col2:
            chorus_pwd = st.text_input("Mot de passe compte technique",
                                       key="chorus_pwd", type="password")

        st.markdown("#### 📅 Période de recherche")
        dc1, dc2 = st.columns(2)
        date_du = dc1.date_input("Du",  value=date.today() - timedelta(days=90), key="chorus_date_du")
        date_au = dc2.date_input("Au",  value=date.today(),                      key="chorus_date_au")

        if st.button("🔄 Synchroniser les factures Chorus Pro", key="btn_chorus_sync",
                     use_container_width=True):
            missing = []
            if not piste_id.strip():     missing.append("Client ID PISTE")
            if not piste_secret.strip(): missing.append("Client Secret PISTE")
            if not chorus_login.strip(): missing.append("Login compte technique")
            if not chorus_pwd.strip():   missing.append("Mot de passe compte technique")
            if missing:
                st.warning(f"Champs obligatoires manquants : {', '.join(missing)}")
            else:
                # ── Étape 1 : token PISTE ──────────────────────────────────────
                oauth_url = (
                    "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"
                    if is_sandbox else
                    "https://oauth.piste.gouv.fr/api/oauth/token"
                )
                with st.spinner("Connexion à PISTE en cours…"):
                    try:
                        tok_resp = _req.post(
                            oauth_url,
                            data={
                                "grant_type":    "client_credentials",
                                "client_id":     piste_id.strip(),
                                "client_secret": piste_secret.strip(),
                            },
                            headers={"Content-Type": "application/x-www-form-urlencoded"},
                            timeout=15,
                        )
                        tok_resp.raise_for_status()
                        token = tok_resp.json()["access_token"]
                        st.success("Token PISTE obtenu ✅")
                    except Exception as exc:
                        st.error(f"Échec de l'authentification PISTE : {exc}")
                        st.stop()

                # ── Étape 2 : appel Chorus Pro ────────────────────────────────
                api_base = (
                    "https://sandbox-api.piste.gouv.fr/cpro/factures/v1"
                    if is_sandbox else
                    "https://api.piste.gouv.fr/cpro/factures/v1"
                )
                cpro_account = base64.b64encode(
                    f"{chorus_login.strip()}:{chorus_pwd}".encode()
                ).decode()

                body = {
                    "rechercheFactureParFournisseur": {
                        "pageResultatDemandee": 1,
                        "nbResultatsParPage":   50,
                    },
                    "periodeDateDepotDu": str(date_du),
                    "periodeDateDepotAu": str(date_au),
                }

                with st.spinner("Récupération des factures Chorus Pro…"):
                    try:
                        api_resp = _req.post(
                            f"{api_base}/rechercher/fournisseur",
                            headers={
                                "Authorization": f"Bearer {token}",
                                "Content-Type":  "application/json",
                                "cpro-account":  cpro_account,
                            },
                            json=body,
                            timeout=30,
                        )
                        api_resp.raise_for_status()
                        data = api_resp.json()
                    except Exception as exc:
                        st.error(f"Erreur Chorus Pro ({api_resp.status_code if 'api_resp' in dir() else '?'}) : {exc}")
                        if "api_resp" in dir():
                            st.code(api_resp.text, language="json")
                        st.stop()

                factures_raw = data.get("listeFactures", [])
                if not factures_raw:
                    st.info("Aucune facture trouvée pour la période sélectionnée.")
                else:
                    saved, errors_c = 0, []
                    for fac in factures_raw:
                        try:
                            _save_invoice(
                                number       = str(fac.get("numeroFacture", "")),
                                inv_type     = "SUPPLIER",
                                counterparty = str(fac.get("designationFournisseur",
                                                           fac.get("siretFournisseur", "Chorus Pro"))),
                                amount       = float(fac.get("montantTTC", 0)),
                                currency     = "EUR",
                                issue_dt     = pd.to_datetime(
                                    fac.get("dateDepot", str(date.today()))
                                ).date(),
                                due_dt       = pd.to_datetime(
                                    fac.get("dateEcheancePaiement",
                                            fac.get("dateDepot", str(date.today())))
                                ).date(),
                                note         = f"Chorus Pro · statut : {fac.get('statutFacture', '')}",
                            )
                            saved += 1
                        except Exception as exc:
                            errors_c.append(str(exc))
                    if saved:
                        st.success(f"✅ {saved} facture(s) importée(s) depuis Chorus Pro.")
                    for e in errors_c:
                        st.warning(e)

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
