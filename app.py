"""
Application Streamlit - FUSION : Fusionneur Excel avec Déduplication Intelligente.
Préserve 100% des colonnes et données d'origine sans altération.
Studio d'édition, assistant de filtrage intelligent, suppression par société/lignes et export instantané.
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
from core.filter_assistant import (
    parse_line_ranges,
    delete_by_indices,
    delete_by_companies,
    execute_smart_command
)

# Initialisation du logger
logger = setup_logger()

# Configuration Streamlit
st.set_page_config(
    page_title="Fusion — Déduplication & Studio de Filtrage",
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
        padding: 22px 28px;
        border-radius: 12px;
        color: white;
        margin-bottom: 20px;
        box-shadow: 0 4px 16px rgba(10, 102, 194, 0.15);
    }
    .hero-title {
        font-size: 1.7rem;
        font-weight: 700;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .hero-subtitle {
        font-size: 0.92rem;
        color: #E1E9F4;
        margin-top: 6px;
        font-weight: 400;
        line-height: 1.4;
    }

    /* Boîtes KPI */
    .metric-card {
        background: #FFFFFF;
        border-radius: 10px;
        padding: 14px 18px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        text-align: center;
    }
    .metric-title {
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #64748B;
        font-weight: 600;
    }
    .metric-value {
        font-size: 1.75rem;
        font-weight: 700;
        color: #0F172A;
        margin: 4px 0;
    }
    .metric-footer {
        font-size: 0.75rem;
        color: #94A3B8;
    }

    /* Boîtes d'action studio */
    .studio-box {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 16px;
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

    /* Boutons */
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
if "history" not in st.session_state:
    st.session_state.history = []
if "stats" not in st.session_state:
    st.session_state.stats = None
if "excel_buffer" not in st.session_state:
    st.session_state.excel_buffer = None
if "export_filename" not in st.session_state:
    st.session_state.export_filename = ""
if "last_action_msg" not in st.session_state:
    st.session_state.last_action_msg = ""

def format_file_size(size_bytes: int) -> str:
    """Convertit une taille en octets en format lisible."""
    if size_bytes < 1024:
        return f"{size_bytes} o"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} Ko"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} Mo"

def push_history(df: pd.DataFrame):
    """Sauvegarde l'état actuel dans l'historique pour permettre l'annulation (Undo)."""
    if df is not None:
        st.session_state.history.append(df.copy())
        if len(st.session_state.history) > 10:
            st.session_state.history.pop(0)

def undo_last_action():
    """Annule la dernière action de filtrage ou suppression."""
    if st.session_state.history:
        prev_df = st.session_state.history.pop()
        st.session_state.dedup_df = prev_df
        if st.session_state.stats:
            roles = detect_column_roles(list(prev_df.columns))
            col_ent = roles["entreprise"]
            st.session_state.stats["final_rows"] = len(prev_df)
            st.session_state.stats["unique_companies"] = prev_df[col_ent].dropna().nunique() if (col_ent and col_ent in prev_df.columns) else 0
        st.session_state.last_action_msg = "↩️ Dernière action annulée avec succès."
        st.toast("Action annulée !", icon="↩️")

def reset_state():
    """Réinitialise l'ensemble des données."""
    st.session_state.raw_df = None
    st.session_state.dedup_df = None
    st.session_state.history = []
    st.session_state.stats = None
    st.session_state.excel_buffer = None
    st.session_state.export_filename = ""
    st.session_state.last_action_msg = ""
    log_buffer.clear()

