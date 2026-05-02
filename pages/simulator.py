# pages/simulator.py — Simulateur de Trésorerie v2
# 5 blocs structurés : Position → Pooling → Transferts → Placements → Scénarios
# Les soldes non-EUR sont toujours convertis en EUR au taux du jour avant simulation.
# ──────────────────────────────────────────────────────────────────────────────

import streamlit as st  # type: ignore
import pandas as pd     # type: ignore
from datetime import datetime, timedelta
import os

from db.database import get_table
from components.navbar import page_header

# ── Couleurs ──────────────────────────────────────────────────────────────────
_BLUE   = "#1A56DB"
_GREEN  = "#057A55"
_RED    = "#E02424"
_AMBER  = "#FF8000"
_TEAL   = "#0D9488"
_NAVY   = "#0F172A"

# ── Constantes financières ─────────────────────────────────────────────────────
SWIFT_FEE_PCT   = 0.0001
BASE_DAYS       = 365
MIN_SURPLUS_EUR = 1_000

_INSTR_KEYS = ["Overnight J+1", "DAT 1M", "DAT 3M", "DAT 6M", "Money Market Fund"]
_INSTR_RATE_COLS = {
    "Overnight J+1":     "rate_overnight",
    "DAT 1M":            "rate_dat_1m",
    "DAT 3M":            "rate_dat_3m",
    "DAT 6M":            "rate_dat_6m",
    "Money Market Fund": "rate_mmf",
}
_INSTR_DURATIONS = {
    "Overnight J+1": 1, "DAT 1M": 30, "DAT 3M": 90,
    "DAT 6M": 180, "Money Market Fund": 1,
}
_INSTR_CUTOFF_COLS = {
    "Overnight J+1":     "cutoff_overnight",
    "DAT 1M":            "cutoff_overnight",
    "DAT 3M":            "cutoff_overnight",
    "DAT 6M":            "cutoff_overnight",
    "Money Market Fund": "cutoff_mmf",
}
_FX_COLS    = {"SEK": "fx_eur_sek", "PLN": "fx_eur_pln", "USD": "fx_eur_usd"}
_SC_LETTERS = ["A", "B", "C"]

_EMPTY_TD = pd.DataFrame(columns=[
    "Banque source", "Banque destination", "Compte source",
    "Compte destination", "Montant EUR", "Frais SWIFT", "Type"
])


# ══════════════════════════════════════════════════════════════════════════════
# UTILITAIRES
# ══════════════════════════════════════════════════════════════════════════════

def _cutoff_status(cutoff_str: str, now: datetime) -> str:
    try:
        h, m = map(int, str(cutoff_str).strip().split(":"))
        diff = h * 60 + m - (now.hour * 60 + now.minute)
        if diff < 0:   return "expired"
        if diff <= 30: return "warning"
        return "ok"
    except Exception:
        return "ok"


def _cutoff_countdown(cutoff_str: str, now: datetime) -> str:
    try:
        h, m = map(int, str(cutoff_str).strip().split(":"))
        diff = h * 60 + m - (now.hour * 60 + now.minute)
        if diff < 0: return "Dépassé"
        return f"{diff // 60}h{diff % 60:02d}" if diff >= 60 else f"{diff} min"
    except Exception:
        return "—"


def _cutoff_open(cutoff_str: str, now: datetime) -> bool:
    return _cutoff_status(cutoff_str, now) != "expired"


def _acc_label(row: pd.Series) -> str:
    return f"{row['bank_name']} — {row['account_number']} ({row['currency']}, {row['account_type']})"


def _fx_rate_for(ccy: str, df_neg: pd.DataFrame) -> float:
    if ccy == "EUR":
        return 1.0
    col = _FX_COLS.get(ccy)
    if col and not df_neg.empty and col in df_neg.columns:
        return float(df_neg[col].iloc[0])
    return st.session_state.get(f"fx_eur_{ccy.lower()}", 1.0)


def _to_eur(amount: float, ccy: str, rate: float) -> float:
    if ccy == "EUR" or rate == 0:
        return amount
    return amount / rate


def _compute_post_balances(df_main: pd.DataFrame, td: pd.DataFrame) -> dict:
    balances = df_main.set_index("bank_name")["total_balance_eur"].to_dict()
    if td.empty:
        return balances
    for _, t in td.iterrows():
        src = t.get("Banque source")
        dst = t.get("Banque destination")
        amt = float(t.get("Montant EUR", 0) or 0)
        fee = float(t.get("Frais SWIFT", 0) or 0)
        if pd.isna(src) or pd.isna(dst) or amt <= 0:
            continue
        if src in balances:
            balances[src] -= (amt + fee)
        if dst in balances:
            balances[dst] += amt
    return balances


def _calc_sweeps(sat_rows: list, master_row: pd.Series, thresholds: list) -> pd.DataFrame:
    master_bank = master_row["bank_name"]
    master_num  = master_row["account_number"]
    rows = []
    for sr, thr in zip(sat_rows, thresholds):
        bal   = float(sr.get("balance_eur", 0) or 0)
        s_bk  = sr["bank_name"]
        s_num = sr["account_number"]
        cross = s_bk != master_bank
        if bal > thr:
            amt = bal - thr
            rows.append({
                "Banque source": s_bk, "Banque destination": master_bank,
                "Compte source": s_num, "Compte destination": master_num,
                "Montant EUR": round(amt, 2),
                "Frais SWIFT": round(amt * SWIFT_FEE_PCT if cross else 0.0, 2),
                "Type": "Sweep → pivot" + (" (cross)" if cross else " (intra)"),
            })
        elif bal < 0:
            amt = abs(bal) + thr
            rows.append({
                "Banque source": master_bank, "Banque destination": s_bk,
                "Compte source": master_num, "Compte destination": s_num,
                "Montant EUR": round(amt, 2),
                "Frais SWIFT": round(amt * SWIFT_FEE_PCT if cross else 0.0, 2),
                "Type": "Cover ← pivot" + (" (cross)" if cross else " (intra)"),
            })
    return pd.DataFrame(rows) if rows else _EMPTY_TD.copy()


def _build_scenario_metrics(sc: dict, df_f_j1: pd.DataFrame, df_f_j2: pd.DataFrame) -> dict:
    t = sc.get("transfers", pd.DataFrame())
    p = sc.get("placements", pd.DataFrame())
    net_income    = float(p["Revenu net PFU"].sum())    if not p.empty and "Revenu net PFU"    in p.columns else 0.0
    transfer_cost = float(t["Frais SWIFT"].sum())       if not t.empty and "Frais SWIFT"        in t.columns else 0.0
    total_placed  = float(p["Montant placé EUR"].sum()) if not p.empty and "Montant placé EUR" in p.columns else 0.0
    wav_rate = 0.0
    if total_placed > 0 and "Taux" in p.columns and "Montant placé EUR" in p.columns:
        wav_rate = float((p["Montant placé EUR"] * p["Taux"]).sum() / total_placed)
    concentration = 0.0
    if total_placed > 0 and "Banque" in p.columns:
        concentration = float(p.groupby("Banque")["Montant placé EUR"].sum().max() / total_placed * 100)
    out_j1   = float(df_f_j1["total_out"].sum()) if not df_f_j1.empty else 0.0
    residual = sc.get("net_position", 0.0) - total_placed - transfer_cost - out_j1
    return {
        "net_income":    net_income,
        "transfer_cost": transfer_cost,
        "wav_rate":      wav_rate,
        "concentration": concentration,
        "residual_j1":   residual,
        "pool_type":     sc.get("pool_type", "—"),
        "net_impact":    net_income - transfer_cost,
    }


