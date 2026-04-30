import streamlit as st  # type: ignore
import pandas as pd  # type: ignore
import plotly.express as px  # type: ignore
import plotly.graph_objects as go
from datetime import datetime, timedelta

from db.database import get_table
from utils.config import BLUE, GREEN, RED, AMBER, TEAL, DARK_BLUE, apply_chart_theme
from components.navbar import page_header

def _get_ticker_data():
    df_cond = get_table("daily_bank_conditions")
    if df_cond.empty: return pd.DataFrame(), pd.DataFrame()
    
    # FX Ticker : Moyenne de la dernière date disponible
    latest_date = df_cond["date"].max()
    df_fx = df_cond[df_cond["date"] == latest_date][["fx_eur_sek", "fx_eur_pln", "fx_eur_usd"]]
    
    # Rates Ticker
    df_rates = get_table("v_bank_cash_rates")
    return df_fx, df_rates

def _calculate_liquidity_metrics():
    acc = get_table("accounts")
    bal = get_table("daily_account_balances")
    
    if acc.empty or bal.empty: return {}

    # Filtrer comptes actifs
    acc_active = acc[acc["is_active"] == 1]
    
    # Récupérer les dernières positions
    latest_idx = bal.groupby("account_id")["date"].idxmax()
    df_latest = bal.loc[latest_idx]
    
    # Jointure pour avoir la devise
    df = acc_active.merge(df_latest, on="account_id", how="inner")
    
    # Calcul previous_balance_eur pour le delta
    prev_balances = []
    for acc_id in df["account_id"]:
        acc_bal = bal[bal["account_id"] == acc_id].sort_values("date", ascending=False)
        prev_balances.append(acc_bal.iloc[1]["balance_eur"] if len(acc_bal) > 1 else 0)
    df["previous_balance_eur"] = prev_balances

    total = float(df["balance_eur"].sum())
    prev  = float(df["previous_balance_eur"].sum())
    
    # Calcul détaillé par devise
    by_currency = df.groupby("currency").agg({
        "book_balance": "sum",
        "balance_eur": "sum"
    }).to_dict("index")

    # On sépare le surplus du risque pour une vision "brute" (Gross) du risque
    # Surplus par devise (uniquement les soldes positifs)
    surplus_df = df[df["balance_eur"] > 0]
    surplus_total = float(surplus_df["balance_eur"].sum())
    surplus_by_curr = surplus_df.groupby("currency").agg({
        "book_balance": "sum",
        "balance_eur": "sum"
    }).to_dict("index")

    # Risque (Overdraft) par devise (uniquement les soldes négatifs)
    overdraft_df = df[df["balance_eur"] < 0]
    overdraft_total = abs(float(overdraft_df["balance_eur"].sum()))
    overdraft_by_curr = overdraft_df.groupby("currency").agg({
        "book_balance": "sum",
        "balance_eur": "sum"
    }).to_dict("index")
    
    return {
        "total": total,
        "delta_abs": total - prev,
        "delta_pct": ((total - prev) / prev * 100) if prev != 0 else 0,
        "by_currency": by_currency,
        "surplus": surplus_total,
        "surplus_by_curr": surplus_by_curr,
        "overdraft": overdraft_total,
        "overdraft_by_curr": overdraft_by_curr,
        "df_raw": df
    }

def _render_pbar(label: str, eur_val: float, total_eur: float, color: str, local_val: float | None = None, currency: str | None = None) -> str:
    """Génère une barre de progression avec affichage du montant en devise et son équivalent en euro."""
    # On s'assure que le pourcentage est positif et ne dépasse pas 100%
    # total_eur est la base de comparaison (le max de la carte)
    p = (max(0.0, float(eur_val)) / float(total_eur) * 100) if total_eur > 0 else 0.0
    p = min(p, 100.0)
    
    # Construction du libellé de montant (Devise Locale + EUR si différent)
    # On garde le signe pour l'affichage du texte si nécessaire, mais ici on traite souvent des abs() pour les bars de risque
    abs_local = abs(float(local_val)) if local_val is not None else 0.0
    abs_eur = abs(float(eur_val))
    
    if local_val is not None and currency is not None and currency != "EUR":
        display_val = f"{abs_local/1e3:,.0f}K {currency} ({abs_eur/1e3:,.0f}K €)"
    else:
        display_val = f"{abs_eur/1e3:,.0f}K €"
        
    return (
        f'<div style="margin-top:5px">'
        f'<div style="display:flex;justify-content:space-between;font-size:0.67rem;color:{color};font-weight:600">'
        f'<span>{label}</span><span>{display_val}</span></div>'
        f'<div style="background:#E5E7EB;height:5px;border-radius:2px;margin-top:2px">'
        f'<div style="background:{color};width:{p:.1f}%;height:5px;border-radius:2px"></div>'
        f'</div></div>'
    )

