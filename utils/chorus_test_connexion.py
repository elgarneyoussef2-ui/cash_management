"""Script de test rapide pour valider la connexion Chorus Pro."""
import json
import os
from utils.chorus_client import fetch_factures_fournisseur, fetch_factures_recipiendaire

LOGIN    = os.environ.get("CHORUS_LOGIN",    "")
PASSWORD = os.environ.get("CHORUS_PASSWORD", "")
DATE_DU  = "2020-01-01"
DATE_AU  = "2026-12-31"

if not LOGIN or not PASSWORD:
    print("⚠  Définissez CHORUS_LOGIN et CHORUS_PASSWORD en variables d'environnement.")
    exit(1)

print("\n── Factures fournisseur (émises) ──")
try:
    fac = fetch_factures_fournisseur(LOGIN, PASSWORD, DATE_DU, DATE_AU)
    print(f"✅ {len(fac)} facture(s)")
    if fac:
        print(json.dumps(fac[0], indent=2, ensure_ascii=False))
except Exception as e:
    print(f"❌ {e}")

print("\n── Factures recipiendaire (reçues) ──")
try:
    rec = fetch_factures_recipiendaire(LOGIN, PASSWORD, DATE_DU, DATE_AU)
    print(f"✅ {len(rec)} facture(s)")
    if rec:
        print(json.dumps(rec[0], indent=2, ensure_ascii=False))
except Exception as e:
    print(f"❌ {e}")