def _fmt_metric(val, fmt_str: str) -> str:
    if val is None:
        return "—"
    try:
        return fmt_str.format(val)
    except Exception:
        return str(val)


# ══════════════════════════════════════════════════════════════════════════════
# HTML BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def _context_bar_html(df_main: pd.DataFrame, now: datetime) -> str:

    def _cut_badge(bank: str, cutoff_str: str) -> str:
        colors = {"ok": "#34d399", "warning": "#fbbf24", "expired": "#f87171"}
        color  = colors.get(_cutoff_status(cutoff_str, now), "#94a3b8")
        cd     = _cutoff_countdown(cutoff_str, now)
        expired = _cutoff_status(cutoff_str, now) == "expired"
        opacity = "opacity:.45;" if expired else ""
        return (
            f'<span style="{opacity}display:inline-flex;align-items:center;gap:6px;'
            f'background:{color}16;border:1px solid {color}40;color:{color};'
            f'padding:4px 10px 4px 8px;border-radius:6px;font-size:11px;'
            f'font-weight:600;white-space:nowrap;flex-shrink:0;">'
            f'<span style="width:7px;height:7px;border-radius:50%;background:{color};'
            f'flex-shrink:0;"></span>'
            f'<span style="color:#e2e8f0;font-weight:500;">{bank}</span>'
            f'<span style="color:#64748b;font-size:10px;">{cutoff_str}</span>'
            f'<span style="color:{color};font-weight:700;font-size:11px;">{cd}</span>'
            f'</span>'
        )

    cuts_html = ""
    if not df_main.empty:
        for _, row in df_main.iterrows():
            cuts_html += _cut_badge(
                str(row.get("bank_name", "")),
                str(row.get("cutoff_overnight", "16:00")),
            )

    return f"""
<div class="ctx-bar">
  <span class="ctx-cuts-label">CUT-OFFS</span>
  <div class="ctx-cuts-scroll">
    {cuts_html}
  </div>
</div>"""


def _bloc_header_html(num: int, title: str, badge: str = "") -> str:
    badge_html = (
        f' <span style="background:#dbeafe;color:#1e40af;padding:2px 10px;'
        f'border-radius:99px;font-size:10px;font-weight:700;">{badge}</span>'
    ) if badge else ""
    return (
        f'<div class="sim-bloc-hdr">'
        f'<div class="sim-bloc-num">{num}</div>'
        f'<span style="font-size:14px;font-weight:700;color:#0f172a;">{title}</span>'
        f'{badge_html}</div>'
    )


def _flow_map_html(sweeps_df: pd.DataFrame) -> str:
    if sweeps_df.empty:
        return ('<p style="color:#64748b;font-size:12px;text-align:center;padding:16px;">'
                'Aucun sweep calculé.</p>')
    lines = []
    for _, row in sweeps_df.iterrows():
        src  = str(row.get("Banque source", "?"))
        dst  = str(row.get("Banque destination", "?"))
        amt  = float(row.get("Montant EUR", 0) or 0)
        fee  = float(row.get("Frais SWIFT", 0) or 0)
        is_s = "Sweep" in str(row.get("Type", ""))
        bg   = "#fce7f3" if is_s else "#e0f2fe"
        fg   = "#be185d" if is_s else "#0369a1"
        fee_s = (f' <span style="color:#f59e0b;font-size:10px;">(frais {fee:,.0f} €)</span>'
                 if fee > 0 else "")
        lines.append(
            f'<div style="display:flex;align-items:center;gap:8px;margin:5px 0;font-size:12px;">'
            f'<span style="background:{bg};color:{fg};padding:3px 10px;border-radius:5px;'
            f'font-weight:600;white-space:nowrap;">{src}</span>'
            f'<span style="color:#94a3b8;font-size:18px;line-height:1">→</span>'
            f'<span style="background:#1A56DB22;color:#1A56DB;padding:3px 10px;'
            f'border-radius:5px;font-weight:700;white-space:nowrap;">★ {dst}</span>'
            f'<span style="margin-left:auto;color:#334155;font-weight:600;'
            f'white-space:nowrap;">{amt:,.0f} €{fee_s}</span>'
            f'</div>'
        )
    return (
        '<div style="padding:14px;background:white;border-radius:8px;border:1px solid #e2e8f0;">'
        '<div style="font-size:10px;font-weight:700;text-transform:uppercase;'
        'color:#94a3b8;margin-bottom:10px;letter-spacing:.06em;">Flux de consolidation</div>'
        + "".join(lines) + '</div>'
    )


# ══════════════════════════════════════════════════════════════════════════════
# BLOC 1 — Position de départ
# ══════════════════════════════════════════════════════════════════════════════

def _render_bloc1(df_accounts: pd.DataFrame, df_neg: pd.DataFrame, now: datetime,
                  total_eur: float, surplus: float, overdraft: float) -> None:
    st.markdown(
        _bloc_header_html(1, "Position de départ",
                          f"{now.strftime('%d/%m/%Y')}"),
        unsafe_allow_html=True,
    )

    rows = []
    for _, ar in df_accounts.iterrows():
        bn = df_neg[df_neg["bank_name"] == ar["bank_name"]]
        plafond = 0.0
        cutoff  = "16:00"
        if not bn.empty:
            b = bn.iloc[0]
            plafond = max(0.0,
                          float(b.get("counterparty_limit_eur", 0) or 0) -
                          float(b.get("counterparty_exposure",  0) or 0))
            cutoff  = str(b.get("cutoff_overnight", "16:00"))

        st_cut = _cutoff_status(cutoff, now)
        icons  = {"ok": "🟢", "warning": "🟡", "expired": "🔴"}
        rows.append({
            "Banque":        ar["bank_name"],
            "N° Compte":     ar["account_number"],
            "Devise":        ar["currency"],
            "Solde local":   float(ar.get("book_balance", 0) or 0),
            "Équiv. EUR":    float(ar.get("balance_eur",  0) or 0),
            "Plafond dispo.": plafond,
            "Cut-off":       f"{icons[st_cut]} {cutoff} · {_cutoff_countdown(cutoff, now)}",
            "_neg":          ar.get("balance_eur", 0) < 0,
            "_exp":          st_cut == "expired",
        })

    df_b1 = pd.DataFrame(rows)
    display_cols = ["Banque", "N° Compte", "Devise", "Solde local",
                    "Équiv. EUR", "Plafond dispo.", "Cut-off"]

    # Carte : Position de départ
    st.dataframe(
        df_b1[display_cols].style
        .format({
            "Solde local":    "{:,.0f}",
            "Équiv. EUR":     "{:,.0f} €",
            "Plafond dispo.": "{:,.0f} €",
        })
        .map(
            lambda v: f"color:{_RED};font-weight:700"
            if isinstance(v, (int, float)) and v < 0 else "",
            subset=["Solde local", "Équiv. EUR"],
        ),
        use_container_width=True,
        hide_index=True,
    )

    c1, c2, c3 = st.columns(3)
    # Carte : 💰 Total EUR disponible
    c1.metric("💰 Total EUR disponible", f"{total_eur:,.0f} €")
    # Carte : 📈 Surplus plaçable
    c2.metric("📈 Surplus plaçable",     f"{surplus:,.0f} €")
    # Carte : 📉 Overdraft à couvrir
    c3.metric("📉 Overdraft à couvrir",  f"{overdraft:,.0f} €")

    # FX conversion note — show rates used for non-EUR accounts
    non_eur = df_accounts[df_accounts["currency"] != "EUR"]["currency"].unique()
    if len(non_eur) > 0:
        rate_parts = []
        for ccy in non_eur:
            rate = _fx_rate_for(ccy, df_neg)
            rate_parts.append(f"1 EUR = <strong>{rate:.4f} {ccy}</strong>")
        st.markdown(
            f'<div style="margin-top:8px;padding:8px 14px;background:#f0f9ff;border-left:3px solid #0ea5e9;'
            f'border-radius:0 6px 6px 0;font-size:11.5px;color:#0369a1;">'
            f'💱 <strong>Conversion automatique au taux du jour :</strong> '
            + " &nbsp;·&nbsp; ".join(rate_parts) +
            " — Les soldes en devises sont convertis en EUR avant toute simulation."
            f"</div>",
            unsafe_allow_html=True,
        )
    st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# BLOC 2 — Pooling