def _sec(title: str) -> None:
    st.markdown(f"""
        <div style="font-size:0.7rem;font-weight:700;color:#374151;letter-spacing:0.12em;
             margin-bottom:6px;padding-bottom:6px;border-bottom:1px solid #E5E7EB">{title}</div>
    """, unsafe_allow_html=True)

def render(now: datetime) -> None:
    page_header()
    st.markdown('<script>setTimeout(function(){window.location.reload();},900000);</script>', unsafe_allow_html=True)

    # 1. TICKER
    df_fx, df_rates = _get_ticker_data()
    _render_ticker(df_fx, df_rates)

    # 2. WELCOME
    _render_welcome_banner(now)

    # 3. METRICS
    m = _calculate_liquidity_metrics()
    _render_kpi_cards(m)

    # 4. CHART
    st.markdown('<hr style="margin:14px 0">', unsafe_allow_html=True)
    _render_positions_chart()

    # 5. TABLES
    st.markdown('<hr style="margin:20px 0">', unsafe_allow_html=True)
    _render_cutoff_table()
    st.markdown('<hr style="margin:20px 0">', unsafe_allow_html=True)
    _render_rates_table()

def _render_ticker(df_fx, df_rates):
    items = []
    if not df_fx.empty:
        st.session_state["fx_eur_sek"] = float(df_fx["fx_eur_sek"].mean())
        st.session_state["fx_eur_pln"] = float(df_fx["fx_eur_pln"].mean())
        st.session_state["fx_eur_usd"] = float(df_fx["fx_eur_usd"].mean())
        for pair, val in [("EUR/SEK", st.session_state["fx_eur_sek"]), 
                          ("EUR/PLN", st.session_state["fx_eur_pln"]), 
                          ("EUR/USD", st.session_state["fx_eur_usd"])]:
            items.append(f'<span style="color:{TEAL};font-weight:700">{pair}</span>&nbsp;<span style="color:#F1F5F9">{val:.4f}</span><span style="color:#334155;margin:0 22px">&#124;</span>')

    for _, r in df_rates.iterrows():
        color = GREEN if r["rate_type"] == "INVESTMENT" else RED
        items.append(f'<span style="color:{color};font-weight:700">{r["bank_name"]}</span>&nbsp;<span style="color:#F1F5F9">{float(r["rate_value"])*100:.2f}%</span><span style="color:#334155;margin:0 22px">&#124;</span>')

    if items:
        content = "".join(items) * 2
        st.markdown(f'<div class="ticker-wrap"><span class="ticker-badge">Taux J</span><div style="overflow:hidden;flex:1"><div class="ticker-track">{content}</div></div></div>', unsafe_allow_html=True)

def _render_welcome_banner(now):
    greet = "Bonjour" if now.hour < 12 else ("Bonne après-midi" if now.hour < 18 else "Bonsoir")
    n_acc = len(get_table("accounts")[get_table("accounts")["is_active"] == 1])
    n_bnk = len(get_table("banks")[get_table("banks")["is_active"] == 1])
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#EFF6FF 0%,#F0FDF4 100%);border-radius:12px;padding:16px 22px;margin-bottom:16px;border:1px solid #E0EDFF;display:flex;justify-content:space-between;align-items:center">
      <div>
        <div style="font-size:1.1rem;font-weight:700;color:#0F172A">{greet}, Trésorier 👋</div>
        <div style="font-size:0.78rem;color:#64748B;margin-top:2px">Vue consolidée au {now.strftime('%d %B %Y')}</div>
      </div>
      <div style="display:flex;gap:20px;text-align:center">
        <div><div style="font-size:0.6rem;font-weight:700;color:#9CA3AF">COMPTES</div><div style="font-size:1.2rem;font-weight:800;color:#1A56DB">{n_acc}</div></div>
        <div><div style="font-size:0.6rem;font-weight:700;color:#9CA3AF">BANQUES</div><div style="font-size:1.2rem;font-weight:800;color:#1A56DB">{n_bnk}</div></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

