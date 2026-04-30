# =============================================================================
# utils/config.py — Palette de couleurs, constantes financières et helpers globaux
#
# Ce module centralise tout ce qui est partagé entre les pages :
#   - Palette de couleurs utilisée dans les graphiques et les cartes KPI
#   - Taux financiers de fallback (si aucun taux négocié n'existe en base)
#   - Initialisation des paramètres de session Streamlit (taux, FX, config)
#   - Fonctions utilitaires : cfg_rate(), fx_to_eur(), fmt(), apply_chart_theme()
#
# Importé par : toutes les pages, components/navbar.py, utils/pooling.py
# =============================================================================

import streamlit as st  # type: ignore
import pandas as pd      # type: ignore
from db.database import get_table  # Pour charger les taux négociés depuis Excel

# ── Palette de couleurs du dashboard ─────────────────────────────────────────
BLUE       = "#1A56DB"
BLUE_LIGHT = "#3B82F6"
DARK_BLUE  = "#1E3A5F"
GREEN      = "#057A55"
RED        = "#E02424"
AMBER      = "#FF8000"
TEAL       = "#0D9488"

# ── Taux financiers de fallback ───────────────────────────────────────────────
OD_RATE  = 0.06    # taux de découvert par défaut
INV_RATE = 0.035   # taux de placement par défaut
DEP_RATE = 0.005   # taux de dépôt courant par défaut

def _init_config() -> None:
    """
    Initialise les paramètres globaux dans st.session_state au premier chargement.
    """
    if "cfg_init" not in st.session_state:
        # Charge les taux négociés depuis Excel (dernière date disponible)
        df_cond = get_table("daily_bank_conditions")
        df_banks = get_table("banks")
        
        if not df_cond.empty and not df_banks.empty:
            latest_date = df_cond["date"].max()
            c = df_cond[df_cond["date"] == latest_date].merge(df_banks, on="bank_id")
            
            # Émulation de la requête UNION ALL
            od = c[["bank_id", "bank_name", "od_rate"]].rename(columns={"od_rate": "rate_value"})
            od["rate_type"] = "OVERDRAFT"
            od["currency"] = "EUR"
            
            inv = c[["bank_id", "bank_name", "invest_rate"]].rename(columns={"invest_rate": "rate_value"})
            inv["rate_type"] = "INVESTMENT"
            inv["currency"] = "EUR"
            
            df_r = pd.concat([od, inv]).sort_values(["bank_name", "rate_type"])
            st.session_state["rates_df"] = df_r
        else:
            st.session_state["rates_df"] = pd.DataFrame()

        st.session_state["od_rate_fb"]      = OD_RATE
        st.session_state["inv_rate_fb"]     = INV_RATE
        st.session_state["dep_rate_fb"]     = DEP_RATE
        st.session_state["tax_rate"]        = 0.30
        st.session_state["fx_eur_sek"]      = 11.50
        st.session_state["fx_eur_pln"]      = 4.15
        st.session_state["fx_eur_usd"]      = 1.09
        st.session_state["pool_fee_annual"] = 0.05
        
        _load_daily_fx_rates()
        st.session_state["cfg_init"]        = True


def _load_daily_fx_rates() -> None:
    """
    Charge les taux de change du jour depuis Excel et met à jour session_state.
    """
    df_cond = get_table("daily_bank_conditions")
    if not df_cond.empty:
        latest_date = df_cond["date"].max()
        df_latest = df_cond[df_cond["date"] == latest_date]
        
        st.session_state["fx_eur_sek"] = float(df_latest["fx_eur_sek"].mean())
        st.session_state["fx_eur_pln"] = float(df_latest["fx_eur_pln"].mean())
        st.session_state["fx_eur_usd"] = float(df_latest["fx_eur_usd"].mean())


def cfg_rate(bank_id: int, rate_type: str, currency: str) -> float:
    """
    Retourne le taux négocié pour une banque, un type de taux et une devise.

    Logique de recherche (ordre de priorité décroissante) :
      1. Taux exact : banque + type + devise (ex: BNP, OVERDRAFT, EUR)
      2. Taux par banque + type sans distinction de devise (fallback devise)
      3. Taux global de session (od_rate_fb ou inv_rate_fb)

    Utilisé dans les simulateurs pour calculer les coûts de découvert
    et les rendements de placement avec les taux réellement négociés.
    """
    df = st.session_state["rates_df"]

    # Recherche exacte : banque + type de taux + devise
    mask = (df["bank_id"] == bank_id) & (df["rate_type"] == rate_type) & (df["currency"] == currency)
    rows = df[mask]

    if rows.empty:
        # Fallback : même banque + type, quelle que soit la devise
        mask2 = (df["bank_id"] == bank_id) & (df["rate_type"] == rate_type)
        rows  = df[mask2]

    if rows.empty:
        # Dernier recours : taux global de la session
        return st.session_state["od_rate_fb"] if rate_type == "OVERDRAFT" else st.session_state["inv_rate_fb"]

    return float(rows["rate_value"].iloc[0])


def fx_to_eur(amount: float, currency: str) -> float:
    """
    Convertit un montant dans une devise en EUR en utilisant les taux de session.

    Les taux EUR/devise sont lus depuis st.session_state (initialisés dans
    _init_config() et modifiables dans la page Configuration).
    Les devises non reconnues sont retournées sans conversion (hypothèse : EUR).
    """
    if currency == "EUR": return amount
    if currency == "SEK": return amount / st.session_state["fx_eur_sek"]
    if currency == "PLN": return amount / st.session_state["fx_eur_pln"]
    if currency == "USD": return amount / st.session_state["fx_eur_usd"]
    return amount  # Devise inconnue : on retourne la valeur brute


def fmt(value, suffix: str = "€") -> str:
    """
    Formate un nombre en chaîne lisible avec séparateur de milliers et suffixe.

    Exemples : fmt(1250000) → "1,250,000 €"
               fmt(None)   → "N/A €"
               fmt(3.5, "%") → "4 %" (arrondi à 0 décimale)
    """
    if value is None:
        return f"N/A {suffix}"
    return f"{value:,.0f} {suffix}"


def apply_chart_theme(fig, title: str = ""):
    """
    Applique le thème visuel uniforme du dashboard à un graphique Plotly.

    Garantit la cohérence visuelle entre tous les graphiques :
      - Police Inter (même que le CSS global)
      - Fond blanc, pas de grille sur l'axe X, grille légère sur Y
      - Marges resserrées pour maximiser l'espace dans les colonnes Streamlit
      - Titre aligné à gauche avec marge adaptée (36px si titre, 6px sinon)

    Doit être appelé APRÈS avoir configuré les traces du graphique,
    car update_layout() fusionne avec la configuration existante.
    """
    fig.update_layout(
        title_text=title,
        title_x=0,  # Titre aligné à gauche (pas centré)
        margin=dict(t=36 if title else 6, b=6, l=6, r=6),  # Marges compactes
        font=dict(family="Inter, sans-serif", size=12, color="#111827"),
        plot_bgcolor="#FFFFFF",   # Fond du graphique blanc
        paper_bgcolor="#FFFFFF",  # Fond du canevas blanc
    )
    fig.update_xaxes(showgrid=False, linecolor="#E5E7EB")          # Pas de grille verticale
    fig.update_yaxes(gridcolor="#F3F4F6", linecolor="#E5E7EB")     # Grille horizontale légère
    return fig