# ══════════════════════════════════════════════════════════════════════════════

def _render_bloc3(df_accounts: pd.DataFrame, df_main: pd.DataFrame,
                  acc_label_to_id: dict, acc_id_to_row: dict,
                  all_labels: list, now: datetime) -> bool:
    """Renders the pooling bloc. Returns True if Physical Pooling is selected."""
    st.markdown(_bloc_header_html(2, "Type de pooling"), unsafe_allow_html=True)

    pool_type = st.radio(
        "Mécanisme",
        ["Physical Pooling", "Notional Pooling"],
        horizontal=True,
        key="pool_type_radio",
        help="Physical: sweeps physiques vers un compte pivot. "
             "Notional : compensation virtuelle, aucun mouvement.",
    )
    is_zba = pool_type.startswith("Physical")

    # ── ZBA ──────────────────────────────────────────────────────────────────
    if is_zba:
        st.info(
            "**Physical Pooling** — Les soldes satellites sont sweepés vers le compte pivot. "
            "Transferts cross-bank : frais SWIFT 0,01 %. Intra-bank : gratuit."
        )
        pool_members = st.multiselect(
            "Comptes dans le pool", options=all_labels, default=all_labels,
            key="physical_pool_members",
        )
        if len(pool_members) < 2:
            st.warning("Sélectionnez au moins 2 comptes pour former un pool Physical.")
            st.session_state["transfer_data"]   = _EMPTY_TD.copy()
            st.session_state["pool_type_label"] = "Physical Pooling"
            st.markdown("---")
            return True

        master_label = st.selectbox(
            "Compte pivot (master)", options=pool_members, key="physical_master",
            help="Reçoit les excédents et couvre les découverts des satellites.",
        )
        master_id  = acc_label_to_id[master_label]
        master_row = acc_id_to_row[master_id]

        sat_labels = [l for l in pool_members if l != master_label]
        sat_rows   = [acc_id_to_row[acc_label_to_id[l]] for l in sat_labels]

        sat_thresholds: list[float] = []
        if sat_labels:
            st.markdown("**Seuil minimum à laisser sur chaque satellite (€) :**")
            n_cols = min(3, len(sat_labels))
            grid   = st.columns(n_cols)
            for i, (sl, sr) in enumerate(zip(sat_labels, sat_rows)):
                with grid[i % n_cols]:
                    bal   = float(sr.get("balance_eur", 0) or 0)
                    color = _RED if bal < 0 else _GREEN
                    st.markdown(
                        f"**{sr['account_number']}** — {sr['bank_name'][:10]}  \n"
                        f"<span style='color:{color}'>{bal:,.0f} €</span>",
                        unsafe_allow_html=True,
                    )
                    thr = st.number_input(
                        "Seuil min (€)", min_value=0.0, value=0.0,
                        step=10_000.0, format="%.0f",
                        key=f"sat_thr_{i}", label_visibility="collapsed",
                    )
                    sat_thresholds.append(thr)

        if st.button("⚡ Calculer les sweeps Physical Pooling", type="primary",
                     use_container_width=True, key="physical_calc"):
            sweeps_df = _calc_sweeps(sat_rows, master_row, sat_thresholds)
            st.session_state["transfer_data"]   = sweeps_df
            st.session_state["pool_type_label"] = "Physical Pooling"
            st.rerun()

        # Flow map
        td = st.session_state.get("transfer_data", _EMPTY_TD)
        if not td.empty:
            vol    = float(td["Montant EUR"].sum())
            fees   = float(td["Frais SWIFT"].sum())
            n_crs  = int(td["Type"].str.contains("cross").sum())
            m1, m2, m3, m4 = st.columns(4)
            # Carte : Sweeps calculés
            m1.metric("Sweeps calculés",   len(td))
            # Carte : Volume transféré
            m2.metric("Volume transféré",  f"{vol:,.0f} €")
            # Carte : Frais SWIFT
            m3.metric("Frais SWIFT",       f"{fees:,.2f} €")
            # Carte : Cross / Intra
            m4.metric("Cross / Intra",     f"{n_crs} / {len(td) - n_crs}")
            # Carte : Flux de consolidation
            st.markdown(
                _flow_map_html(td),
                unsafe_allow_html=True,
            )
        else:
            st.info("Cliquez sur **Calculer les sweeps** pour générer les transferts.")

    # ── Notional ─────────────────────────────────────────────────────────────
    else:
        st.info(
            "**Notional Pooling** — Aucun transfert physique. "
            "La banque compense les intérêts sur la position nette. "
            "Chaque compte conserve son solde et investit son propre surplus."
        )
        notional_members = st.multiselect(
            "Comptes dans le pool", options=all_labels, default=all_labels,
            key="notional_members",
        )
        if notional_members:
            m_ids   = [acc_label_to_id[l] for l in notional_members]
            df_pool = df_accounts[df_accounts["account_id"].isin(m_ids)].copy()
            p_banks = df_pool["bank_name"].unique().tolist()

            pos_nette = float(df_pool["balance_eur"].sum())
            od_bef    = float(abs(df_pool[df_pool["balance_eur"] < 0]["balance_eur"].sum()))
            sur_bef   = float(df_pool[df_pool["balance_eur"] > 0]["balance_eur"].sum())
            bn_df     = df_main[df_main["bank_name"].isin(p_banks)]
            od_avg    = float(bn_df["od_rate"].mean())    if not bn_df.empty else 0.08
            inv_max   = float(bn_df["invest_rate"].max()) if not bn_df.empty else 0.035
            dep_rate  = st.session_state.get("dep_rate_fb", 0.005)
            eco_agios = od_bef * od_avg / BASE_DAYS
            rend_add  = (max(pos_nette, 0.0) * inv_max - sur_bef * dep_rate) / BASE_DAYS
            net_day   = eco_agios + rend_add

            n1, n2, n3, n4 = st.columns(4)
            # Carte : Position nette compensée
            n1.metric("Position nette compensée",    f"{pos_nette:,.0f} €")
            # Carte : Économie agios /jour
            n2.metric("Économie agios /jour",         f"{eco_agios:,.2f} €",
                      delta=f"{eco_agios * BASE_DAYS:,.0f} €/an")
            # Carte : Rendement additionnel /jour
            n3.metric("Rendement additionnel /jour",  f"{rend_add:,.2f} €")
            # Carte : Net impact /jour
            n4.metric("Net impact /jour",             f"{net_day:,.2f} €",
                      delta=f"{net_day * BASE_DAYS:,.0f} €/an")

        st.session_state["transfer_data"]   = _EMPTY_TD.copy()
        st.session_state["pool_type_label"] = "Notional"

    st.markdown("---")
    return is_zba


