# =============================================================================
# dashboard.py — Point d'entrée principal du Treasury Dashboard
# =============================================================================

import streamlit as st  # type: ignore
from pathlib import Path

from db.database import get_db
from utils.config import _init_config
from components.navbar import inject_navbar

import pages.overview     as _overview
import pages.banks        as _banks
import pages.flows        as _flows
import pages.simulator    as _simulator

st.set_page_config(
    page_title="Treasury · Cash Management",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="collapsed"
)

def _load_css(path: str) -> None:
    """Lit un fichier .css et l'injecte dans le <head> de la page via st.markdown."""
    try:
        st.markdown(f"<style>{Path(path).read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    except:
        pass

_load_css("assets/base.css")
_load_css("assets/components.css")

get_db()
_init_config()

page, now = inject_navbar()

if page == "Vue d'ensemble":
    _overview.render(now)
elif page == "Banques & Comptes":
    _banks.render(now)
elif page == "Flux & Factures":
    _flows.render(now)
elif page == "Scenario Simulator":
    _simulator.render(now)

st.markdown("---")
st.caption("Treasury Dashboard v5.0 · Streamlit & Excel")
