import streamlit as st  # type: ignore
import plotly.express as px  # type: ignore
from datetime import datetime

from db.database import get_table
from utils.config import RED, GREEN
from components.navbar import page_header

def render(now: datetime) -> None:
    page_header()
    
    acc = get_table("accounts")
    banks = get_table("banks")
    bal = get_table("daily_account_balances")
    cond = get_table("daily_bank_conditions")
    
    if acc.empty or banks.empty or bal.empty:
        st.info("Données insuffisantes.")
        return

    # Préparation des données via Pandas
    latest_idx = bal.groupby("account_id")["date"].idxmax()
    df_bal = bal.loc[latest_idx]
    
    latest_cond_idx = cond.groupby("bank_id")["date"].idxmax()
    df_cond = cond.loc[latest_cond_idx][["bank_id", "od_ceiling"]]
    
    df_accounts = acc.merge(banks, on="bank_id")\
                     .merge(df_bal, on="account_id")\
                     .merge(df_cond, on="bank_id", how="left")
    
    df_accounts = df_accounts[["account_number", "bank_name", "account_type", "currency", "book_balance", "balance_eur", "od_ceiling"]]
    
    # Carte : Positions & Soldes par Compte
    st.markdown("#### Positions & Soldes par Compte")
    COL_FR = {
        "account_number": "N° Compte", "bank_name": "Banque", "account_type": "Type",
        "currency": "Devise", "book_balance": "Solde Devise", "balance_eur": "Solde EUR",
        "od_ceiling": "Plafond Banque",
    }
    def _red_neg(val): 
        return "color: #E02424; font-weight: 600" if isinstance(val, (int, float)) and val < 0 else ""
    
    if not df_accounts.empty:
        st.dataframe(
            df_accounts.rename(columns=COL_FR)
            .style.map(_red_neg, subset=["Solde EUR", "Solde Devise"])
            .format({"Solde EUR": "{:,.0f} €", "Solde Devise": "{:,.0f}"}), # type: ignore
            use_container_width=True, 
            hide_index=True
        )
    else:
        st.info("Aucun compte actif trouvé.")
    st.download_button("⬇ Exporter CSV", df_accounts.to_csv(index=False).encode("utf-8"), "positions.csv", "text/csv")

    st.markdown("---")
    # Graphe : Positions Détaillées par Banque & Compte
    st.markdown("#### Positions Détaillées par Banque & Compte")
    df_plot = df_accounts.copy()
    df_plot["Label"] = df_plot["bank_name"].astype(str) + "<br><sup>" + df_plot["account_number"].astype(str) + "</sup>"
    fig = px.bar(df_plot, x="balance_eur", y="Label", color="balance_eur", orientation='h',
                 color_continuous_scale=[[0, RED], [0.5, "#E5E7EB"], [1, GREEN]],
                 color_continuous_midpoint=0, text="balance_eur")
    fig.update_traces(texttemplate="%{text:,.0f} €", textposition="outside")
    fig.update_layout(showlegend=False, coloraxis_showscale=False, height=max(400, len(df_plot) * 45))
    st.plotly_chart(fig, use_container_width=True)