# ══════════════════════════════════════════════════════════════════════════════
# BLOC 3 — Transferts inter-banques
# ══════════════════════════════════════════════════════════════════════════════

def _render_bloc4(df_main: pd.DataFrame, now: datetime) -> None:
    is_zba = st.session_state.get("pool_type_label", "Physical Pooling") == "Physical Pooling"
    td     = st.session_state.get("transfer_data", _EMPTY_TD.copy())

    st.markdown(
        _bloc_header_html(3, "Transferts inter-banques",
                          "Pré-rempli Physical Pooling" if (not is_zba and not td.empty) else "Notional — aucun mouvement"),
        unsafe_allow_html=True,
    )

    if td.empty:
        st.info("Aucun transfert physique · Mode Notional actif ou sweeps non calculés.")
    else:
        # Compute post-balances and inline status
        post_bal = _compute_post_balances(df_main, td)
        rows_styled = []
        for _, t in td.iterrows():
            src   = str(t.get("Banque source", ""))
            dst   = str(t.get("Banque destination", ""))
            amt   = float(t.get("Montant EUR", 0) or 0)
            fee   = float(t.get("Frais SWIFT", 0) or 0)
            typ   = str(t.get("Type", ""))

            # Date de valeur
            src_row = df_main[df_main["bank_name"] == src]
            dst_row = df_main[df_main["bank_name"] == dst]
            src_ctry = str(src_row["bank_id"].iloc[0]) if not src_row.empty else ""
            dst_ctry = str(dst_row["bank_id"].iloc[0]) if not dst_row.empty else ""
            val_date = "J+1 SEPA" if src_ctry == dst_ctry else "J+2 Cross"

            # Counterparty % after transfer
            dst_limit = float(dst_row["counterparty_limit_eur"].iloc[0]) if not dst_row.empty else 0.0
            dst_post  = post_bal.get(dst, 0.0)
            cpty_pct  = (dst_post / dst_limit * 100) if dst_limit > 0 else 0.0

            src_post  = post_bal.get(src, 0.0)
            if src_post < 0:
                status_emoji = "🔴 Découvert"
                status_color = _RED
            elif cpty_pct > 80:
                status_emoji = "🟡 Plafond >80%"
                status_color = _AMBER
            else:
                status_emoji = "🟢 OK"
                status_color = _GREEN

            rows_styled.append({
                "Banque source":      src,
                "Banque destination": dst,
                "Montant EUR":        amt,
                "Frais SWIFT":        fee,
                "Type":               typ,
                "Date valeur":        val_date,
                "Contrepartie %":     f"{cpty_pct:.1f}%",
                "Statut":             status_emoji,
                "_color":             status_color,
            })

        df_td_disp = pd.DataFrame(rows_styled)
        display_cols = ["Banque source", "Banque destination", "Montant EUR",
                        "Frais SWIFT", "Type", "Date valeur", "Contrepartie %", "Statut"]
        st.dataframe(
            df_td_disp[display_cols].style
            .format({"Montant EUR": "{:,.0f} €", "Frais SWIFT": "{:,.2f} €"})
            .map(lambda v: f"color:{_RED};font-weight:700"
                 if isinstance(v, str) and "🔴" in v else (
                 f"color:{_AMBER};font-weight:600"
                 if isinstance(v, str) and "🟡" in v else ""),
                 subset=["Statut"]),
            use_container_width=True,
            hide_index=True,
        )

        # Totals
        total_fees = float(td["Frais SWIFT"].sum())
        st.markdown(
            f"<div style='text-align:right;font-size:12px;color:#6b7280;margin-top:8px;'>"
            f"Coût total des transferts : "
            f"<strong style='color:{_AMBER};'>{total_fees:,.2f} €</strong></div>",
            unsafe_allow_html=True,
        )

        # Post-transfer balances
        st.markdown(
            "<div style='font-size:11px;font-weight:700;text-transform:uppercase;"
            "letter-spacing:.06em;color:#94a3b8;margin:12px 0 8px;'>Soldes après transferts</div>",
            unsafe_allow_html=True,
        )
        # Carte : Soldes après transferts
        cols = st.columns(min(4, len(post_bal)))
        for i, (bank, bal) in enumerate(post_bal.items()):
            color = _RED if bal < 0 else (_AMBER if bal < 500_000 else _GREEN)
            with cols[i % len(cols)]:
                st.markdown(
                    f"<div style='padding:10px 14px;background:white;border:1px solid #e2e8f0;"
                    f"border-radius:8px;margin-bottom:6px;'>"
                    f"<div style='font-size:10px;color:#6b7280;margin-bottom:2px;'>{bank}</div>"
                    f"<div style='font-weight:700;color:{color};font-size:14px;'>"
                    f"{bal:,.0f} €</div></div>",
                    unsafe_allow_html=True,
                )

    st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# BLOC 4 — Placements
# ══════════════════════════════════════════════════════════════════════════════

