"""
Application Streamlit - FUSION : Fusionneur Excel avec Déduplication Intelligente.
Thème moderne LinkedIn (#0A66C2), KPIs en direct, visualisations Plotly et export stylisé.
"""

import io
import time
from datetime import datetime
import pandas as pd
import plotly.express as px
import streamlit as st

from core.logger import setup_logger, log_buffer
from core.file_reader import read_excel_files, EXPECTED_COLUMNS
from core.deduplicator import deduplicate_contacts, filter_contacts
from core.exporter import export_to_excel, generate_export_filename

# Initialisation du logger
logger = setup_logger()

# Configuration Streamlit
st.set_page_config(
    page_title="FUSION — Déduplication & Fusion Excel",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Injection de styles CSS personnalisés (Charte LinkedIn & Dark/Light Modern)
st.markdown("""
<style>
    /* Variables de charte */
    :root {
        --primary-blue: #0A66C2;
        --primary-hover: #004182;
        --secondary-blue: #70B5F9;
        --bg-light: #F3F6F8;
        --card-bg: #FFFFFF;
        --text-dark: #191919;
        --success-green: #057642;
        --warning-orange: #E68A00;
        --error-red: #B92B27;
    }

    /* Style global */
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        color: #0A66C2;
        margin-bottom: 0.2rem;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #5E5E5E;
        margin-bottom: 1.8rem;
    }

    /* Cartes KPI */
    .kpi-container {
        display: flex;
        gap: 16px;
        margin-bottom: 24px;
    }
    .kpi-card {
        background: #FFFFFF;
        border-radius: 12px;
        padding: 18px 20px;
        border: 1px solid #E0E0E0;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
        flex: 1;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(10, 102, 194, 0.12);
        border-color: #70B5F9;
    }
    .kpi-label {
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #666666;
        font-weight: 600;
    }
    .kpi-value {
        font-size: 1.8rem;
        font-weight: 800;
        color: #0A66C2;
        margin-top: 4px;
    }
    .kpi-sub {
        font-size: 0.8rem;
        color: #888888;
        margin-top: 2px;
    }

    /* Bouton principal personnalisé */
    div.stButton > button:first-child {
        background-color: #0A66C2 !0important;
        color: white !important;
        font-size: 1.1rem !important;
        font-weight: 700 !important;
        border-radius: 8px !important;
        padding: 0.6rem 2rem !important;
        border: none !important;
        box-shadow: 0 4px 10px rgba(10, 102, 194, 0.3) !important;
        transition: all 0.3s ease !important;
    }
    div.stButton > button:first-child:hover {
        background-color: #004182 !important;
        box-shadow: 0 6px 14px rgba(10, 102, 194, 0.45) !important;
        transform: translateY(-1px);
    }

    /* Console de logs */
    .log-box {
        background-color: #1E1E1E;
        color: #D4D4D4;
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 0.85rem;
        padding: 14px 16px;
        border-radius: 8px;
        max-height: 240px;
        overflow-y: auto;
        border: 1px solid #333333;
        line-height: 1.5;
    }
    .log-info { color: #70B5F9; }
    .log-warning { color: #E68A00; }
    .log-error { color: #FF6B6B; }
    .log-time { color: #888888; margin-right: 8px; }

    /* Fichiers uploadés badge */
    .file-badge {
        display: inline-block;
        background: #EBF4FC;
        color: #0A66C2;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
        margin: 4px 4px 4px 0;
        border: 1px solid #C2E0FF;
    }
</style>
""", unsafe_allow_html=True)

# Initialisation du session_state
if "raw_df" not in st.session_state:
    st.session_state.raw_df = None
if "dedup_df" not in st.session_state:
    st.session_state.dedup_df = None
if "stats" not in st.session_state:
    st.session_state.stats = None
if "excel_buffer" not in st.session_state:
    st.session_state.excel_buffer = None
if "export_filename" not in st.session_state:
    st.session_state.export_filename = ""

def format_file_size(size_bytes: int) -> str:
    """Convertit une taille en octets en format lisible."""
    if size_bytes < 1024:
        return f"{size_bytes} o"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} Ko"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} Mo"

