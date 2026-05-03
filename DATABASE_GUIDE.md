# 📖 Guide de la Base de Données (Excel)

Ce document détaille la structure du fichier `treasury_master.xlsx`, l'utilité de chaque colonne et leur utilisation dans l'application Treasury Dashboard.

---

## 🏦 Table : `banks`
Définit les établissements bancaires partenaires.

| Colonne | Description | Utilisation dans l'App |
| :--- | :--- | :--- |
| `bank_id` | Identifiant unique de la banque | Clé de jointure principale (utilisée partout) |
| `bank_code` | Code court (ex: BNP, SG) | Affichage compact dans les tableaux |
| `bank_name` | Nom complet de la banque | Titres des graphiques et sélecteurs |
| `bic_swift` | Code SWIFT/BIC | Utilisé pour identifier les transferts cross-bank |
| `country` | Pays de la banque | Analyse de risque géographique |
| `is_active` | État d'activité (1=Oui, 0=Non) | Filtrage des banques dans les menus |

---

## 💳 Table : `accounts`
Détaille les comptes bancaires rattachés aux banques.

| Colonne | Description | Utilisation dans l'App |
| :--- | :--- | :--- |
| `account_id` | Identifiant unique du compte | Jointure avec les soldes et transactions |
| `bank_id` | ID de la banque parente | Jointure pour récupérer le nom de la banque |
| `account_number` | Numéro de compte / IBAN | Affichage dans les détails de comptes |
| `account_type` | Type (CURRENT, SAVINGS, etc.) | Segmentation dans les rapports |
| `currency` | Devise du compte (EUR, SEK, PLN) | Détermine le besoin de conversion FX |

---

## 📊 Table : `daily_account_balances`
Historique des soldes quotidiens.

| Colonne | Description | Utilisation dans l'App |
| :--- | :--- | :--- |
| `account_id` | ID du compte concerné | Jointure |
| `date` | Date du relevé | Axe temporel des graphiques d'évolution |
| `book_balance` | Solde comptable (devise locale) | Affichage du solde réel par compte |
| `balance_eur` | Contre-valeur en EUR au jour J | **Colonne critique** pour tous les KPIs consolidés |

---

## ⚙️ Table : `daily_bank_conditions`
Conditions financières négociées par banque et par jour.

| Colonne | Description | Utilisation dans l'App |
| :--- | :--- | :--- |
| `bank_id` | ID de la banque | Jointure |
| `date` | Date d'application | Récupération des conditions les plus récentes |
| `counterparty_limit_eur` | Limite d'exposition max (€) | Calcul du plafond de risque (Overview/Simulator) |
| `cutoff_overnight` | Heure limite virement J+1 | Alertes et validation dans le Simulator |
| `cutoff_mmf` | Heure limite placement OPCVM | Validation des ordres de placement |
| `od_rate` | Taux de découvert négocié | Calcul des agios prévisionnels |
| `invest_rate` | Taux de placement par défaut | Calcul du rendement théorique |
| `fx_eur_sek` / `pln` / `usd` | Taux de change du jour | **Source de vérité** pour toutes les conversions EUR |
| `estr_rate` | Taux ESTR du jour | Calcul du spread vs marché (Simulator) |

---

## 📝 Table : `transactions`
Flux réels passés sur les comptes.

| Colonne | Description | Utilisation dans l'App |
| :--- | :--- | :--- |
| `account_id` | ID du compte | Jointure |
| `date` | Date de l'opération | Filtrage par mois/période |
| `category` | Catégorie (OPEX, REVENUE, etc.) | Analyse des flux par nature |
| `type` | Sens du flux (IN / OUT) | Calcul du Cash Flow Net |
| `amount_eur` | Montant converti en EUR | Sommes consolidées dans la page "Flux" |

---

## 🔮 Table : `forecasts`
Prévisions de trésorerie pour les jours à venir.

| Colonne | Description | Utilisation dans l'App |
| :--- | :--- | :--- |
| `forecast_date` | Date prévue du flux | Axe temporel du graphique "Cash Flow Prévisionnel" |
| `type` | Sens (IN / OUT) | Couleurs des barres (Vert=IN, Rouge=OUT) |
| `amount` | Montant prévu | Calcul de la position nette cumulée |

---

## 📄 Table : `invoices`
Factures clients et fournisseurs en attente.

| Colonne | Description | Utilisation dans l'App |
| :--- | :--- | :--- |
| `invoice_type` | CUSTOMER / SUPPLIER | Calcul du BFR (Besoin en Fonds de Roulement) |
| `amount_ttc` | Montant de la facture | Calcul du DSO et DPO |
| `due_date` | Date d'échéance | Alertes de retard et échéancier (Page Flux) |
| `status` | État (PENDING, PAID) | Filtrage pour ne garder que l'encours |

---

## 👁️ Feuilles de Vues (`v_...`)
Ces feuilles sont des vues consolidées (calculées ou simulées) utilisées pour simplifier le code Streamlit.
- `v_today_negotiations` : Synthèse des conditions et soldes pour la page Simulation.
- `v_banking_positions` : Agrégation des soldes par banque pour le graphique de l'Overview.
- `v_bank_cash_rates` : Liste plate des taux pour le Ticker (bandeau défilant).