def _render_bloc5(df_accounts: pd.DataFrame, df_main: pd.DataFrame,
                  acc_label_to_id: dict, acc_id_to_row: dict,
                  all_labels: list, post_balances: dict,
                  df_f_j1: pd.DataFrame, df_f_j2: pd.DataFrame,
                  tax_rate: float, now: datetime) -> list:
    is_zba = st.session_state.get("pool_type_label", "ZBA") == "ZBA"

    st.markdown(_bloc_header_html(4, "Placements"), unsafe_allow_html=True)

    placement_rows: list[dict] = []

    # ── ZBA : pivot investit ──────────────────────────────────────────────────
    if is_zba:
        master_label = st.session_state.get("zba_master")
        if master_label and master_label in acc_label_to_id:
            pivot_acc_id  = acc_label_to_id[master_label]
            pivot_bank    = acc_id_to_row[pivot_acc_id]["bank_name"]
            pivot_acc_num = acc_id_to_row[pivot_acc_id]["account_number"]
        else:
            pivot_bank    = df_main.iloc[0]["bank_name"] if not df_main.empty else "—"
            pivot_acc_num = ""

        bm = df_main[df_main["bank_name"] == pivot_bank]
        if bm.empty:
            st.warning("Banque pivot introuvable dans les conditions du jour.")
            st.markdown("---")
            return []

        bm_row       = bm.iloc[0]
        post_pivot   = post_balances.get(pivot_bank, float(bm_row.get("total_balance_eur", 0) or 0))
        fr_j1        = df_f_j1[df_f_j1["bank_name"] == pivot_bank]
        out_j1_pivot = float(fr_j1["total_out"].iloc[0]) if not fr_j1.empty else 0.0
        surplus      = max(0.0, post_pivot - out_j1_pivot)
        min_inv      = float(bm_row.get("min_invest_eur", MIN_SURPLUS_EUR) or MIN_SURPLUS_EUR)
        estr         = float(bm_row.get("estr_rate", 0.039) or 0.039)

        st.caption(f"Compte pivot : **{master_label or pivot_bank}**")
        pm1, pm2, pm3 = st.columns(3)
        # Carte : Solde post-sweeps
        pm1.metric("Solde post-sweeps", f"{post_pivot:,.0f} €")
        # Carte : Réserve J+1
        pm2.metric("Réserve J+1",        f"{out_j1_pivot:,.0f} €")
        # Carte : Surplus plaçable
        pm3.metric("Surplus plaçable",   f"{surplus:,.0f} €")

        if surplus < min_inv:
            st.info(f"Surplus insuffisant pour placement (minimum : {min_inv:,.0f} €).")
            st.markdown("---")
            return []

        total_allocated = 0.0

        # Instruments table
        st.markdown("**Allocation par instrument :**")
        for instr in _INSTR_KEYS:
            taux  = float(bm_row.get(_INSTR_RATE_COLS[instr], 0.035) or 0.035)
            dur   = _INSTR_DURATIONS[instr]
            avail = _cutoff_open(
                str(bm_row.get(_INSTR_CUTOFF_COLS[instr], "16:00")), now)
            co    = str(bm_row.get(_INSTR_CUTOFF_COLS[instr], "16:00"))
            spread = (taux - estr) * 10_000

            with st.container(border=True):
                if not avail:
                    st.markdown(
                        f"<div style='opacity:.45;pointer-events:none;'>",
                        unsafe_allow_html=True,
                    )
                h1, h2 = st.columns([5, 1])
                h1.markdown(f"**{instr}** &nbsp;·&nbsp; {dur} j &nbsp;·&nbsp; "
                            f"<span style='color:{_GREEN};font-weight:700'>{taux:.3%}</span> &nbsp;·&nbsp; "
                            f"<span style='color:{'#f87171' if not avail else ('#34d399' if spread >= 0 else '#f87171')};'>"
                            f"{'🔴 Cut-off dépassé' if not avail else f'ESTR +{spread:+.0f} bps'}</span>",
                            unsafe_allow_html=True)
                h2.markdown(
                    f"<span style='background:{'#fee2e2' if not avail else '#dcfce7'};"
                    f"color:{'#dc2626' if not avail else '#16a34a'};padding:2px 8px;"
                    f"border-radius:5px;font-size:10px;font-weight:700;'>{'✕ Fermé' if not avail else '✓ Ouvert'}</span>",
                    unsafe_allow_html=True,
                )
                ci1, ci2, ci3 = st.columns(3)
                remaining = max(0.0, surplus - total_allocated)
                with ci2:
                    amt = st.number_input(
                        f"Montant {instr} (€)",
                        min_value=0.0,
                        max_value=float(surplus),
                        step=10_000.0,
                        format="%.0f",
                        key=f"zba_pl_{instr}",
                        disabled=not avail,
                        help=f"Restant disponible : {remaining:,.0f} €",
                        label_visibility="collapsed",
                    )
                with ci1:
                    # Carte : Taux annuel
                    ci1.metric("Taux annuel", f"{taux:.3%}")
                with ci3:
                    if amt > 0 and avail:
                        brut = amt * taux * dur / BASE_DAYS
                        net  = brut * (1 - tax_rate)
                        # Carte : Revenu net
                        ci3.metric("Revenu net", f"{net:,.2f} €")
                    elif not avail:
                        ci3.warning("Cut-off dépassé")
                    else:
                        ci3.caption("Saisissez un montant")

                if not avail:
                    st.markdown("</div>", unsafe_allow_html=True)

            if amt > 0 and avail:
                total_allocated += amt
                brut = amt * taux * dur / BASE_DAYS
                placement_rows.append({
                    "Banque": pivot_bank, "N° Compte": pivot_acc_num,
                    "Instrument": instr, "Montant placé EUR": amt,
                    "Taux": taux, "Durée (j)": dur,
                    "Revenu brut EUR": brut,
                    "Revenu net PFU": brut * (1 - tax_rate),
                    "Spread vs ESTR": round(spread, 1),
                })

        # Barre de progression
        pct = min(1.0, total_allocated / surplus) if surplus > 0 else 0.0
        st.markdown(
            f"<div style='margin:12px 0 4px;font-size:12px;color:#6b7280;display:flex;"
            f"justify-content:space-between;'>"
            f"<span>Allocation du surplus</span>"
            f"<span style='color:{'#E02424' if total_allocated > surplus else '#334155'};'>"
            f"<strong>{total_allocated:,.0f} €</strong> / {surplus:,.0f} €</span></div>",
            unsafe_allow_html=True,
        )
        st.progress(pct)

        if total_allocated > surplus * 1.001:
            st.error(f"⛔ Total alloué {total_allocated:,.0f} € > surplus plaçable {surplus:,.0f} €")

    # ── Notional : chaque compte investit ────────────────────────────────────
    else:
        notional_cur = st.session_state.get("notional_members", all_labels)
        if not isinstance(notional_cur, list):
            notional_cur = all_labels
        m_ids_n   = [acc_label_to_id[l] for l in notional_cur if l in acc_label_to_id]
        df_pool_n = df_accounts[df_accounts["account_id"].isin(m_ids_n)].copy()

        if df_pool_n.empty:
            st.info("Aucun compte sélectionné dans le pool (section précédente).")
        else:
            surplus_total = 0.0
            any_surplus   = False
            for _, ar in df_pool_n.iterrows():
                bn      = ar["bank_name"]
                acc_id  = int(ar["account_id"])
                bal_eur = float(ar.get("balance_eur", 0) or 0)
                fr_n    = df_f_j1[df_f_j1["bank_name"] == bn]
                out_j1n = float(fr_n["total_out"].iloc[0]) if not fr_n.empty else 0.0
                n_same  = max(1, int((df_pool_n["bank_name"] == bn).sum()))
                surplus = max(0.0, bal_eur - out_j1n / n_same)
                bm_n    = df_main[df_main["bank_name"] == bn]
                if bm_n.empty:
                    continue
                bm_ns = bm_n.iloc[0]
                min_i = float(bm_ns.get("min_invest_eur", MIN_SURPLUS_EUR) or MIN_SURPLUS_EUR)
                if surplus < min_i:
                    continue

                any_surplus  = True
                surplus_total += surplus
                estr_n = float(bm_ns.get("estr_rate", 0.039) or 0.039)

                with st.container(border=True):
                    h1, h2 = st.columns([4, 1])
                    bc = _GREEN if bal_eur >= 0 else _RED
                    h1.markdown(
                        f"**{ar['account_number']}** — {bn} ({ar['currency']})  \n"
                        f"<span style='color:{bc}'>Solde : {bal_eur:,.0f} €</span>",
                        unsafe_allow_html=True,
                    )
                    h2.metric("Surplus", f"{surplus:,.0f} €")

                    ci1, ci2, ci3 = st.columns(3)
                    with ci1:
                        def _fmt_instr(i: str) -> str:
                            t = float(bm_ns.get(_INSTR_RATE_COLS[i], 0.035) or 0.035)
                            ok = _cutoff_open(
                                str(bm_ns.get(_INSTR_CUTOFF_COLS[i], "16:00")), now)
                            return f"{i} ({t:.3%})" + ("" if ok else " 🔴")
                        instr_n = st.selectbox(
                            "Instrument", options=_INSTR_KEYS,
                            key=f"n_instr_{acc_id}",
                            format_func=_fmt_instr,
                        )
                    taux_n  = float(bm_ns.get(_INSTR_RATE_COLS[instr_n], 0.035) or 0.035)
                    avail_n = _cutoff_open(
                        str(bm_ns.get(_INSTR_CUTOFF_COLS[instr_n], "16:00")), now)
                    with ci2:
                        amt_n = st.number_input(
                            "Montant (€)", min_value=0.0, max_value=surplus,
                            value=surplus if avail_n else 0.0,
                            step=10_000.0, format="%.0f",
                            key=f"n_amt_{acc_id}",
                            disabled=not avail_n,
                        )
                    with ci3:
                        if amt_n > 0 and avail_n:
                            dur_n  = _INSTR_DURATIONS[instr_n]
                            brut_n = amt_n * taux_n * dur_n / BASE_DAYS
                            net_n  = brut_n * (1 - tax_rate)
                            spread_n = (taux_n - estr_n) * 10_000
                            ci3.metric("Revenu net", f"{net_n:,.2f} €")
                            col = _GREEN if spread_n >= 0 else _RED
                            ci3.markdown(
                                f"<span style='color:{col}'>{spread_n:+.0f} bps vs ESTR</span>",
                                unsafe_allow_html=True,
                            )
                        elif not avail_n:
                            ci3.warning("Cut-off dépassé")

                if amt_n > 0 and avail_n:
                    dur_n  = _INSTR_DURATIONS[instr_n]
                    brut_n = amt_n * taux_n * dur_n / BASE_DAYS
                    placement_rows.append({
                        "Banque": bn, "N° Compte": ar["account_number"],
                        "Instrument": instr_n, "Montant placé EUR": amt_n,
                        "Taux": taux_n, "Durée (j)": dur_n,
                        "Revenu brut EUR": brut_n,
                        "Revenu net PFU": brut_n * (1 - tax_rate),
                        "Spread vs ESTR": round((taux_n - estr_n) * 10_000, 1),
                    })

            if not any_surplus:
                st.info("Aucun surplus suffisant après réserve J+1 et minimum de placement.")
            else:
                total_placed_n = sum(r["Montant placé EUR"] for r in placement_rows)
                pct_n = min(1.0, total_placed_n / surplus_total) if surplus_total > 0 else 0.0
                st.markdown(
                    f"<div style='margin:12px 0 4px;font-size:12px;color:#6b7280;"
                    f"display:flex;justify-content:space-between;'>"
                    f"<span>Allocation globale du pool</span>"
                    f"<span><strong>{total_placed_n:,.0f} €</strong> / {surplus_total:,.0f} €</span></div>",
                    unsafe_allow_html=True,
                )
                st.progress(pct_n)

    # ── Résumé placements ────────────────────────────────────────────────────
    if placement_rows:
        total_pl  = sum(r["Montant placé EUR"] for r in placement_rows)
        total_net = sum(r["Revenu net PFU"]    for r in placement_rows)
        wav       = sum(r["Montant placé EUR"] * r["Taux"] for r in placement_rows) / total_pl
        total_gross = sum(r["Revenu brut EUR"] for r in placement_rows)

        st.markdown("---")
        k1, k2, k3 = st.columns(3)
        k1.metric("Total placé",       f"{total_pl:,.0f} €")
        k2.metric("Revenu total net",   f"{total_net:,.2f} €",
                  delta=f"{total_net * BASE_DAYS:,.0f} €/an")
        k3.metric("Taux moyen pondéré", f"{wav:.3%}")

    # ── Alerte liquidité J+1 / J+2 ───────────────────────────────────────────
    total_placed_all = sum(r["Montant placé EUR"] for r in placement_rows)
    residual = (
        (post_balances.get(st.session_state.get("zba_master", ""), 0.0)
         if is_zba else float(df_main["total_balance_eur"].sum()))
        - total_placed_all
    )
    out_j1_total = float(df_f_j1["total_out"].sum()) if not df_f_j1.empty else 0.0
    out_j2_total = float(df_f_j2["total_out"].sum()) if not df_f_j2.empty else 0.0

    if out_j1_total > 0 or out_j2_total > 0:
        liq_j1 = residual - out_j1_total
        liq_j2 = residual - out_j2_total
        if liq_j1 < 0 or liq_j2 < 0:
            worst = min(liq_j1, liq_j2)
            st.warning(
                f"⚠️ **Alerte liquidité** — Les sorties prévues J+1 ({out_j1_total:,.0f} €) "
                f"/ J+2 ({out_j2_total:,.0f} €) dépassent la liquidité résiduelle "
                f"({residual:,.0f} €). Risque de manque de cash demain "
                f"(écart estimé : **{worst:,.0f} €**). Réduisez les placements."
            )

    st.markdown("---")
    return placement_rows


