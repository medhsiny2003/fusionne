"""
Application Streamlit - FUSION : Fusionneur Excel avec Déduplication Intelligente.
Préserve 100% des colonnes et données d'origine sans altération.
Confidentialité totale des données.
"""

import io
import time
import unicodedata
from datetime import datetime
import pandas as pd
import plotly.express as px
import streamlit as st

from core.logger import setup_logger, log_buffer
from core.file_reader import read_excel_files
from core.deduplicator import deduplicate_contacts, filter_contacts, detect_column_roles
from core.exporter import export_to_excel, generate_export_filename

# Initialisation du logger
logger = setup_logger()

# Configuration Streamlit
st.set_page_config(
    page_title="Fusion — Déduplication Excel",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Thème CSS moderne, minimaliste et professionnel
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Header principal */
    .hero-container {
        background: linear-gradient(135deg, #0A66C2 0%, #004182 100%);
        padding: 24px 30px;
        border-radius: 14px;
        color: white;
        margin-bottom: 24px;
        box-shadow: 0 4px 16px rgba(10, 102, 194, 0.15);
    }
    .hero-title {
        font-size: 1.8rem;
        font-weight: 700;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .hero-subtitle {
        font-size: 0.95rem;
        color: #E1E9F4;
        margin-top: 6px;
        font-weight: 400;
        line-height: 1.4;
    }

    /* Boîtes KPI */
    .metric-card {
        background: #FFFFFF;
        border-radius: 10px;
        padding: 16px 20px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        text-align: center;
    }
    .metric-title {
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        color: #64748B;
        font-weight: 600;
    }
    .metric-value {
        font-size: 1.9rem;
        font-weight: 700;
        color: #0F172A;
        margin: 4px 0;
    }
    .metric-footer {
        font-size: 0.78rem;
        color: #94A3B8;
    }

    /* Badges de fichiers */
    .file-chip {
        display: inline-flex;
        align-items: center;
        background: #F1F5F9;
        border: 1px solid #CBD5E1;
        border-radius: 20px;
        padding: 4px 12px;
        margin: 4px;
        font-size: 0.82rem;
        color: #334155;
        font-weight: 500;
    }

    /* Bouton principal */
    div.stButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease-in-out !important;
    }
    
    /* Console de logs */
    .terminal-console {
        background-color: #0F172A;
        color: #E2E8F0;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.82rem;
        padding: 14px;
        border-radius: 8px;
        max-height: 250px;
        overflow-y: auto;
        border: 1px solid #1E293B;
        line-height: 1.6;
    }
    .term-info { color: #38BDF8; }
    .term-warn { color: #FBBF24; }
    .term-err { color: #F87171; }
    .term-time { color: #64748B; margin-right: 6px; }
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
    """Réinitialise l'ensemble des données."""
    st.session_state.raw_df = None
    st.session_state.dedup_df = None
    st.session_state.stats = None
    st.session_state.excel_buffer = None
    st.session_state.export_filename = ""
    log_buffer.clear()

# --- HERO BANNER ---
st.markdown("""
<div class="hero-container">
    <div class="hero-title">⚡ FUSION &bull; Fusionneur Excel & Déduplication Intelligente</div>
    <div class="hero-subtitle">
        Fusionnez instantanément vos fichiers Excel en conservant <b>100% de vos colonnes et données d'origine</b> sans aucune perte.<br>
        Déduplication intelligente en cascade (LinkedIn &gt; Email &gt; Triplet) et export Excel stylisé.
    </div>
</div>
""", unsafe_allow_html=True)

# --- ZONE D'IMPORT ---
upload_col, action_col = st.columns([3, 1])

with upload_col:
    uploaded_files = st.file_uploader(
        "📁 Déposez vos fichiers Excel (.xlsx, .xls) :",
        type=["xlsx", "xls"],
        accept_multiple_files=True,
        help="Sélectionnez vos fichiers Excel. Toutes vos colonnes sont préservées à l'identique."
    )

with action_col:
    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    btn_process = st.button("🚀 Fusionner les fichiers", type="primary", use_container_width=True, disabled=not uploaded_files)
    btn_clear = st.button("🗑️ Réinitialiser", use_container_width=True, on_click=reset_state)

# Affichage des badges de fichiers
if uploaded_files:
    chips_html = '<div style="margin-bottom: 15px;">'
    total_size = 0
    for f in uploaded_files:
        total_size += f.size
        chips_html += f'<span class="file-chip">📄 {f.name} ({format_file_size(f.size)})</span>'
    chips_html += f'<span class="file-chip" style="background: #E0F2FE; border-color: #7DD3FC; color: #0369A1; font-weight: 600;">📦 {len(uploaded_files)} fichier(s) • {format_file_size(total_size)}</span></div>'
    st.markdown(chips_html, unsafe_allow_html=True)

# Traitement de fusion
if btn_process and uploaded_files:
    with st.spinner("Traitement et déduplication en cours..."):
        # 1. Lecture sans altération des colonnes
        raw_df, count_files, total_raw = read_excel_files(uploaded_files)
        st.session_state.raw_df = raw_df

        if not raw_df.empty:
            # 2. Déduplication intelligente
            dedup_df, stats = deduplicate_contacts(raw_df)
            
            # 3. Export Excel stylisé
            export_name = generate_export_filename()
            excel_buffer = export_to_excel(dedup_df)

            st.session_state.dedup_df = dedup_df
            st.session_state.stats = stats
            st.session_state.excel_buffer = excel_buffer
            st.session_state.export_filename = export_name
            
            st.toast("Fusion et déduplication terminées avec succès !", icon="✅")

# --- RÉSULTATS & VISUALISATIONS ---
if st.session_state.dedup_df is not None and st.session_state.stats is not None:
    df_result = st.session_state.dedup_df
    stats = st.session_state.stats
    roles = detect_column_roles(list(df_result.columns))

    st.markdown("---")
    
    # 1. KPI Cards
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Fichiers Sources</div>
            <div class="metric-value" style="color: #0A66C2;">{len(uploaded_files) if uploaded_files else 1}</div>
            <div class="metric-footer">Fichiers traités</div>
        </div>
        """, unsafe_allow_html=True)
        
    with k2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Lignes Brutes</div>
            <div class="metric-value">{stats['initial_rows']:,}</div>
            <div class="metric-footer">Total avant déduplication</div>
        </div>
        """, unsafe_allow_html=True)

    with k3:
        st.markdown(f"""
        <div class="metric-card" style="border-top: 3px solid #E11D48;">
            <div class="metric-title">Doublons Éliminés</div>
            <div class="metric-value" style="color: #E11D48;">{stats['duplicates_removed']:,}</div>
            <div class="metric-footer">Taux : <b>{stats['dedup_rate_pct']}%</b></div>
        </div>
        """, unsafe_allow_html=True)

    with k4:
        st.markdown(f"""
        <div class="metric-card" style="border-top: 3px solid #10B981;">
            <div class="metric-title">Contacts Uniques</div>
            <div class="metric-value" style="color: #10B981;">{stats['final_rows']:,}</div>
            <div class="metric-footer">{len(df_result.columns)} colonnes préservées</div>
        </div>
        """, unsafe_allow_html=True)

    # Détail des critères
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.info(f"🔗 **Doublons détectés par LinkedIn :** {stats['dedup_by_linkedin']}")
    c2.info(f"✉️ **Doublons détectés par Email :** {stats['dedup_by_email']}")
    c3.info(f"👤 **Doublons détectés par Triplet :** {stats['dedup_by_triplet']}")

    # 2. Bouton Téléchargement Prominent
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    current_export_buffer = export_to_excel(df_result)
    
    dl_col1, dl_col2 = st.columns([3, 1])
    with dl_col1:
        st.download_button(
            label=f"📥 Télécharger le Fichier Excel Fusionné ({len(df_result)} contacts uniques)",
            data=current_export_buffer,
            file_name=st.session_state.export_filename or "contacts_fusionnes.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
    with dl_col2:
        st.caption(f"✨ 100% des colonnes conservées, filtres automatiques et styles openpyxl.")

    # 3. Onglets de Consultation
    tab_data, tab_charts, tab_logs = st.tabs(["📋 Aperçu des Contacts", "📈 Graphiques & Statistiques", "📜 Journal d'Exécution"])

    with tab_data:
        search_kw = st.text_input("🔍 Recherche rapide dans la table :", "")
        
        display_df = df_result.copy()
        if search_kw:
            mask = display_df.astype(str).apply(lambda row: row.str.contains(search_kw, case=False, na=False).any(), axis=1)
            display_df = display_df[mask]

        # Affichage direct de toutes les colonnes réelles du fichier
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=420,
        )
        st.caption(f"Affichage de {len(display_df)} sur {len(df_result)} contacts uniques ({len(df_result.columns)} colonnes).")

    with tab_charts:
        ch1, ch2 = st.columns([3, 2])
        col_ent = roles["entreprise"]
        col_stat = roles["statut"]

        with ch1:
            if col_ent and col_ent in df_result.columns and not df_result.empty:
                top_comp = df_result[col_ent].dropna().value_counts().head(10).reset_index()
                top_comp.columns = ["Entreprise", "Contacts"]
                fig_bar = px.bar(
                    top_comp,
                    x="Contacts",
                    y="Entreprise",
                    orientation="h",
                    title=f"🏢 Top 10 des Entreprises ({col_ent})",
                    color="Contacts",
                    color_continuous_scale=["#93C5FD", "#0A66C2"]
                )
                fig_bar.update_layout(
                    yaxis=dict(autorange="reversed"),
                    margin=dict(l=20, r=20, t=40, b=20),
                    height=360,
                )
                st.plotly_chart(fig_bar, use_container_width=True)

        with ch2:
            if col_stat and col_stat in df_result.columns and not df_result.empty:
                mx_counts = df_result[col_stat].fillna("Non renseigné").value_counts().reset_index()
                mx_counts.columns = ["Statut", "Total"]
                fig_pie = px.pie(
                    mx_counts,
                    names="Statut",
                    values="Total",
                    title=f"🛡️ Répartition du Statut ({col_stat})",
                    hole=0.45,
                    color_discrete_sequence=["#10B981", "#F59E0B", "#EF4444", "#64748B"]
                )
                fig_pie.update_layout(
                    margin=dict(l=20, r=20, t=40, b=20),
                    height=360,
                )
                st.plotly_chart(fig_pie, use_container_width=True)

    with tab_logs:
        logs = log_buffer.get_logs()
        if logs:
            log_lines_html = []
            for entry in logs[-60:]:
                lvl = entry["level"]
                cls_name = "term-info" if lvl == "INFO" else ("term-warn" if lvl == "WARNING" else "term-err")
                time_str = entry["timestamp"]
                raw = entry["message"].replace("<", "&lt;").replace(">", "&gt;")
                log_lines_html.append(f'<div><span class="term-time">[{time_str}]</span><span class="{cls_name}">[{lvl}]</span> {raw}</div>')
            st.markdown(f'<div class="terminal-console">{"".join(log_lines_html)}</div>', unsafe_allow_html=True)
        else:
            st.info("Aucun log généré.")
else:
    st.markdown("""
    <div style="background: #F8FAFC; border: 1px dashed #CBD5E1; border-radius: 12px; padding: 40px 20px; text-align: center; color: #64748B; margin-top: 10px;">
        <div style="font-size: 2.5rem; margin-bottom: 10px;">📂</div>
        <div style="font-size: 1.1rem; font-weight: 600; color: #334155;">Aucun fichier chargé pour le moment</div>
        <div style="font-size: 0.9rem; margin-top: 4px;">Glissez vos fichiers Excel ci-dessus puis cliquez sur "🚀 Fusionner les fichiers".</div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📜 Logs d'activité", expanded=False):
        logs = log_buffer.get_logs()
        if logs:
            log_lines_html = []
            for entry in logs[-30:]:
                lvl = entry["level"]
                cls_name = "term-info" if lvl == "INFO" else ("term-warn" if lvl == "WARNING" else "term-err")
                time_str = entry["timestamp"]
                raw = entry["message"].replace("<", "&lt;").replace(">", "&gt;")
                log_lines_html.append(f'<div><span class="term-time">[{time_str}]</span><span class="{cls_name}">[{lvl}]</span> {raw}</div>')
            st.markdown(f'<div class="terminal-console">{"".join(log_lines_html)}</div>', unsafe_allow_html=True)
        else:
            st.caption("En attente de traitement.")
