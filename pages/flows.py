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
    """Generates next sequential invoice number (INV-YYYY-NNN or FOU-YYYY-NNN)."""
    df = get_table("invoices")
    prefix = "INV" if inv_type == "CUSTOMER" else "FOU"
    year   = datetime.now().year
    if df.empty:
        return f"{prefix}-{year}-001"
    existing = df["invoice_number"].astype(str)
    same_prefix = existing[existing.str.startswith(f"{prefix}-{year}-")]
    if same_prefix.empty:
        return f"{prefix}-{year}-001"
    nums = same_prefix.str.extract(r"-(\d+)$")[0].dropna().astype(int)
    return f"{prefix}-{year}-{(nums.max() + 1):03d}"


def _save_invoice(number, inv_type, counterparty, amount, currency, issue_dt, due_dt) -> None:
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
    k1.markdown(
        f'<div style="{style};border-top:3px solid {GREEN}"><div style="font-size:.72rem;color:#64748B">CRÉANCES CLIENTS</div>'
        f'<div style="font-size:1.35rem;font-weight:800;color:{GREEN}">{m["creances"]:,.0f} €</div></div>',
        unsafe_allow_html=True,
    )
    k2.markdown(
        f'<div style="{style};border-top:3px solid {RED}"><div style="font-size:.72rem;color:#64748B">DETTES FOURNISSEURS</div>'
        f'<div style="font-size:1.35rem;font-weight:800;color:{RED}">{m["dettes"]:,.0f} €</div></div>',
        unsafe_allow_html=True,
    )
    bfr_c = RED if m["bfr"] > 0 else GREEN
    k3.markdown(
        f'<div style="{style};border-top:3px solid {bfr_c}"><div style="font-size:.72rem;color:#64748B">BFR NET</div>'
        f'<div style="font-size:1.35rem;font-weight:800;color:{bfr_c}">{m["bfr"]:,.0f} €</div></div>',
        unsafe_allow_html=True,
    )
    k4.markdown(
        f'<div style="{style};border-top:3px solid {AMBER}"><div style="font-size:.72rem;color:#64748B">DSO (jours)</div>'
        f'<div style="font-size:1.35rem;font-weight:800;color:{AMBER}">{m["dso"]}</div></div>',
        unsafe_allow_html=True,
    )
    k5.markdown(
        f'<div style="{style};border-top:3px solid {BLUE}"><div style="font-size:.72rem;color:#64748B">DPO (jours)</div>'
        f'<div style="font-size:1.35rem;font-weight:800;color:{BLUE}">{m["dpo"]}</div></div>',
        unsafe_allow_html=True,
    )

    # ── Invoice creation ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### ➕ Nouvelle Facture")

    with st.expander("Saisir une facture manuellement", expanded=False):
        with st.form("inv_form", clear_on_submit=True):
            r1c1, r1c2 = st.columns(2)
            inv_type    = r1c1.selectbox("Type", ["CUSTOMER", "SUPPLIER"],
                                         format_func=lambda x: "Client" if x == "CUSTOMER" else "Fournisseur")
            counterparty = r1c2.text_input("Tiers (raison sociale) *")

            r2c1, r2c2, r2c3 = st.columns(3)
            amount   = r2c1.number_input("Montant TTC *", min_value=0.0, step=1000.0, format="%.2f")
            currency = r2c2.selectbox("Devise", _CCY_OPTIONS)
            inv_number = r2c3.text_input(
                "N° Facture",
                placeholder="Auto-généré si vide",
                help="Laissez vide pour un numéro automatique (INV-YYYY-NNN ou FOU-YYYY-NNN)",
            )

            r3c1, r3c2 = st.columns(2)
            issue_dt = r3c1.date_input("Date d'émission", value=date.today())
            due_dt   = r3c2.date_input(
                "Date d'échéance", value=date.today() + timedelta(days=30)
            )

            submitted = st.form_submit_button("💾 Enregistrer la facture", use_container_width=True)

        if submitted:
            errors = []
            if not counterparty.strip():
                errors.append("Le champ **Tiers** est obligatoire.")
            if amount <= 0:
                errors.append("Le montant doit être supérieur à 0.")
            if due_dt < issue_dt:
                errors.append("La date d'échéance ne peut pas être antérieure à la date d'émission.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                final_number = inv_number.strip() or _next_invoice_number(inv_type)
                try:
                    _save_invoice(final_number, inv_type, counterparty.strip(),
                                  amount, currency, issue_dt, due_dt)
                    st.success(
                        f"✅ Facture **{final_number}** enregistrée — "
                        f"{amount:,.0f} {currency} · échéance {due_dt.strftime('%d/%m/%Y')}"
                    )
                except Exception as exc:
                    st.error(f"Erreur lors de l'enregistrement : {exc}")

    # ── Invoice schedule ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🗓️ Échéancier des Factures en Attente")

    inv = get_table("invoices")
    if not inv.empty:
        df = inv[inv["status"] == "PENDING"].sort_values("due_date").copy()
        df = df[["invoice_number", "invoice_type", "counterparty_name",
                 "due_date", "amount_ttc", "currency"]]
        df = df.rename(columns={
            "invoice_number":   "N° Facture",
            "invoice_type":     "Type",
            "counterparty_name":"Tiers",
            "due_date":         "Échéance",
            "amount_ttc":       "Montant TTC",
            "currency":         "Devise",
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

        # Cumulative net view (all dates)
        df_pivot = df_fc.pivot_table(
            index="forecast_date", columns="type", values="Montant", aggfunc="sum", fill_value=0
        ).reset_index()
        df_pivot["Net"] = df_pivot.get("IN", 0) - df_pivot.get("OUT", 0)
        df_pivot["Cumulé"] = df_pivot["Net"].cumsum()

        fig2 = px.area(
            df_pivot,
            x="forecast_date",
            y="Cumulé",
            color_discrete_sequence=[BLUE],
            labels={"forecast_date": "Date", "Cumulé": "Position nette cumulée (€)"},
        )
        fig2.add_hline(y=0, line_color="#E02424", line_dash="dash", line_width=1)
        apply_chart_theme(fig2, "Position nette cumulée")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Aucune prévision disponible.")