def _render_kpi_cards(m):
    c1, c2, c3 = st.columns(3)
    card_style = "background:#fff;border-radius:12px;padding:18px 20px;box-shadow:0 1px 4px rgba(0,0,0,0.06)"
    
    # Carte 1 : Liquidité Totale
    with c1:
        bars_html = "".join([
            _render_pbar(curr, data["balance_eur"], m["total"], BLUE, data["book_balance"], curr)
            for curr, data in sorted(m["by_currency"].items(), key=lambda x: x[1]["balance_eur"], reverse=True)
        ])
        st.markdown(
            f'<div style="{card_style};border-top:3px solid {BLUE}">'
            f'<div style="font-size:0.6rem;font-weight:700;color:#6B7280">LIQUIDITÉ CONSOLIDÉE</div>'
            f'<div style="font-size:1.7rem;font-weight:800;color:{BLUE}">{m["total"]:,.0f} €</div>'
            f'{bars_html}</div>', 
            unsafe_allow_html=True
        )
    
    # Carte 2 : Surplus
    with c2:
        bars_html = "".join([
            _render_pbar(curr, data["balance_eur"], m["surplus"], GREEN, data["book_balance"], curr)
            for curr, data in sorted(m["surplus_by_curr"].items(), key=lambda x: x[1]["balance_eur"], reverse=True)
        ])
        if not bars_html:
            bars_html = _render_pbar("Dispo", 0, 1, GREEN)
            
        st.markdown(
            f'<div style="{card_style};border-top:3px solid {GREEN}">'
            f'<div style="font-size:0.6rem;font-weight:700;color:#6B7280">SURPLUS CASH</div>'
            f'<div style="font-size:1.7rem;font-weight:800;color:{GREEN}">{m["surplus"]:,.0f} €</div>'
            f'{bars_html}</div>', 
            unsafe_allow_html=True
        )
    
    # Carte 3 : Risque
    with c3:
        # Pour le risque, on affiche les montants absolus dans les barres
        bars_html = "".join([
            _render_pbar(curr, abs(data["balance_eur"]), m["overdraft"], RED, abs(data["book_balance"]), curr)
            for curr, data in sorted(m["overdraft_by_curr"].items(), key=lambda x: x[1]["balance_eur"]) # Plus négatif en premier
        ])
        if not bars_html:
            bars_html = _render_pbar("Alerte", 0, 1, RED)

        st.markdown(
            f'<div style="{card_style};border-top:3px solid {RED}">'
            f'<div style="font-size:0.6rem;font-weight:700;color:#991B1B">RISQUE DÉCOUVERT</div>'
            f'<div style="font-size:1.7rem;font-weight:800;color:{RED}">{m["overdraft"]:,.0f} €</div>'
            f'{bars_html}</div>', 
            unsafe_allow_html=True
        )

def _render_positions_chart():
    _sec("BANKING POSITIONS")
    df = get_table("v_banking_positions").sort_values("total_balance_eur", ascending=True)
    if df.empty: return
    df = df.rename(columns={"total_balance_eur": "balance_eur"})
    df["couleur"] = df["balance_eur"].apply(lambda x: "Positif" if x >= 0 else "Négatif")
    fig = px.bar(df, x="balance_eur", y="bank_name", orientation="h", color="couleur", color_discrete_map={"Positif": GREEN, "Négatif": RED}, text="balance_eur")
    fig.update_traces(texttemplate="%{x:,.0f} €", textposition="outside")
    fig.update_layout(showlegend=False, height=300, margin=dict(l=0, r=0, t=0, b=0))
    apply_chart_theme(fig)
    st.plotly_chart(fig, use_container_width=True)

def _render_cutoff_table():
    _sec("⏰ BANK CUT-OFFS & LIQUIDITY PLACEMENT")
    df = get_table("v_today_negotiations")
    if df.empty: return
    df_display = pd.DataFrame([{
        "Banque": r["bank_name"], "ON": r["cutoff_overnight"], "MMF": r["cutoff_mmf"],
        "Solde Valeur": r["available_balance_value"], "Capacité": r["room_to_invest"],
        "Statut": "🟢 Prêt" if r["available_balance_value"] >= r["min_invest_eur"] and r["room_to_invest"] > 0 else "🔴 Limite"
    } for _, r in df.iterrows()])
    st.dataframe(df_display.style.format({"Solde Valeur": "{:,.0f} €", "Capacité": "{:,.0f} €"}), use_container_width=True, hide_index=True)

def _render_rates_table():
    _sec("BANK RATES")
    df = get_table("v_today_negotiations")
    if df.empty: return
    df_disp = df[["bank_name", "od_rate", "rate_overnight", "rate_dat_1m", "rate_dat_3m", "rate_dat_6m", "rate_mmf", "fx_eur_sek", "fx_eur_pln", "fx_eur_usd"]].rename(columns={
        "bank_name": "Banque", "od_rate": "Découvert", "rate_overnight": "Overnight", "rate_dat_1m": "1M", "rate_dat_3m": "3M", "rate_dat_6m": "6M", "rate_mmf": "MMF"
    })
    formats: dict[str, str] = {c: "{:.2%}" for c in df_disp.columns if c not in ["Banque", "fx_eur_sek", "fx_eur_pln", "fx_eur_usd"]}
    formats.update({"fx_eur_sek": "{:.4f}", "fx_eur_pln": "{:.4f}", "fx_eur_usd": "{:.4f}"})
    st.dataframe(df_disp.style.format(formats), use_container_width=True, hide_index=True) # type: ignore
