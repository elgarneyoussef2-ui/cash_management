# =============================================================================
# components/navbar.py — Barre de navigation et en-tête de page
#
# Ce module gère deux responsabilités :
#   1. inject_navbar() : construit le HTML de la topnav, l'injecte dans le DOM
#      parent Streamlit via un iframe JS, et retourne la page active + l'heure.
#   2. page_header()   : affiche l'en-tête de chaque page (titre, sous-titre,
#      date, bouton d'export optionnel) en lisant la page courante depuis les
#      variables globales du module.
#
# Importé par : dashboard.py (inject_navbar), toutes les pages (page_header)
# =============================================================================

import streamlit as st  # type: ignore
import streamlit.components.v1 as _stc  # Pour injecter du HTML/JS hors du rendu Streamlit
from datetime import datetime

# ── Table de correspondance slug URL → nom de page complet ───────────────────
# Le slug est le paramètre ?p=<slug> utilisé dans l'URL pour identifier la page.
# Exemple : ?p=banks → "Banques & Comptes"
_NAV_SLUGS = {
    "overview":    "Vue d'ensemble",
    "banks":       "Banques & Comptes",
    "flows":       "Flux & Factures",
    "simulator":   "Scenario Simulator",
}

# ── Icônes emoji associées à chaque slug (affichées dans la navbar) ───────────
_NAV_ICONS_MAP = {
    "overview":    "📊", "banks":    "🏦", "flows":   "📝",
    "simulator": "⚡",
}

# ── Métadonnées d'en-tête pour chaque page ───────────────────────────────────
# Chaque entrée : page_name → (label_affiché, sous-titre_descriptif)
# Utilisé par page_header() pour afficher l'en-tête spécifique à la page.
_PAGE_ICONS = {
    "Vue d'ensemble":         ("Vue d'ensemble",              "Consolidated treasury position & KPIs"),
    "Banques & Comptes":      ("Banques & Comptes",           "Account positions, rates & spreads"),
    "Flux & Factures":        ("Flux & Factures",             "Invoice management & cash flow analysis"),
    "Scenario Simulator":     ("Scenario Simulator",          "Simulate pooling, transfers & investments"),
}

# ── État du module mis à jour à chaque re-run Streamlit ──────────────────────
# Ces variables globales sont écrasées par inject_navbar() à chaque exécution.
# page_header() les lit ensuite pour connaître la page et l'heure courantes.
_current_page: str = "Vue d'ensemble"
_current_now: datetime = datetime.now()


def _nav_link(slug: str, active_slug: str) -> str:
    """
    Génère le HTML d'un lien de navigation pour la barre desktop.

    Applique la classe CSS `tnav-active` et l'attribut `aria-current`
    si le slug correspond à la page actuellement affichée.
    Le lien pointe vers `?p=<slug>` pour changer de page sans rechargement complet.
    """
    label  = _NAV_SLUGS[slug]
    icon   = _NAV_ICONS_MAP[slug]
    active = " tnav-active" if slug == active_slug else ""
    ac     = ' aria-current="page"' if slug == active_slug else ""
    return (
        f'<a class="tnav-link{active}" href="?p={slug}" role="menuitem"{ac} aria-label="{label}">'
        f'<span aria-hidden="true">{icon}</span>'
        f'<span class="tnav-lbl">{label}</span>'
        f'</a>'
    )


def _mob_link(slug: str, active_slug: str) -> str:
    """
    Génère le HTML d'un lien de navigation pour le menu mobile déroulant.

    Version simplifiée de _nav_link() sans aria-label (redondant sur mobile).
    Utilisé dans le menu hamburger affiché en dessous de la barre principale.
    """
    label  = _NAV_SLUGS[slug]
    icon   = _NAV_ICONS_MAP[slug]
    active = " tnav-active" if slug == active_slug else ""
    ac     = ' aria-current="page"' if slug == active_slug else ""
    return (
        f'<a class="tnav-mob-link{active}" href="?p={slug}" role="menuitem"{ac}>'
        f'<span aria-hidden="true">{icon}</span>{label}'
        f'</a>'
    )