# ══════════════════════════════════════════════════════════════════════════════
# BLOC 5 — Comparaison de scénarios
# ══════════════════════════════════════════════════════════════════════════════

def _render_bloc6(df_placements: pd.DataFrame, total_net_pos: float,
                  df_f_j1: pd.DataFrame, df_f_j2: pd.DataFrame, now: datetime,
                  df_accounts: pd.DataFrame = None) -> None:
    st.markdown(_bloc_header_html(5, "Comparaison de scénarios"), unsafe_allow_html=True)

    # Snapshot buttons (A, B, C)
    cols = st.columns(3)
    for i, letter in enumerate(_SC_LETTERS):
        key = f"scenario_{letter.lower()}"
        with cols[i]:
            already = key in st.session_state
            if st.button(
                f"💾 Snapshot → Scénario {letter}",
                type="secondary" if already else "primary",
                use_container_width=True,
                key=f"snap_btn_{letter}",
                disabled=already,
            ):
                st.session_state[key] = {
                    "pool_type":        st.session_state.get("pool_type_label", "—"),
                    "transfers":        st.session_state.get("transfer_data", _EMPTY_TD.copy()).copy(),
                    "placements":       df_placements.copy(),
                    "net_position":     total_net_pos,
                    "timestamp":        now,
                    "accounts_snapshot": df_accounts.copy() if df_accounts is not None else pd.DataFrame(),
                }
                st.toast(f"✅ Scénario {letter} sauvegardé !")
                st.rerun()

    # Reset button
    saved_keys = [k for k in [f"scenario_{l.lower()}" for l in _SC_LETTERS]
                  if k in st.session_state]
    if saved_keys:
        if st.button("🗑 Effacer tous les scénarios", type="secondary",
                     key="clear_scenarios"):
            for k in saved_keys:
                del st.session_state[k]
            st.rerun()

    # Comparison table
    saved_scs = {
        l: st.session_state[f"scenario_{l.lower()}"]
        for l in _SC_LETTERS
        if f"scenario_{l.lower()}" in st.session_state
    }
    if not saved_scs:
        st.info(
            "Configurez les blocs 2 à 4, puis cliquez sur **Snapshot → Scénario A** "
            "pour commencer la comparaison."
        )
        st.markdown("---")
        return

    metrics_computed = {
        l: _build_scenario_metrics(sc, df_f_j1, df_f_j2)
        for l, sc in saved_scs.items()
    }

    metrics_def = [
        ("Revenu net total",         "net_income",    True,  "{:,.2f} €"),
        ("Coût transferts",          "transfer_cost", False, "{:,.2f} €"),
        ("Taux moyen pondéré",       "wav_rate",      True,  "{:.3%}"),
        ("Concentration max",        "concentration", False, "{:.1f} %"),
        ("Liquidité résiduelle J+1", "residual_j1",   True,  "{:,.0f} €"),
        ("Net impact total",         "net_impact",    True,  "{:,.2f} €"),
        ("Type de pooling",          "pool_type",     None,  "{}"),
    ]

    # Find best scenario (net_impact)
    best_letter = max(
        metrics_computed.items(),
        key=lambda x: x[1].get("net_impact", float("-inf")),
    )[0] if len(metrics_computed) > 1 else list(metrics_computed.keys())[0]

    # Build comparison DataFrame
    comp_rows = []
    for label, key, higher, fmt in metrics_def:
        vals = {l: m.get(key) for l, m in metrics_computed.items()}
        if higher is not None:
            best_val = max(vals.values()) if higher else min(vals.values())
        else:
            best_val = None
        row: dict = {"Métrique": label}
        for l, v in vals.items():
            cell = _fmt_metric(v, fmt)
            if best_val is not None and len(metrics_computed) > 1:
                try:
                    num = float(v)  # type: ignore[arg-type]
                    cell += " ✅" if abs(num - float(best_val)) < 1e-9 else ""
                except Exception:
                    pass
            row[f"Scénario {l}"] = cell
        comp_rows.append(row)

    df_comp = pd.DataFrame(comp_rows)
    # Carte : Comparaison de scénarios
    st.dataframe(df_comp, use_container_width=True, hide_index=True)

    # Recommendation
    if len(metrics_computed) > 1:
        best_m = metrics_computed[best_letter]
        st.success(
            f"🏆 **Recommandation : Scénario {best_letter}** — "
            f"Net impact : {best_m['net_impact']:,.2f} € "
            f"| Pooling : {best_m['pool_type']}"
        )

    # Validate button
    if st.button("✓ Valider ce scénario et générer la fiche",
                 type="primary", use_container_width=True, key="validate_scenario"):
        chosen_letter = best_letter
        st.session_state["fiche_scenario_key"] = f"scenario_{chosen_letter.lower()}"
        st.session_state["fiche_scenario_label"] = chosen_letter
        st.rerun()

    st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# FICHE D'INSTRUCTION