def reset_state():
    """Réinitialise tous les états de l'application."""
    st.session_state.raw_df = None
    st.session_state.dedup_df = None
    st.session_state.stats = None
    st.session_state.excel_buffer = None
    st.session_state.export_filename = ""
    log_buffer.clear()
    logger.info("Application réinitialisée par l'utilisateur.")

# --- SIDEBAR : FILTRES & CONFIGURATION ---
with st.sidebar:
    st.image("https://img.icons8.com/color/96/microsoft-excel-2019--v1.png", width=64)
    st.title("⚙️ Paramètres")
    
    st.markdown("### 🎯 Critères de Déduplication")
    st.info("""
    **Cascade Intelligente :**
    1. 🔗 **Lien LinkedIn** (priorité max)
    2. ✉️ **Email Proposé** (si LinkedIn absent)
    3. 👤 **Triplet Prénom + Nom + Entreprise**
    
    *Arbitrage : Meilleur score de confiance, complétude, et fusion des emails alternatifs.*
    """)

    st.markdown("---")
    st.markdown("### 🔍 Filtres Optionnels")
    
    filter_mx = st.multiselect(
        "Statut MX autorisé :",
        options=["Validé", "À vérifier", "Invalide"],
        default=["Validé", "À vérifier", "Invalide"],
        help="Filtrer les contacts selon la validité de leur serveur mail."
    )

    min_confidence = st.slider(
        "Score de Confiance min (%) :",
        min_value=0,
        max_value=100,
        value=0,
        step=5,
        help="Exclure les contacts sous un score de confiance spécifique."
    )

    st.markdown("---")
    if st.button("🗑️ Effacer tout et réinitialiser", use_container_width=True):
        reset_state()
        st.rerun()

# --- EN-TÊTE PRINCIPAL ---
st.markdown('<div class="main-title">⚡ FUSION — Déduplication Excel Intelligente</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Fusionnez vos exports LinkedIn Prospector (5 à 50 fichiers Excel), '
    'éliminez les doublons en cascade et générez un fichier unique propre et stylisé.</div>',
    unsafe_allow_html=True
)

# --- ZONE D'UPLOAD ---
st.markdown("### 📁 1. Importation des Fichiers Excel")
uploaded_files = st.file_uploader(
    "Glissez-déposez vos fichiers Excel ici (.xlsx, .xls) :",
    type=["xlsx", "xls"],
    accept_multiple_files=True,
    help="Sélectionnez de 1 à 50 fichiers Excel avec la même structure de colonnes."
)

if uploaded_files:
    # Affichage des badges de fichiers avec leur taille
    st.markdown(f"**{len(uploaded_files)} fichier(s) sélectionné(s) :**")
    file_badges_html = "<div>"
    total_size = 0
    for f in uploaded_files:
        total_size += f.size
        file_badges_html += f'<span class="file-badge">📄 {f.name} ({format_file_size(f.size)})</span>'
    file_badges_html += f'<span class="file-badge" style="background:#E2F0D9; color:#057642; border-color:#A9D08E;">📦 Total: {format_file_size(total_size)}</span></div>'
    st.markdown(file_badges_html, unsafe_allow_html=True)
    st.markdown("")

    # Bouton d'action principal
    col_btn, col_empty = st.columns([2, 3])
    with col_btn:
        start_processing = st.button("🚀 Fusionner et Dédupliquer", use_container_width=True)

    if start_processing:
        progress_bar = st.progress(0, text="Initialisation de la fusion...")
        time.sleep(0.1)

        # 1. Lecture
        progress_bar.progress(25, text="Lecture et validation des fichiers Excel...")
        raw_df, count_files, total_raw = read_excel_files(uploaded_files)
        st.session_state.raw_df = raw_df

        if not raw_df.empty:
            # 2. Déduplication
            progress_bar.progress(60, text="Application de la déduplication intelligente en cascade...")
            dedup_df, stats = deduplicate_contacts(raw_df)
            
            # 3. Export Excel stylisé
            progress_bar.progress(85, text="Stylisation du classeur Excel (openpyxl)...")
            export_name = generate_export_filename()
            excel_buffer = export_to_excel(dedup_df)

            st.session_state.dedup_df = dedup_df
            st.session_state.stats = stats
            st.session_state.excel_buffer = excel_buffer
            st.session_state.export_filename = export_name

            progress_bar.progress(100, text="Traitement terminé avec succès !")
            time.sleep(0.5)
            progress_bar.empty()
            st.success(f"🎉 Fusion terminée avec succès ! {stats['duplicates_removed']} doublons éliminés.")

