# 💰 Treasury · Cash Management Dashboard

Un tableau de bord complet pour la gestion de trésorerie et le cash management, conçu pour offrir une visibilité en temps réel sur les positions bancaires, les flux de trésorerie et les prévisions financières.

## 🚀 Fonctionnalités Clés

Le dashboard est divisé en quatre modules principaux :

1.  **Vue d'ensemble (Overview)** : 
    - Indicateurs clés de performance (KPI) : Solde total, Liquidité nette, Position de cash.
    - Graphiques d'évolution des soldes.
    - Alertes sur les seuils de découvert.

2.  **Banques & Comptes** :
    - Gestion détaillée des comptes bancaires par établissement.
    - Suivi des conditions bancaires (taux de découvert, taux de placement, taux de change FX).
    - Répartition géographique et par devise des actifs.

3.  **Flux & Factures** :
    - Visualisation des entrées et sorties de fonds.
    - Gestion des factures fournisseurs et clients.
    - Analyse des flux par catégorie et par entité.

4.  **Scenario Simulator** :
    - Outil de simulation puissant pour tester l'impact de différents scénarios financiers.
    - Ajustement des taux, des délais de paiement et des investissements.
    - Comparaison instantanée avec les prévisions actuelles.

## 🧠 Logique Métier & Calculs Financiers

Cette section détaille les concepts financiers et les formules de calcul utilisés dans l'application.

### 1. Gestion de la Liquidité (Overview)
- **Position de Cash Brute** : Somme de tous les soldes bancaires convertis en EUR.
- **Surplus de Trésorerie** : Somme uniquement des soldes positifs. C'est la ressource disponible pour le placement.
- **Risque de Découvert (Overdraft)** : Somme des soldes négatifs. Représente l'utilisation des lignes de crédit et génère des frais financiers.
- **Conversion Devise (FX)** : Tous les calculs sont ramenés en EUR en utilisant les taux de change du jour (spot rates) stockés dans `daily_bank_conditions`.

### 2. Analyse du BFR (Flux & Factures)
Le dashboard calcule des indicateurs clés du Besoin en Fonds de Roulement (BFR) :
- **DSO (Days Sales Outstanding)** : Délai moyen de paiement client.
  - *Calcul* : `(Créances Clients * 30) / Chiffre d'Affaires du mois`.
- **DPO (Days Payables Outstanding)** : Délai moyen de paiement fournisseur.
  - *Calcul* : `(Dettes Fournisseurs * 30) / Achats du mois`.
- **BFR Net** : `Créances Clients - Dettes Fournisseurs`.

### 3. Simulation et Optimisation (Simulator)
Le simulateur permet de projeter des décisions de trésorerie :
- **Cash Pooling (ZBA - Zero Balance Account)** :
  - Simulation de remontées de fonds (Sweeps) vers un compte pivot.
  - Calcul automatique des frais de transfert SWIFT (appliqués sur les transferts transfrontaliers).
- **Optimisation des Placements** :
  - Comparaison des rendements sur différents instruments : Overnight (J+1), DAT (Dépôt à Terme) 1M/3M/6M.
  - Prise en compte des **Cut-offs horaires** : L'application vérifie si l'heure limite de transaction bancaire est dépassée pour valider la faisabilité d'une opération le jour même.
- **Calcul des Intérêts** :
  - *Formule* : `Montant * Taux * (Nombre de jours / 365)`.

## 📁 Structure du Projet

```text
├── assets/             # Fichiers CSS personnalisés
├── components/         # Composants UI réutilisables (ex: Navbar)
├── db/                 # Gestion de la "base de données" (Excel)
├── pages/              # Les différentes pages de l'application Streamlit
├── utils/              # Fonctions utilitaires, config et calculs financiers
├── dashboard.py        # Point d'entrée principal de l'application
├── treasury_master.xlsx # Base de données Excel source
└── pyrightconfig.json  # Configuration du typage Python
```

## 🛠️ Technologies Utilisées

- **Python 3.10+**
- **Streamlit** : Interface utilisateur web.
- **Pandas** : Moteur de calcul et manipulation de données.
- **Openpyxl** : Interface avec la base de données Excel.
- **Plotly** : Graphiques financiers interactifs.

## 🔗 Intégration Chorus Pro (Sandbox)

Le dashboard supporte désormais la synchronisation native avec **Chorus Pro** via la plateforme PISTE.

### Configuration
1. Obtenez vos identifiants sur [PISTE](https://piste.gouv.fr/).
2. Dans la page **Flux & Factures**, onglet **API / ERP**, sélectionnez **Chorus Pro (Sandbox)**.
3. Renseignez votre `Client ID`, `Client Secret` et `SIRET`.
4. Cliquez sur **Synchroniser** pour importer automatiquement vos factures reçues.

*Note : En mode Sandbox, si aucune facture n'est présente, le système propose des données de démonstration cohérentes.*

## ⚙️ Installation & Utilisation

1. **Installation** :
   ```bash
   pip install streamlit pandas openpyxl plotly
   ```

2. **Lancement** :
   ```bash
   streamlit run dashboard.py
   ```

---
*Treasury Dashboard v5.0 · Expertise Trésorerie & Data*