# ══════════════════════════════════════════════════════════════════════════════

def _render_fiche(df_f_j1: pd.DataFrame, df_f_j2: pd.DataFrame,
                  now: datetime) -> None:
    sc_key = st.session_state.get("fiche_scenario_key")
    sc_lbl = st.session_state.get("fiche_scenario_label", "?")
    if not sc_key or sc_key not in st.session_state:
        return

    sc      = st.session_state[sc_key]
    sc_met  = _build_scenario_metrics(sc, df_f_j1, df_f_j2)
    t_data  = sc.get("transfers", pd.DataFrame())
    p_data  = sc.get("placements", pd.DataFrame())
    ts      = sc.get("timestamp", now)

    with st.expander(
        f"📋 Fiche d'instruction — Scénario {sc_lbl} · "
        f"{ts.strftime('%d/%m/%Y %H:%M')}",
        expanded=True,
    ):
        st.markdown(
            f"**Date :** {ts.strftime('%d/%m/%Y %H:%M')} &nbsp;|&nbsp; "
            f"**Scénario {sc_lbl}** &nbsp;|&nbsp; "
            f"**Pooling : {sc.get('pool_type', '—')}**"
        )
        st.markdown("---")

        # ── I. Conversions de change automatiques ────────────────────────────
        st.markdown("##### I. Conversions de change")
        st.info(
            "Les soldes en devises étrangères sont **automatiquement convertis en EUR** "
            "au taux de change du jour de la banque émettrice, avant tout transfert ou placement."
        )
        # Show rates used for each non-EUR account in the snapshot
        sc_accounts = sc.get("accounts_snapshot", pd.DataFrame())
        if not sc_accounts.empty:
            non_eur_rows = sc_accounts[sc_accounts["currency"] != "EUR"]
            if not non_eur_rows.empty:
                fx_lines = []
                for _, r in non_eur_rows.iterrows():
                    local = float(r.get("book_balance", 0) or 0)
                    eur   = float(r.get("balance_eur",  0) or 0)
                    rate  = local / eur if eur != 0 else 0.0
                    fx_lines.append(
                        f"- **{r['bank_name']} — {r['account_number']}** : "
                        f"{local:,.0f} {r['currency']} → **{eur:,.0f} €** "
                        f"(taux : 1 EUR = {rate:.4f} {r['currency']})"
                    )
                st.markdown("\n".join(fx_lines))

        # ── II. Transferts inter-banques ──────────────────────────────────────
        st.markdown("##### II. Transferts inter-banques")
        if t_data.empty:
            st.write("*Aucun transfert physique (Notional Pooling)*")
        else:
            st.dataframe(
                t_data.style.format(
                    {"Montant EUR": "{:,.0f} €", "Frais SWIFT": "{:,.2f} €"}
                ),
                use_container_width=True,
                hide_index=True,
            )

        # ── III. Ordres de placement ──────────────────────────────────────────
        st.markdown("##### III. Ordres de placement")
        if p_data.empty:
            st.write("*Aucun placement simulé*")
        else:
            p_cols = [c for c in ["Banque", "N° Compte", "Instrument",
                                   "Montant placé EUR", "Taux",
                                   "Durée (j)", "Revenu net PFU"]
                      if c in p_data.columns]
            st.dataframe(
                p_data[p_cols].style.format({
                    "Montant placé EUR": "{:,.0f} €",
                    "Taux":             "{:.4%}",
                    "Revenu net PFU":   "{:,.2f} €",
                }),
                use_container_width=True,
                hide_index=True,
            )

        # ── IV. Couvertures ───────────────────────────────────────────────────
        st.markdown("##### IV. Couvertures à terme")
        st.write("*Aucune couverture à terme — conversion systématique au cours du jour.*")

        # ── Synthèse ──────────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("##### Synthèse")
        r1, r2, r3 = st.columns(3)
        # Carte : Revenu net total
        r1.metric("Revenu net total",      f"{sc_met['net_income']:,.2f} €")
        # Carte : Net après frais
        r2.metric("Net après frais",       f"{sc_met['net_impact']:,.2f} €")
        # Carte : Taux moyen pondéré
        r3.metric("Taux moyen pondéré",    f"{sc_met['wav_rate']:.4%}")
        s1, s2 = st.columns(2)
        # Carte : Coût transferts
        s1.metric("Coût transferts",       f"{sc_met['transfer_cost']:,.2f} €")
        # Carte : Liquidité résiduelle J+1
        s2.metric("Liquidité résiduelle J+1", f"{sc_met['residual_j1']:,.0f} €")

        # Export CSV
        csv_parts = []
        if not t_data.empty:
            csv_parts.append(t_data.assign(Catégorie="Transfert"))
        if not p_data.empty:
            csv_parts.append(p_data.assign(Catégorie="Placement"))
        if csv_parts:
            csv_out = pd.concat(csv_parts, ignore_index=True)
            st.download_button(
                "⬇️ Exporter la fiche en CSV",
                csv_out.to_csv(index=False).encode("utf-8"),
                f"instruction_sc{sc_lbl}_{ts.strftime('%Y%m%d_%H%M')}.csv",
                "text/csv",
                use_container_width=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════════════

def render(now: datetime) -> None:
    page_header()

    # ── Initialisation session ───────────────────────────────────────────────
    if "transfer_data"  not in st.session_state:
        st.session_state["transfer_data"]  = _EMPTY_TD.copy()
    if "placement_data" not in st.session_state:
        st.session_state["placement_data"] = pd.DataFrame()

    # ── Chargement des données ───────────────────────────────────────────────
    acc    = get_table("accounts")
    banks  = get_table("banks")
    bal    = get_table("daily_account_balances")
    neg    = get_table("v_today_negotiations")
    pos    = get_table("v_banking_positions")
    fcasts = get_table("forecasts")

    if acc.empty or banks.empty or bal.empty or neg.empty or pos.empty:
        st.warning("⚠️ Données insuffisantes pour la simulation.")
        return

    # df_accounts : un compte par ligne avec solde
    latest_idx  = bal.groupby("account_id")["date"].idxmax()
    df_bal      = bal.loc[latest_idx]
    df_accounts = (
        acc
        .merge(banks, on="bank_id", suffixes=("", "_bank"))
        .merge(df_bal, on="account_id")
    )
    df_accounts = df_accounts[df_accounts["is_active"] == 1].sort_values(
        ["bank_name", "account_number"]
    )

    df_neg = neg.copy()
    df_pos = pos.copy()

    # df_main : une banque par ligne avec conditions
    df_main = df_pos.merge(
        df_neg[[
            "bank_name", "bank_id", "counterparty_limit_eur", "counterparty_exposure",
            "cutoff_overnight", "cutoff_mmf", "od_rate", "invest_rate", "estr_rate",
            "pool_fee_pct", "rate_overnight", "rate_dat_1m", "rate_dat_3m",
            "rate_dat_6m", "rate_mmf", "min_invest_eur", "room_to_invest",
        ]],
        on="bank_name",
        how="left",
    )
    df_main["plafond_restant"] = (
        df_main["counterparty_limit_eur"].fillna(0) -
        df_main["counterparty_exposure"].fillna(0)
    ).clip(lower=0)

    # Prévisions J+1 et J+2
    def _out_forecasts(date_str: str) -> pd.DataFrame:
        if fcasts.empty:
            return pd.DataFrame(columns=["bank_id", "bank_name", "total_out"])
        df_f = fcasts[
            (fcasts["type"] == "OUT") &
            (fcasts["forecast_date"].astype(str) == date_str)
        ]
        if df_f.empty:
            return pd.DataFrame(columns=["bank_id", "bank_name", "total_out"])
        df_f = (
            df_f
            .merge(acc, on="account_id")
            .merge(banks, on="bank_id", suffixes=("", "_b"))
        )
        return (
            df_f.groupby(["bank_id", "bank_name"])["amount"]
            .sum()
            .reset_index()
            .rename(columns={"amount": "total_out"})
        )

    j1_str  = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    j2_str  = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    df_f_j1 = _out_forecasts(j1_str)
    df_f_j2 = _out_forecasts(j2_str)

    # KPIs globaux
    tax_rate      = st.session_state.get("tax_rate", 0.30)
    total_net_pos = float(df_main["total_balance_eur"].sum())
    total_surplus = float(df_main[df_main["total_balance_eur"] > 0]["total_balance_eur"].sum())
    total_od      = float(abs(df_main[df_main["total_balance_eur"] < 0]["total_balance_eur"].sum()))

    acc_label_to_id = {_acc_label(r): int(r["account_id"]) for _, r in df_accounts.iterrows()}
    acc_id_to_row   = {int(r["account_id"]): r for _, r in df_accounts.iterrows()}
    all_labels      = list(acc_label_to_id.keys())

    # ── Titre + barre de contexte ────────────────────────────────────────────
    st.title("🏦 Simulateur de Trésorerie")
    st.markdown(
        _context_bar_html(df_main, now),
        unsafe_allow_html=True,
    )
    st.markdown("")

    # ── Bloc 1 ───────────────────────────────────────────────────────────────
    _render_bloc1(df_accounts, df_neg, now, total_net_pos, total_surplus, total_od)

    # ── Bloc 2 (pooling) ─────────────────────────────────────────────────────
    _render_bloc3(df_accounts, df_main, acc_label_to_id, acc_id_to_row, all_labels, now)

    # ── Bloc 4 (transferts) ──────────────────────────────────────────────────
    _render_bloc4(df_main, now)

    # ── Post-balances pour Bloc 5 ─────────────────────────────────────────────
    td            = st.session_state.get("transfer_data", _EMPTY_TD.copy())
    post_balances = _compute_post_balances(df_main, td)

    # ── Bloc 5 (placements) ──────────────────────────────────────────────────
    placement_rows = _render_bloc5(
        df_accounts, df_main,
        acc_label_to_id, acc_id_to_row, all_labels,
        post_balances, df_f_j1, df_f_j2, tax_rate, now,
    )
    df_placements = pd.DataFrame(placement_rows) if placement_rows else pd.DataFrame()
    st.session_state["placement_data"] = df_placements

    # ── Bloc 6 (scénarios) ───────────────────────────────────────────────────
    _render_bloc6(df_placements, total_net_pos, df_f_j1, df_f_j2, now, df_accounts)

    # ── Fiche d'instruction ───────────────────────────────────────────────────
    _render_fiche(df_f_j1, df_f_j2, now)

    # ── Téléchargement Excel maître ───────────────────────────────────────────
    with st.expander("🛠️ Gestion de la base de données", expanded=False):
        st.info("Le projet utilise exclusivement **Excel** comme source de données.")
        if os.path.exists("treasury_master.xlsx"):
            with open("treasury_master.xlsx", "rb") as f:
                st.download_button(
                    "⬇️ Télécharger treasury_master.xlsx",
                    data=f.read(),
                    file_name=f"treasury_master_{now.strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
        else:
            st.error("Fichier treasury_master.xlsx introuvable.")
