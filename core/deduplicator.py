"""
Module de déduplication intelligente non destructif pour Fusion.
Détecte automatiquement les colonnes clés, élimine les doublons en cascade
et conserve 100% des colonnes et formats d'origine.
"""

import re
import unicodedata
from typing import List, Optional, Tuple, Dict
import pandas as pd
from .logger import setup_logger

logger = setup_logger()

def normalize_text(text: Optional[str]) -> str:
    """Nettoie et normalise une chaîne de texte."""
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
    Normalise une URL LinkedIn (gère sous-domaines pays, www, paramètres, trailing slashes).
    """
    if url is None or pd.isna(url):
        return ""
    u = str(url).strip().lower()
    if not u or "linkedin.com" not in u:
        return ""
    
    # Enlever fragments et query params (?...)
    u = re.sub(r"[?#].*$", "", u)
    # Enlever protocoles (http://, https://)
    u = re.sub(r"^https?://", "", u)
    # Remplacer tout sous-domaine par linkedin.com (ex: ma.linkedin.com -> linkedin.com)
    u = re.sub(r"^[a-z0-9\-_.]+\.linkedin\.com", "linkedin.com", u)
    u = u.rstrip("/")
    return u

def parse_confidence_score(score_val) -> float:
    """Convertit une valeur de score en flottant."""
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
    """Calcule le nombre de valeurs non vides dans une ligne."""
    count = 0
    for val in row:
        if pd.notna(val):
            s = str(val).strip()
            if s and s.lower() not in ["none", "nan", "null", ""]:
                count += 1
    return count

def detect_column_roles(columns: List[str]) -> Dict[str, Optional[str]]:
    """
    Détecte intelligemment les rôles des colonnes présentes dans le fichier.
    """
    roles: Dict[str, Optional[str]] = {
        "linkedin": None,
        "email_primary": None,
        "email_alt": None,
        "prenom": None,
        "nom": None,
        "entreprise": None,
        "score": None,
        "statut": None,
    }

    def clean_name(c):
        norm = unicodedata.normalize("NFKD", str(c))
        clean = "".join([x for x in norm if not unicodedata.combining(x)]).lower()
        return re.sub(r"[_\-./\\]+", " ", clean).strip()

    cleaned_cols = {c: clean_name(c) for c in columns}

    for col, cl in cleaned_cols.items():
        # LinkedIn
        if not roles["linkedin"] and ("linkedin" in cl or cl in ["url", "profile url", "lien profil"]):
            roles["linkedin"] = col
        # Score
        elif not roles["score"] and ("score" in cl or "confiance" in cl or "confidence" in cl):
            roles["score"] = col
        # Statut validation
        elif not roles["statut"] and ("statut" in cl or "validation" in cl or "mx" in cl):
            roles["statut"] = col
        # Prénom
        elif not roles["prenom"] and ("prenom" in cl or "first name" in cl or "firstname" in cl):
            roles["prenom"] = col
        # Nom
        elif not roles["nom"] and ("nom" in cl or "last name" in cl or "lastname" in cl or "surname" in cl):
            if "prenom" not in cl:
                roles["nom"] = col
        # Entreprise
        elif not roles["entreprise"] and ("entreprise" in cl or "societe" in cl or "company" in cl or "organisation" in cl):
            roles["entreprise"] = col
        # Email alternatif
        elif not roles["email_alt"] and ("alternatif" in cl or "secondary" in cl or "alt" in cl or "email 2" in cl):
            roles["email_alt"] = col
        # Email principal
        elif not roles["email_primary"] and ("email" in cl or "mail" in cl or "courriel" in cl):
            roles["email_primary"] = col

    # Deuxième passe si l'email principal n'a pas été trouvé mais qu'un email existe
    if not roles["email_primary"]:
        for col, cl in cleaned_cols.items():
            if "mail" in cl or "courriel" in cl or "@" in cl:
                roles["email_primary"] = col
                break

    return roles

def deduplicate_contacts(df: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    """
    Déduplique le DataFrame en préservant 100% des colonnes et formats d'origine.
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
    original_columns = list(df.columns)
    roles = detect_column_roles(original_columns)

    col_linkedin = roles["linkedin"]
    col_email = roles["email_primary"]
    col_email_alt = roles["email_alt"]
    col_prenom = roles["prenom"]
    col_nom = roles["nom"]
    col_entreprise = roles["entreprise"]
    col_score = roles["score"]

    work_df = df.copy().reset_index(drop=True)
    work_df["_row_id"] = range(len(work_df))

    # Calcul des clés normalisées
    work_df["_key_linkedin"] = work_df[col_linkedin].apply(normalize_linkedin_url) if col_linkedin else ""
    work_df["_key_email"] = work_df[col_email].apply(normalize_email) if col_email else ""

    def make_triplet(row):
        p = normalize_text(row.get(col_prenom, "")) if col_prenom else ""
        n = normalize_text(row.get(col_nom, "")) if col_nom else ""
        e = normalize_text(row.get(col_entreprise, "")) if col_entreprise else ""
        if p and n and e:
            return f"{p}|{n}|{e}"
        elif p and n:
            return f"{p}|{n}"
        return ""

    work_df["_key_triplet"] = work_df.apply(make_triplet, axis=1)

    # Groupement en cascade : LinkedIn > Email > Triplet
    cluster_map = {}
    next_cluster_id = 1

    linkedin_groups = {}
    for idx, row in work_df.iterrows():
        l_key = row["_key_linkedin"]
        if l_key:
            if l_key not in linkedin_groups:
                linkedin_groups[l_key] = next_cluster_id
                next_cluster_id += 1
            cluster_map[idx] = linkedin_groups[l_key]

    email_groups = {}
    for idx, row in work_df.iterrows():
        if idx not in cluster_map:
            e_key = row["_key_email"]
            if e_key:
                if e_key not in email_groups:
                    email_groups[e_key] = next_cluster_id
                    next_cluster_id += 1
                cluster_map[idx] = email_groups[e_key]

    triplet_groups = {}
    for idx, row in work_df.iterrows():
        if idx not in cluster_map:
            t_key = row["_key_triplet"]
            if t_key:
                if t_key not in triplet_groups:
                    triplet_groups[t_key] = next_cluster_id
                    next_cluster_id += 1
                cluster_map[idx] = triplet_groups[t_key]

    for idx in range(len(work_df)):
        if idx not in cluster_map:
            cluster_map[idx] = next_cluster_id
            next_cluster_id += 1

    work_df["_cluster_id"] = [cluster_map[i] for i in range(len(work_df))]

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

        clean_grp = grp[original_columns].copy()

        if len(clean_grp) == 1:
            merged_rows.append(clean_grp.iloc[0])
            continue

        # Arbitrage : score de confiance le plus haut, puis complétude
        if col_score:
            scores = clean_grp[col_score].apply(parse_confidence_score)
        else:
            scores = pd.Series([0.0] * len(clean_grp), index=clean_grp.index)
        
        completeness = clean_grp.apply(count_row_completeness, axis=1)

        temp_grp = clean_grp.copy()
        temp_grp["_score"] = scores
        temp_grp["_completeness"] = completeness
        temp_grp["_orig_order"] = range(len(temp_grp))

        sorted_grp = temp_grp.sort_values(
            by=["_score", "_completeness", "_orig_order"],
            ascending=[False, False, True]
        )

        best_row = sorted_grp.iloc[0].drop(labels=["_score", "_completeness", "_orig_order"]).copy()

        # Fusion des emails alternatifs si la colonne existe
        if col_email:
            collected_emails = []
            for _, r in clean_grp.iterrows():
                for c in [col_email, col_email_alt]:
                    if c and c in r and pd.notna(r[c]):
                        raw_e = str(r[c]).strip()
                        norm_e = normalize_email(raw_e)
                        if norm_e and norm_e not in [normalize_email(x) for x in collected_emails]:
                            collected_emails.append(raw_e)

            primary_val = best_row.get(col_email)
            norm_prim = normalize_email(primary_val)
            if not norm_prim and collected_emails:
                best_row[col_email] = collected_emails[0]
                norm_prim = normalize_email(collected_emails[0])

            if col_email_alt:
                other_emails = [e for e in collected_emails if normalize_email(e) != norm_prim]
                if other_emails:
                    best_row[col_email_alt] = other_emails[0]

        merged_rows.append(best_row)

    final_df = pd.DataFrame(merged_rows, columns=original_columns).reset_index(drop=True)
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
        f"Déduplication réussie : {final_rows} contacts uniques conservés sur {initial_rows}. "
        f"{duplicates_removed} doublons éliminés ({round(rate, 1)}%)."
    )

    return final_df, stats

def filter_contacts(
    df: pd.DataFrame,
    mx_status: Optional[List[str]] = None,
    min_confidence: float = 0.0,
    selected_companies: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Filtre optionnel sécurisé.
    """
    if df.empty:
        return df

    filtered_df = df.copy()
    roles = detect_column_roles(list(df.columns))
    col_statut = roles["statut"]
    col_score = roles["score"]
    col_entreprise = roles["entreprise"]

    # 1. Statut
    if mx_status and col_statut and col_statut in filtered_df.columns:
        allowed = [str(s).strip().lower() for s in mx_status]
        filtered_df = filtered_df[
            filtered_df[col_statut].apply(
                lambda val: str(val).strip().lower() in allowed if (pd.notna(val) and str(val).strip() != "") else True
            )
        ]

    # 2. Score
    if min_confidence > 0.0 and col_score and col_score in filtered_df.columns:
        scores = filtered_df[col_score].apply(parse_confidence_score)
        filtered_df = filtered_df[scores >= min_confidence]

    # 3. Entreprise
    if selected_companies and col_entreprise and col_entreprise in filtered_df.columns:
        filtered_df = filtered_df[filtered_df[col_entreprise].astype(str).isin(selected_companies)]

    return filtered_df.reset_index(drop=True)
