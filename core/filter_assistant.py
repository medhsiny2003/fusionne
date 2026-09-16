"""
Module d'assistance intelligente et de filtrage chirurgical pour Fusion.
Permet d'interpréter des commandes en langage naturel, de supprimer des lignes/plages,
d'exclure des entreprises spécifiques et d'appliquer des filtres de qualité en cascade.
"""

import re
import unicodedata
from typing import List, Tuple, Set, Dict, Optional, Any
import pandas as pd
from .deduplicator import detect_column_roles, parse_confidence_score, is_valid_email_syntax

def parse_line_ranges(range_str: str, max_index: int) -> Set[int]:
    """
    Parse une chaîne de plages ou numéros de lignes (1-indexed) :
    Ex: '1-5, 8, 12-15' -> {0, 1, 2, 3, 4, 7, 11, 12, 13, 14}
    """
    if not range_str or not range_str.strip():
        return set()

    indices = set()
    cleaned = range_str.replace("à", "-").replace("a", "-").replace("to", "-")
    tokens = re.findall(r"(\d+)(?:\s*-\s*(\d+))?", cleaned)

    for start_str, end_str in tokens:
        if not start_str:
            continue
        start = int(start_str)
        if end_str:
            end = int(end_str)
            # Ordonner start et end
            low, high = min(start, end), max(start, end)
            for i in range(low, high + 1):
                if 1 <= i <= max_index:
                    indices.add(i - 1) # 0-indexed
        else:
            if 1 <= start <= max_index:
                indices.add(start - 1)

    return indices

def delete_by_indices(df: pd.DataFrame, indices_to_remove: Set[int]) -> Tuple[pd.DataFrame, int]:
    """Supprime les lignes selon un ensemble d'indices 0-indexed."""
    if df.empty or not indices_to_remove:
        return df, 0

    valid_indices = [i for i in indices_to_remove if 0 <= i < len(df)]
    if not valid_indices:
        return df, 0

    new_df = df.drop(index=valid_indices).reset_index(drop=True)
    return new_df, len(valid_indices)

def delete_by_companies(df: pd.DataFrame, companies_to_remove: List[str]) -> Tuple[pd.DataFrame, int]:
    """Supprime toutes les lignes associées aux entreprises spécifiées."""
    if df.empty or not companies_to_remove:
        return df, 0

    roles = detect_column_roles(list(df.columns))
    col_ent = roles["entreprise"]
    if not col_ent or col_ent not in df.columns:
        return df, 0

    to_remove_clean = [str(c).strip().lower() for c in companies_to_remove]
    mask = df[col_ent].apply(lambda x: str(x).strip().lower() in to_remove_clean if pd.notna(x) else False)
    
    deleted_count = mask.sum()
    new_df = df[~mask].reset_index(drop=True)
    return new_df, int(deleted_count)

