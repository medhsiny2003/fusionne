"""
Module de déduplication intelligente en cascade pour Fusion.
Applique les 3 critères en cascade avec normalisation internationale LinkedIn,
arbitrage par score de confiance, complétude des données et fusion des emails alternatifs.
"""

import re
import urllib.parse
from typing import List, Optional, Tuple, Set
import numpy as np
import pandas as pd
from .logger import setup_logger

logger = setup_logger()

def normalize_text(text: Optional[str]) -> str:
    """Nettoie et normalise une chaîne de texte (minuscules, suppression espaces superflus)."""
    if text is None or pd.isna(text):
        return ""
    s = str(text).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def normalize_email(email: Optional[str]) -> str:
    """Normalise une adresse email."""
    if email is None or pd.isna(email):
        return ""
    e = str(email).strip().lower()
    if "@" not in e:
        return ""
    return e

def normalize_linkedin_url(url: Optional[str]) -> str:
    """
    Normalise une URL de profil LinkedIn :
    - Enlève les paramètres de tracking (?...) et fragments (#...)
    - Enlève le protocole (http/https)
    - Normalise tous les sous-domaines (ma.linkedin.com, fr.linkedin.com, re.linkedin.com, www.linkedin.com -> linkedin.com)
    - Enlève le slash final
    - Passage en minuscules
    """
    if url is None or pd.isna(url):
        return ""
    u = str(url).strip().lower()
    if not u or "linkedin.com" not in u:
        return ""
    
    # Enlever fragments et query params
    u = re.sub(r"[?#].*$", "", u)
    # Enlever protocoles
    u = re.sub(r"^https?://", "", u)
    # Remplacer tout sous-domaine par linkedin.com (ex: ma.linkedin.com, re.linkedin.com, www.linkedin.com)
    u = re.sub(r"^[a-z0-9\-_.]+\.linkedin\.com", "linkedin.com", u)
    # Enlever trailing slash
    u = u.rstrip("/")
    return u

def parse_confidence_score(score_val) -> float:
    """Convertit une valeur de score de confiance en float entre 0 et 100."""
    if score_val is None or pd.isna(score_val):
        return 0.0
    try:
        if isinstance(score_val, (int, float)):
            return float(score_val)
        s = str(score_val).replace("%", "").replace(",", ".").strip()
        return float(s)
    except (ValueError, TypeError):
        return 0.0

def count_row_completeness(row: pd.Series) -> int:
    """Calcule le nombre de champs remplis et non vides dans une ligne."""
    count = 0
    for val in row:
        if pd.notna(val):
            s = str(val).strip()
            if s and s.lower() not in ["none", "nan", "null", ""]:
                count += 1
    return count

def merge_duplicate_group(group_df: pd.DataFrame) -> pd.Series:
    """
    Fusionne un groupe de lignes doublons :
    1. Sélectionne la ligne ayant le meilleur Score de Confiance.
    2. En cas d'égalité, prend la ligne la plus complète (moins de NaN).
    3. Fusionne les emails alternatifs disponibles dans le groupe sans perte.
    """
    if len(group_df) == 1:
        return group_df.iloc[0].copy()

    # Calculer scores et complétude pour chaque ligne
    scores = group_df["Score de Confiance (%)"].apply(parse_confidence_score)
    completeness = group_df.apply(count_row_completeness, axis=1)

    # Créer un DataFrame temporaire de tri
    temp_df = group_df.copy()
    temp_df["_parsed_score"] = scores
    temp_df["_completeness"] = completeness
    temp_df["_orig_idx"] = range(len(temp_df))

    # Trier par score décroissant, puis complétude décroissante, puis index initial
    sorted_df = temp_df.sort_values(
        by=["_parsed_score", "_completeness", "_orig_idx"],
        ascending=[False, False, True]
    )

    # La ligne gagnante
    best_row = sorted_df.iloc[0].drop(labels=["_parsed_score", "_completeness", "_orig_idx"]).copy()

    # Collecter tous les emails distincts valides du groupe
    collected_emails: List[str] = []
    
    for _, row in group_df.iterrows():
        for col in ["Email Proposé", "Email Alternatif 1", "Email Alternatif 2"]:
            if col in row and pd.notna(row[col]):
                raw_email = str(row[col]).strip()
                norm = normalize_email(raw_email)
                if norm and norm not in [normalize_email(e) for e in collected_emails]:
                    collected_emails.append(raw_email)

    # Réattribuer les emails à la ligne gagnante
    best_primary_email = best_row.get("Email Proposé")
    norm_primary = normalize_email(best_primary_email)

    if norm_primary:
        # Garder le primaire et lister les autres
        alt_emails = [e for e in collected_emails if normalize_email(e) != norm_primary]
    else:
        # Si pas d'email primaire dans la meilleure ligne mais disponible ailleurs
        if collected_emails:
            best_row["Email Proposé"] = collected_emails[0]
            alt_emails = collected_emails[1:]
        else:
            alt_emails = []

    # Affecter Email Alternatif 1 & 2
    best_row["Email Alternatif 1"] = alt_emails[0] if len(alt_emails) > 0 else best_row.get("Email Alternatif 1", None)
    best_row["Email Alternatif 2"] = alt_emails[1] if len(alt_emails) > 1 else best_row.get("Email Alternatif 2", None)

    return best_row

