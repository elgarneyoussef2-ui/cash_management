import streamlit as st  # type: ignore
import pandas as pd  # type: ignore
import os
from datetime import datetime

# Constante pour le fichier Excel maître
EXCEL_DB_PATH = "treasury_master.xlsx"

@st.cache_resource
def get_db():
    """
    Simule une connexion à une base de données en chargeant le fichier Excel.
    Retourne un dictionnaire de DataFrames indexé par le nom de la feuille (table).
    """
    if not os.path.exists(EXCEL_DB_PATH):
        st.error(f"Fichier de base de données Excel introuvable : {EXCEL_DB_PATH}")
        return {}
    
    # Chargement de toutes les feuilles Excel en cache
    return pd.read_excel(EXCEL_DB_PATH, sheet_name=None)

def get_table(name: str) -> pd.DataFrame:
    """
    Récupère une table (feuille Excel) directement par son nom.
    """
    db = get_db()
    name = name.lower()
    if name in db:
        return db[name].copy()
    return pd.DataFrame()
