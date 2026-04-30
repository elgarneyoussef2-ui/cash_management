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
- **Streamlit** : Framework pour l'interface utilisateur web.
- **Pandas** : Manipulation et analyse de données.
- **Openpyxl** : Lecture/Écriture des fichiers Excel.
- **Plotly** : Visualisations de données interactives.

## ⚙️ Installation

1.  **Cloner le dépôt** :
    ```bash
    git clone https://github.com/elgarneyoussef2-ui/cash_management.git
    cd cash_management
    ```

2.  **Créer un environnement virtuel** (recommandé) :
    ```bash
    python -m venv venv
    source venv/bin/activate  # Sur Windows: venv\Scripts\activate
    ```

3.  **Installer les dépendances** :
    ```bash
    pip install streamlit pandas openpyxl plotly
    ```

## 📖 Utilisation

Pour lancer le dashboard, exécutez la commande suivante à la racine du projet :

```bash
streamlit run dashboard.py
```

L'application sera accessible dans votre navigateur à l'adresse `http://localhost:8501`.

## 📊 Données

L'application utilise le fichier `treasury_master.xlsx` comme source de vérité. Assurez-vous que ce fichier est présent à la racine pour que le dashboard puisse charger les données.

---
*Treasury Dashboard v5.0 · Développé avec Streamlit & Excel*