def deduplicate_contacts(df: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    """
    Exécute la déduplication intelligente en 3 critères en cascade :
      1. Lien Profil LinkedIn
      2. Email Proposé (si LinkedIn absent)
      3. Triplet Prénom + Nom + Entreprise (si LinkedIn et Email absents)

    Retourne :
      - DataFrame dédupliqué et fusionné
      - Dictionnaire des statistiques de déduplication
    """
    if df.empty:
        stats = {
            "initial_rows": 0,
            "final_rows": 0,
            "duplicates_removed": 0,
            "dedup_by_linkedin": 0,
            "dedup_by_email": 0,
            "dedup_by_triplet": 0,
            "dedup_rate_pct": 0.0,
        }
        return df, stats

    initial_rows = len(df)
    logger.info(f"Démarrage de la déduplication sur {initial_rows} contacts...")

    # Travailler sur une copie
    work_df = df.copy().reset_index(drop=True)
    work_df["_row_id"] = range(len(work_df))

    # Clés de déduplication normalisées
    work_df["_key_linkedin"] = work_df["Lien Profil LinkedIn"].apply(normalize_linkedin_url) if "Lien Profil LinkedIn" in work_df.columns else ""
    work_df["_key_email"] = work_df["Email Proposé"].apply(normalize_email) if "Email Proposé" in work_df.columns else ""
    
    # Triplet Prénom + Nom + Entreprise
    def build_triplet(row):
        p = normalize_text(row.get("Prénom", ""))
        n = normalize_text(row.get("Nom", ""))
        e = normalize_text(row.get("Entreprise", ""))
        if p and n and e:
            return f"{p}|{n}|{e}"
        return ""

    work_df["_key_triplet"] = work_df.apply(build_triplet, axis=1)

    # Attribution d'un ID de cluster unique (Cascade : LinkedIn > Email > Triplet)
    cluster_map = {} # row_id -> cluster_id
    next_cluster_id = 1

    linkedin_groups = {}
    for idx, row in work_df.iterrows():
        l_key = row["_key_linkedin"]
        if l_key:
            if l_key not in linkedin_groups:
                linkedin_groups[l_key] = next_cluster_id
                next_cluster_id += 1
            cluster_map[idx] = linkedin_groups[l_key]

    # Groupe 2: Par Email (pour les lignes sans linkedin_key)
    email_groups = {}
    for idx, row in work_df.iterrows():
        if idx not in cluster_map:
            e_key = row["_key_email"]
            if e_key:
                if e_key not in email_groups:
                    email_groups[e_key] = next_cluster_id
                    next_cluster_id += 1
                cluster_map[idx] = email_groups[e_key]

    # Groupe 3: Par Triplet (pour les lignes sans linkedin_key et sans email_key)
    triplet_groups = {}
    for idx, row in work_df.iterrows():
        if idx not in cluster_map:
            t_key = row["_key_triplet"]
            if t_key:
                if t_key not in triplet_groups:
                    triplet_groups[t_key] = next_cluster_id
                    next_cluster_id += 1
                cluster_map[idx] = triplet_groups[t_key]

    # Lignes orphelines (aucun critère présent) : chacune forme son propre cluster
    for idx in range(len(work_df)):
        if idx not in cluster_map:
            cluster_map[idx] = next_cluster_id
            next_cluster_id += 1

    work_df["_cluster_id"] = [cluster_map[i] for i in range(len(work_df))]

    # Compteurs statistiques
    linkedin_cluster_ids = set(linkedin_groups.values())
    email_cluster_ids = set(email_groups.values())
    triplet_cluster_ids = set(triplet_groups.values())

    dedup_by_linkedin = 0
    dedup_by_email = 0
    dedup_by_triplet = 0

    merged_rows = []
    grouped = work_df.groupby("_cluster_id", sort=False)

    for cluster_id, grp in grouped:
        grp_size = len(grp)
        if grp_size > 1:
            dups = grp_size - 1
            if cluster_id in linkedin_cluster_ids:
                dedup_by_linkedin += dups
            elif cluster_id in email_cluster_ids:
                dedup_by_email += dups
            elif cluster_id in triplet_cluster_ids:
                dedup_by_triplet += dups

        clean_grp = grp.drop(columns=["_row_id", "_key_linkedin", "_key_email", "_key_triplet", "_cluster_id"])
        merged_row = merge_duplicate_group(clean_grp)
        merged_rows.append(merged_row)

    final_df = pd.DataFrame(merged_rows).reset_index(drop=True)
    final_rows = len(final_df)
    duplicates_removed = initial_rows - final_rows
    rate = (duplicates_removed / initial_rows * 100) if initial_rows > 0 else 0.0

    stats = {
        "initial_rows": initial_rows,
        "final_rows": final_rows,
        "duplicates_removed": duplicates_removed,
        "dedup_by_linkedin": dedup_by_linkedin,
        "dedup_by_email": dedup_by_email,
        "dedup_by_triplet": dedup_by_triplet,
        "dedup_rate_pct": round(rate, 2),
    }

    logger.info(
        f"Déduplication réussie: {final_rows} contacts uniques conservés. "
        f"{duplicates_removed} doublons supprimés ({round(rate, 1)}%). "
        f"[LinkedIn: {dedup_by_linkedin}, Email: {dedup_by_email}, Triplet: {dedup_by_triplet}]"
    )

    return final_df, stats

def filter_contacts(
    df: pd.DataFrame,
    mx_status: Optional[List[str]] = None,
    min_confidence: float = 0.0,
    selected_companies: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Applique les filtres optionnels sur le DataFrame de contacts :
    - mx_status : liste des statuts MX autorisés (ex: ['Validé', 'À vérifier'])
    - min_confidence : score de confiance minimal (0-100)
    - selected_companies : liste des entreprises sélectionnées
    """
    if df.empty:
        return df

    filtered_df = df.copy()

    # 1. Filtre par Statut MX (tolérant à la casse et non-bloquant si vide)
    if mx_status is not None and len(mx_status) > 0 and "Statut MX" in filtered_df.columns:
        allowed = [str(s).strip().lower() for s in mx_status]
        # Si 'tous' est présent, on ne filtre pas
        if "tous" not in allowed:
            filtered_df = filtered_df[
                filtered_df["Statut MX"].apply(
                    lambda val: str(val).strip().lower() in allowed if (pd.notna(val) and str(val).strip() != "") else True
                )
            ]

    # 2. Filtre par Score de Confiance
    if min_confidence > 0.0 and "Score de Confiance (%)" in filtered_df.columns:
        scores = filtered_df["Score de Confiance (%)"].apply(parse_confidence_score)
        filtered_df = filtered_df[scores >= min_confidence]

    # 3. Filtre par Entreprise
    if selected_companies and len(selected_companies) > 0 and "Entreprise" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Entreprise"].astype(str).isin(selected_companies)]

    return filtered_df.reset_index(drop=True)