def execute_smart_command(df: pd.DataFrame, command_text: str) -> Tuple[pd.DataFrame, str, bool]:
    """
    Interprète une commande en langage naturel et applique la modification :
    Exemples :
    - 'supprimer les lignes 1 à 5'
    - 'supprimer la ligne 12'
    - 'supprimer entreprise Airbus'
    - 'supprimer les contacts avec statut invalide'
    - 'garder uniquement statut validé'
    - 'supprimer score < 80'
    - 'supprimer les contacts sans email'
    
    Retourne : (nouveau_df, message_explication, succes)
    """
    if df.empty:
        return df, "Le tableau est vide.", False

    cmd = command_text.strip().lower()
    norm_cmd = "".join([c for c in unicodedata.normalize("NFKD", cmd) if not unicodedata.combining(c)])
    
    roles = detect_column_roles(list(df.columns))
    col_ent = roles["entreprise"]
    col_stat = roles["statut"]
    col_score = roles["score"]
    col_email = roles["email_primary"]

    initial_count = len(df)

    # 1. Commande de suppression par lignes/plages (ex: 'supprimer lignes 1 a 5', 'supprimer 1-10')
    if any(k in norm_cmd for k in ["ligne", "lignes", "rang", "index"]) or re.search(r"^\s*\d+\s*(?:-\s*\d+)?", norm_cmd):
        indices = parse_line_ranges(norm_cmd, len(df))
        if indices:
            new_df, count = delete_by_indices(df, indices)
            return new_df, f"✅ {count} ligne(s) supprimée(s) avec succès.", True

    # 2. Commande de suppression par Entreprise (ex: 'supprimer entreprise airbus', 'exclure societe thales')
    if any(k in norm_cmd for k in ["entreprise", "societe", "company", "boite", "exclure"]):
        if col_ent and col_ent in df.columns:
            # Extraire les noms d'entreprises mentionnés
            existing_companies = df[col_ent].dropna().unique()
            matched_companies = []
            for comp in existing_companies:
                comp_clean = "".join([c for c in unicodedata.normalize("NFKD", str(comp).lower()) if not unicodedata.combining(c)])
                if comp_clean and comp_clean in norm_cmd:
                    matched_companies.append(str(comp))

            if matched_companies:
                new_df, count = delete_by_companies(df, matched_companies)
                names_str = ", ".join(matched_companies)
                return new_df, f"✅ {count} contact(s) supprimé(s) pour l'entreprise ({names_str}).", True

    # 3. Commande sur le statut (ex: 'supprimer invalide', 'garder valide')
    if col_stat and col_stat in df.columns:
        if "invalide" in norm_cmd and any(k in norm_cmd for k in ["supprimer", "enlever", "purg", "retirer", "delete"]):
            mask = df[col_stat].apply(lambda x: str(x).strip().lower() in ["invalide", "invalid", "faux"] if pd.notna(x) else False)
            new_df = df[~mask].reset_index(drop=True)
            count = mask.sum()
            return new_df, f"✅ {count} contact(s) avec statut 'Invalide' supprimé(s).", True

        if "valide" in norm_cmd and any(k in norm_cmd for k in ["garder", "conserver", "uniquement", "seulement"]):
            mask = df[col_stat].apply(lambda x: str(x).strip().lower() in ["validé", "valide", "valid"] if pd.notna(x) else False)
            new_df = df[mask].reset_index(drop=True)
            count = initial_count - len(new_df)
            return new_df, f"✅ Filtre appliqué : {len(new_df)} contacts 'Validé' conservés ({count} lignes écartées).", True

    # 4. Commande sur le score (ex: 'supprimer score < 80', 'score inferieur a 70')
    score_match = re.search(r"score\s*(?:<|inf[eé]rieur\s*(?:[aà])?|moins\s*de)?\s*(\d+)", norm_cmd)
    if score_match and col_score and col_score in df.columns:
        threshold = float(score_match.group(1))
        scores = df[col_score].apply(parse_confidence_score)
        mask = scores < threshold
        new_df = df[~mask].reset_index(drop=True)
        count = mask.sum()
        return new_df, f"✅ {count} contact(s) avec un score < {threshold}% supprimé(s).", True

    # 5. Commande sur les emails (ex: 'supprimer sans email', 'emails invalides')
    if any(k in norm_cmd for k in ["sans email", "sans mail", "email vide", "email invalide", "faux email"]):
        if col_email and col_email in df.columns:
            valid_mask = df[col_email].apply(is_valid_email_syntax)
            new_df = df[valid_mask].reset_index(drop=True)
            count = initial_count - len(new_df)
            return new_df, f"✅ {count} contact(s) sans email valide supprimé(s).", True

    return df, f"⚠️ Commande non reconnue : '{command_text}'. Exemples : 'supprimer les lignes 1 à 5', 'supprimer entreprise Airbus', 'supprimer statut invalide', 'supprimer score < 80'.", False