def inject_navbar() -> tuple:
    """
    Construit et injecte la barre de navigation dans le DOM parent Streamlit.

    Étapes :
      1. Lit le paramètre URL ?p=<slug> (défaut: "overview") pour identifier la page
      2. Génère les liens desktop et mobile avec la page active surlignée
      3. Assemble le HTML complet de la navbar (marque, liens, date/heure, LIVE badge)
      4. Échappe les backticks et ${} pour éviter les conflits avec les template literals JS
      5. Injecte via _stc.html() un script JS qui :
           - Supprime l'ancienne navbar si elle existe (re-runs Streamlit)
           - Insère la nouvelle navbar au début du container Streamlit
           - Câble le menu hamburger (toggle open/close, Escape, clic extérieur)
      6. Met à jour _current_page et _current_now pour que page_header() puisse les lire

    Returns:
        tuple: (_current_page: str, _current_now: datetime)
    """
    global _current_page, _current_now

    # Capture le timestamp du re-run (affiché dans la navbar et les en-têtes)
    _current_now = datetime.now()

    # Lecture du slug depuis les query params URL (?p=<slug>)
    try:
        slug = st.query_params.get("p", "overview")
    except Exception:
        slug = "overview"
    if slug not in _NAV_SLUGS:
        slug = "overview"
    _current_page = _NAV_SLUGS[slug]

    # Construction des blocs de liens HTML (desktop + mobile)
    desktop_links = "".join(_nav_link(s, slug) for s in _NAV_SLUGS)
    mobile_links  = "".join(_mob_link(s, slug)  for s in _NAV_SLUGS)

    # Assemblage du HTML complet de la navbar :
    #   - Marque (logo + nom) cliquable → retour à overview
    #   - Liens de navigation desktop
    #   - Zone droite : date/heure + badge LIVE + bouton hamburger mobile
    #   - Menu mobile déroulant (#tnav-mob)
    nav_html = (
        '<div id="tnav">'
          '<div class="tnav-inner">'
            '<a class="tnav-brand" href="?p=overview" aria-label="Accueil Treasury Dashboard">'
              '<div class="tnav-brand-icon" aria-hidden="true">\U0001f3e6</div>'
              '<div class="tnav-brand-text">'
                '<div class="tnav-brand-name">TREASURY</div>'
                '<div class="tnav-brand-sub">Smart Dashboard</div>'
              '</div>'
            '</a>'
            f'<div class="tnav-links" role="menubar" aria-label="Pages principales">{desktop_links}</div>'
            '<div class="tnav-right">'
              f'<div class="tnav-datetime" aria-label="Date et heure">'
                f'<span class="tnav-date">{_current_now.strftime("%d.%m.%Y")}</span>'
                f'<span class="tnav-time">{_current_now.strftime("%H:%M")}</span>'
              '</div>'
              # Badge "LIVE" vert pulsant (indicateur de données temps-réel)
              '<div style="display:flex;align-items:center;gap:6px;margin-left:8px;padding:3px 10px;border-radius:20px;background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.2)">'
                '<span style="width:6px;height:6px;border-radius:50%;background:#10B981;box-shadow:0 0 6px rgba(16,185,129,0.5);flex-shrink:0"></span>'
                '<span style="font-size:0.62rem;color:#6EE7B7;font-weight:700;letter-spacing:0.06em">LIVE</span>'
              '</div>'
              # Bouton hamburger (3 barres) pour déclencher le menu mobile
              '<div id="tnav-ham" class="tnav-hamburger" role="button" tabindex="0" aria-expanded="false" aria-controls="tnav-mob" aria-label="Ouvrir le menu">'
                '<span class="tnav-ham-bar" aria-hidden="true"></span>'
                '<span class="tnav-ham-bar" aria-hidden="true"></span>'
                '<span class="tnav-ham-bar" aria-hidden="true"></span>'
              '</div>'
            '</div>'
          '</div>'
          # Menu mobile déroulant (caché par défaut, visible avec la classe tnav-mob-open)
          f'<div id="tnav-mob" class="tnav-mob" role="menu" aria-label="Menu mobile" aria-hidden="true">'
            '<div class="tnav-mob-meta">Navigation</div>'
            f'{mobile_links}'
            '<div class="tnav-mob-divider"></div>'
            f'<div style="padding:6px 16px 4px"><span style="font-size:0.62rem;color:#64748B">'
            f'{_current_now.strftime("%d.%m.%Y")} · {_current_now.strftime("%H:%M")}</span></div>'
          '</div>'
        '</div>'
    )

    # Échappement des caractères spéciaux avant injection dans un template literal JS
    # (les backticks et ${} sont interprétés par JS et casseraient le HTML)
    nav_esc = nav_html.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${')

    # Injection via un iframe Streamlit (height=0 = invisible) contenant le script JS.
    # Le script accède au DOM parent (window.parent.document) pour placer la navbar
    # en dehors du container Streamlit qui serait sinon scrollable avec la page.
    _stc.html(f"""
<script>
(function () {{
  try {{
    var doc = (window.parent || window).document;
    // Supprime l'ancienne navbar (présente lors des re-runs Streamlit)
    var old = doc.getElementById('tnav');
    if (old) old.remove();
    // Crée la nouvelle navbar depuis le HTML généré en Python
    var tmp = doc.createElement('div');
    tmp.innerHTML = `{nav_esc}`;
    var nav = tmp.firstElementChild;
    // Insère au début du container principal Streamlit (ou du body en fallback)
    var root = doc.querySelector('[data-testid="stAppViewContainer"]') || doc.body;
    root.insertBefore(nav, root.firstChild);
    // Câblage du menu hamburger : toggle, Escape, clic extérieur
    var ham = doc.getElementById('tnav-ham');
    var mob = doc.getElementById('tnav-mob');
    if (ham && mob) {{
      function toggle(open) {{
        if (open === undefined) open = !mob.classList.contains('tnav-mob-open');
        mob.classList.toggle('tnav-mob-open', open);
        ham.classList.toggle('tnav-ham-open', open);
        ham.setAttribute('aria-expanded', String(open));
        mob.setAttribute('aria-hidden',   String(!open));
      }}
      ham.addEventListener('click', function () {{ toggle(); }});
      ham.addEventListener('keydown', function (e) {{
        if (e.key === 'Enter' || e.key === ' ') {{ e.preventDefault(); toggle(); }}
      }});
      doc.addEventListener('keydown', function (e) {{
        if (e.key === 'Escape') {{ toggle(false); ham.focus(); }}
      }});
      doc.addEventListener('click', function (e) {{
        if (!nav.contains(e.target)) toggle(false);
      }});
    }}
  }} catch (err) {{
    console.warn('[tnav] inject failed:', err);
  }}
}})();
</script>
""", height=0)

    return _current_page, _current_now


def page_header(export_label: str = "", export_data: bytes = b"", export_name: str = "") -> None:
    """
    Affiche l'en-tête standardisé de la page active.

    Lit _current_page et _current_now (mis à jour par inject_navbar() juste avant
    l'appel de chaque page dans dashboard.py) pour afficher le titre et le sous-titre
    correspondant à la page en cours.

    Si export_label et export_data sont fournis, affiche un bouton de téléchargement
    CSV en haut à droite de l'en-tête (utilisé par certaines pages pour exporter
    leurs données).

    Args:
        export_label : Texte du bouton de téléchargement (ex: "⬇ Exporter CSV")
        export_data  : Contenu binaire du fichier à télécharger
        export_name  : Nom du fichier suggéré lors du téléchargement
    """
    # Récupère le label et le sous-titre depuis _PAGE_ICONS selon la page active
    label, subtitle = _PAGE_ICONS.get(_current_page, (_current_page, ""))
    header_html = (
        f'<div style="margin-bottom:6px">'
        f'<div style="font-size:1.35rem;font-weight:800;color:#0F172A;line-height:1.2">{label}</div>'
        f'<div style="font-size:0.78rem;color:#64748B;margin-top:2px">{subtitle}'
        f' &nbsp;·&nbsp; <span style="color:#1A56DB;font-weight:600">'
        f'{_current_now.strftime("%d %B %Y")}</span></div>'
        f'</div>'
    )
    if export_label and export_data:
        # Disposition 8/2 : titre à gauche, bouton de téléchargement à droite
        hcol1, hcol2 = st.columns([8, 2])
        with hcol1:
            st.markdown(header_html, unsafe_allow_html=True)
        with hcol2:
            st.markdown("<div style='padding-top:8px'>", unsafe_allow_html=True)
            st.download_button(export_label, export_data, export_name, "text/csv",
                               use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown(header_html, unsafe_allow_html=True)
    # Séparateur horizontal sous l'en-tête
    st.markdown('<hr style="margin:4px 0 16px">', unsafe_allow_html=True)