# --- HERO BANNER ---
st.markdown("""
<div class="hero-container">
    <div class="hero-title">⚡ FUSION &bull; Déduplication, Nettoyage & Studio IA de Filtrage</div>
    <div class="hero-subtitle">
        Fusionnez vos fichiers Excel sans doublons, <b>groupez par entreprise</b> et filtrez précisément vos données à la ligne ou à la société près grâce à l'assistant intelligent.
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
    btn_process = st.button("🚀 Fusionner & Nettoyer", type="primary", use_container_width=True, disabled=not uploaded_files)
    btn_clear = st.button("🗑️ Réinitialiser tout", use_container_width=True, on_click=reset_state)

# Affichage des badges de fichiers
if uploaded_files:
    chips_html = '<div style="margin-bottom: 15px;">'
    total_size = 0
    for f in uploaded_files:
        total_size += f.size
        chips_html += f'<span class="file-chip">📄 {f.name} ({format_file_size(f.size)})</span>'
    chips_html += f'<span class="file-chip" style="background: #E0F2FE; border-color: #7DD3FC; color: #0369A1; font-weight: 600;">📦 {len(uploaded_files)} fichier(s) • {format_file_size(total_size)}</span></div>'
    st.markdown(chips_html, unsafe_allow_html=True)

# Traitement de fusion initiale
if btn_process and uploaded_files:
    with st.spinner("Nettoyage des emails, déduplication et groupement par société en cours..."):
        raw_df, count_files, total_raw = read_excel_files(uploaded_files)
        st.session_state.raw_df = raw_df

        if not raw_df.empty:
            dedup_df, stats = deduplicate_contacts(raw_df)
            export_name = generate_export_filename()

            st.session_state.dedup_df = dedup_df
            st.session_state.history = []
            st.session_state.stats = stats
            st.session_state.export_filename = export_name
            st.session_state.last_action_msg = "Base fusionnée, dédupliquée et groupée par entreprise."
            st.toast("Fusion et déduplication terminées !", icon="✅")

# --- RÉSULTATS & STUDIO D'ÉDITION ---
if st.session_state.dedup_df is not None and st.session_state.stats is not None:
    df_result = st.session_state.dedup_df
    stats = st.session_state.stats
    roles = detect_column_roles(list(df_result.columns))

    st.markdown("---")
    
    # 1. KPI Cards
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Fichiers Sources</div>
            <div class="metric-value" style="color: #0A66C2;">{len(uploaded_files) if uploaded_files else 1}</div>
            <div class="metric-footer">Imports combinés</div>
        </div>
        """, unsafe_allow_html=True)
        
    with k2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Lignes Initiales</div>
            <div class="metric-value">{stats['initial_rows']:,}</div>
            <div class="metric-footer">Avant traitement</div>
        </div>
        """, unsafe_allow_html=True)

    with k3:
        st.markdown(f"""
        <div class="metric-card" style="border-top: 3px solid #E11D48;">
            <div class="metric-title">Doublons & Vides</div>
            <div class="metric-value" style="color: #E11D48;">{stats['duplicates_removed'] + stats.get('purged_empty_rows', 0):,}</div>
            <div class="metric-footer">Purgés & éliminés</div>
        </div>
        """, unsafe_allow_html=True)

    with k4:
        unique_comps = df_result[roles["entreprise"]].dropna().nunique() if (roles["entreprise"] and roles["entreprise"] in df_result.columns) else 0
        st.markdown(f"""
        <div class="metric-card" style="border-top: 3px solid #0284C7;">
            <div class="metric-title">Sociétés Groupées</div>
            <div class="metric-value" style="color: #0284C7;">{unique_comps:,}</div>
            <div class="metric-footer">Sections continues</div>
        </div>
        """, unsafe_allow_html=True)

    with k5:
        st.markdown(f"""
        <div class="metric-card" style="border-top: 3px solid #10B981;">
            <div class="metric-title">Contacts Actifs</div>
            <div class="metric-value" style="color: #10B981;">{len(df_result):,}</div>
            <div class="metric-footer">Prêts pour export</div>
        </div>
        """, unsafe_allow_html=True)

    # 2. Boutons d'Action & Téléchargement
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    current_export_buffer = export_to_excel(df_result)

    act_c1, act_c2, act_c3 = st.columns([3, 1, 1])
    with act_c1:
        st.download_button(
            label=f"📥 Télécharger le Fichier Excel Final ({len(df_result)} contacts uniques)",
            data=current_export_buffer,
            file_name=st.session_state.export_filename or "contacts_fusionnes.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
    with act_c2:
        if st.button("↩️ Annuler (Undo)", use_container_width=True, disabled=len(st.session_state.history) == 0):
            undo_last_action()
            st.rerun()
    with act_c3:
        if st.session_state.last_action_msg:
            st.caption(f"📢 {st.session_state.last_action_msg}")

    # 3. ONGLETS : STUDIO D'ÉDITION & ASSISTANT IA
    st.markdown("---")
    tab_studio, tab_data, tab_charts, tab_logs = st.tabs([
        "🎛️ Studio d'Édition & Assistant IA",
        "📋 Tableau des Contacts",
        "📈 Répartition par Société",
        "📜 Journal d'Exécution"
    ])

    # --- TAB 1 : STUDIO D'ÉDITION ---
    with tab_studio:
        st.markdown("### 🤖 Assistant de Commandes & Filtrage Personnalisé")
        st.markdown("Exécutez des commandes en langage naturel ou utilisez les sélecteurs pour modifier et affiner vos contacts.")

        # Sous-colonnes : Assistant Prompt vs Outils Chirurgiques
        studio_left, studio_right = st.columns([1, 1])

        with studio_left:
            st.markdown("#### 💬 Commande en Langage Naturel")
            cmd_input = st.text_input(
                "Entrez votre instruction :",
                placeholder="Ex: 'supprimer les lignes 1 à 5', 'supprimer entreprise Airbus', 'supprimer statut invalide', 'supprimer score < 80'",
                key="cmd_prompt_input"
            )
            col_exec_btn, col_help_txt = st.columns([1, 2])
            with col_exec_btn:
                if st.button("⚡ Exécuter", type="primary", use_container_width=True):
                    if cmd_input:
                        push_history(df_result)
                        new_df, msg, success = execute_smart_command(df_result, cmd_input)
                        if success:
                            st.session_state.dedup_df = new_df
                            st.session_state.last_action_msg = msg
                            st.success(msg)
                            st.rerun()
                        else:
                            st.warning(msg)
                    else:
                        st.info("Veuillez saisir une commande.")

            with col_help_txt:
                st.caption("💡 *Comprend : plages de lignes ('1-5'), noms d'entreprises ('Airbus'), statuts ('invalide'), scores ('< 70'), etc.*")

            st.markdown("---")
            st.markdown("#### ⚡ Filtres Rapides en 1 Clic")
            f_c1, f_c2, f_c3 = st.columns(3)
            with f_c1:
                if st.button("🔴 Purger Statuts Invalides", use_container_width=True):
                    push_history(df_result)
                    new_df, msg, ok = execute_smart_command(df_result, "supprimer statut invalide")
                    st.session_state.dedup_df = new_df
                    st.session_state.last_action_msg = msg
                    st.rerun()
            with f_c2:
                if st.button("📉 Purger Scores < 80%", use_container_width=True):
                    push_history(df_result)
                    new_df, msg, ok = execute_smart_command(df_result, "supprimer score < 80")
                    st.session_state.dedup_df = new_df
                    st.session_state.last_action_msg = msg
                    st.rerun()
            with f_c3:
                if st.button("✉️ Purger Sans Email", use_container_width=True):
                    push_history(df_result)
                    new_df, msg, ok = execute_smart_command(df_result, "supprimer sans email")
                    st.session_state.dedup_df = new_df
                    st.session_state.last_action_msg = msg
                    st.rerun()

        with studio_right:
            st.markdown("#### 🏢 Suppression par Société / Entreprise")
            col_ent = roles["entreprise"]
            if col_ent and col_ent in df_result.columns:
                comp_counts = df_result[col_ent].dropna().value_counts()
                comp_options = [f"{comp} ({count} contacts)" for comp, count in comp_counts.items()]
                comp_map = {f"{comp} ({count} contacts)": comp for comp, count in comp_counts.items()}

                selected_comps_ui = st.multiselect(
                    "Sélectionnez une ou plusieurs entreprises à supprimer intégralement :",
                    options=comp_options,
                    placeholder="Choisir une société...",
                    key="multiselect_comp_delete"
                )

                if st.button("🗑️ Supprimer toute(s) cette/ces société(s)", type="secondary", disabled=not selected_comps_ui, use_container_width=True):
                    target_comps = [comp_map[c] for c in selected_comps_ui]
                    push_history(df_result)
                    new_df, del_count = delete_by_companies(df_result, target_comps)
                    st.session_state.dedup_df = new_df
                    st.session_state.last_action_msg = f"🗑️ {del_count} contact(s) supprimé(s) pour {len(target_comps)} entreprise(s)."
                    st.toast(f"{del_count} contacts supprimés !", icon="🗑️")
                    st.rerun()
            else:
                st.info("Aucune colonne d'entreprise détectée.")

            st.markdown("---")
            st.markdown("#### 🔢 Suppression par Numéros ou Plages de Lignes")
            range_input = st.text_input(
                "Entrez les numéros de lignes (1-indexé) :",
                placeholder="Ex: 1-5, 12, 20-30",
                key="manual_range_delete_input"
            )
            if st.button("🗑️ Supprimer ces numéros de lignes", disabled=not range_input, use_container_width=True):
                indices = parse_line_ranges(range_input, len(df_result))
                if indices:
                    push_history(df_result)
                    new_df, del_count = delete_by_indices(df_result, indices)
                    st.session_state.dedup_df = new_df
                    st.session_state.last_action_msg = f"🗑️ {del_count} ligne(s) spécifique(s) supprimée(s)."
                    st.toast(f"{del_count} lignes supprimées !", icon="🗑️")
                    st.rerun()
                else:
                    st.warning("Aucune ligne valide dans la plage saisie.")

    # --- TAB 2 : TABLEAU DES CONTACTS ---
    with tab_data:
        search_kw = st.text_input("🔍 Recherche rapide dans la table :", "", key="search_table_kw")
        
        display_df = df_result.copy()
        display_df.insert(0, "N°", range(1, len(display_df) + 1))

        if search_kw:
            mask = display_df.astype(str).apply(lambda row: row.str.contains(search_kw, case=False, na=False).any(), axis=1)
            display_df = display_df[mask]

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=430,
        )
        st.caption(f"Affichage de {len(display_df)} sur {len(df_result)} contacts uniques ({len(df_result.columns)} colonnes).")

    # --- TAB 3 : GRAPHIQUES ---
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

    # --- TAB 4 : LOGS ---
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
        <div style="font-size: 0.9rem; margin-top: 4px;">Glissez vos fichiers Excel ci-dessus puis cliquez sur "🚀 Fusionner & Nettoyer".</div>
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