# --- RÉSULTATS & STATISTIQUES ---
if st.session_state.dedup_df is not None and st.session_state.stats is not None:
    df_result = st.session_state.dedup_df
    stats = st.session_state.stats

    # Application des filtres interactifs
    companies = sorted([str(c) for c in df_result["Entreprise"].dropna().unique() if str(c).strip()])
    selected_companies = st.sidebar.multiselect(
        "Filtrer par Entreprise(s) :",
        options=companies,
        default=[],
        help="Laissez vide pour afficher toutes les entreprises."
    )

    filtered_view_df = filter_contacts(
        df_result,
        mx_status=filter_mx if filter_mx else None,
        min_confidence=min_confidence,
        selected_companies=selected_companies if selected_companies else None
    )

    st.markdown("---")
    st.markdown("### 📊 2. Statistiques et KPIs de Fusion")

    # Affichage des cartes KPI
    kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5 = st.columns(5)
    
    with kpi_col1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Fichiers Traités</div>
            <div class="kpi-value">{len(uploaded_files) if uploaded_files else 1}</div>
            <div class="kpi-sub">Source Excel</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi_col2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Lignes Brutes</div>
            <div class="kpi-value">{stats['initial_rows']:,}</div>
            <div class="kpi-sub">Total avant dédup</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi_col3:
        st.markdown(f"""
        <div class="kpi-card" style="border-left: 4px solid #B92B27;">
            <div class="kpi-label">Doublons Supprimés</div>
            <div class="kpi-value" style="color: #B92B27;">{stats['duplicates_removed']:,}</div>
            <div class="kpi-sub">Taux : {stats['dedup_rate_pct']}%</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi_col4:
        st.markdown(f"""
        <div class="kpi-card" style="border-left: 4px solid #057642;">
            <div class="kpi-label">Contacts Uniques</div>
            <div class="kpi-value" style="color: #057642;">{stats['final_rows']:,}</div>
            <div class="kpi-sub">Base dédupliquée</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi_col5:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Contacts Filtrés</div>
            <div class="kpi-value">{len(filtered_view_df):,}</div>
            <div class="kpi-sub">Vue active</div>
        </div>
        """, unsafe_allow_html=True)

    # Détails des critères de déduplication
    st.markdown("")
    col_d1, col_d2, col_d3 = st.columns(3)
    col_d1.info(f"🔗 **Doublons LinkedIn :** {stats['dedup_by_linkedin']}")
    col_d2.info(f"✉️ **Doublons Email :** {stats['dedup_by_email']}")
    col_d3.info(f"👤 **Doublons Triplet :** {stats['dedup_by_triplet']}")

    # Graphiques d'analyse
    st.markdown("---")
    st.markdown("### 📈 3. Visualisations Graphiques")
    
    chart_col1, chart_col2 = st.columns([3, 2])

    with chart_col1:
        # Top 10 Entreprises
        if "Entreprise" in filtered_view_df.columns and not filtered_view_df.empty:
            top_companies = filtered_view_df["Entreprise"].value_counts().head(10).reset_index()
            top_companies.columns = ["Entreprise", "Nombre de Contacts"]
            fig_bar = px.bar(
                top_companies,
                x="Nombre de Contacts",
                y="Entreprise",
                orientation="h",
                title="🏢 Top 10 des Entreprises Représentées",
                color="Nombre de Contacts",
                color_continuous_scale=["#70B5F9", "#0A66C2"],
            )
            fig_bar.update_layout(
                yaxis=dict(autorange="reversed"),
                margin=dict(l=20, r=20, t=40, b=20),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                height=350,
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    with chart_col2:
        # Répartition Statut MX
        if "Statut MX" in filtered_view_df.columns and not filtered_view_df.empty:
            mx_counts = filtered_view_df["Statut MX"].value_counts().reset_index()
            mx_counts.columns = ["Statut MX", "Total"]
            colors_map = {"Validé": "#057642", "À vérifier": "#E68A00", "Invalide": "#B92B27"}
            fig_pie = px.pie(
                mx_counts,
                names="Statut MX",
                values="Total",
                title="🛡️ Répartition du Statut MX",
                hole=0.45,
                color="Statut MX",
                color_discrete_map=colors_map
            )
            fig_pie.update_layout(
                margin=dict(l=20, r=20, t=40, b=20),
                paper_bgcolor="rgba(0,0,0,0)",
                height=350,
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    # --- APERÇU INTERACTIF DU TABLEAU ---
    st.markdown("---")
    st.markdown("### 📋 4. Aperçu des Données Dédupliquées")

    col_search, col_dl = st.columns([3, 1])
    with col_search:
        search_query = st.text_input("🔍 Recherche rapide (nom, entreprise, email...) :", "")
    
    with col_dl:
        # Bouton de téléchargement Excel stylisé
        if st.session_state.excel_buffer is not None:
            # Si des filtres sont actifs, regénérer l'export sur la sélection si différente
            if len(filtered_view_df) != len(df_result):
                download_buffer = export_to_excel(filtered_view_df)
            else:
                download_buffer = st.session_state.excel_buffer

            st.download_button(
                label="📥 Télécharger l'Excel Fusionné",
                data=download_buffer,
                file_name=st.session_state.export_filename or "contacts_fusionnes.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

    display_df = filtered_view_df.copy()
    if search_query:
        mask = display_df.astype(str).apply(lambda row: row.str.contains(search_query, case=False, na=False).any(), axis=1)
        display_df = display_df[mask]

    # Colonnes à afficher proprement
    cols_to_show = [c for c in EXPECTED_COLUMNS if c in display_df.columns]
    st.dataframe(
        display_df[cols_to_show],
        use_container_width=True,
        hide_index=True,
        height=400,
    )
    st.caption(f"Affichage de {len(display_df)} contacts sur {len(filtered_view_df)}.")

# --- CONSOLE DE LOGS EN TEMPS RÉEL ---
st.markdown("---")
with st.expander("📜 Console des Logs en Temps Réel", expanded=True):
    logs = log_buffer.get_logs()
    if logs:
        log_lines_html = []
        for entry in logs[-50:]:  # Dernières 50 lignes
            lvl = entry["level"]
            cls_name = "log-info" if lvl == "INFO" else ("log-warning" if lvl == "WARNING" else "log-error")
            time_str = entry["timestamp"]
            raw = entry["message"].replace("<", "&lt;").replace(">", "&gt;")
            log_lines_html.append(f'<div><span class="log-time">[{time_str}]</span><span class="{cls_name}">[{lvl}]</span> {raw}</div>')
        
        st.markdown(f'<div class="log-box">{"".join(log_lines_html)}</div>', unsafe_allow_html=True)
    else:
        st.info("Aucun log généré pour le moment. Déposez des fichiers et lancez la fusion.")
