"""
Module de lecture et validation des fichiers Excel pour Fusion.
Supporte les formats .xlsx et .xls avec mapping intelligent des alias de colonnes
et gestion avancée des erreurs.
"""

import io
import os
import re
import unicodedata
from typing import List, Tuple, Union, BinaryIO, Dict
import pandas as pd
from .logger import setup_logger

logger = setup_logger()

EXPECTED_COLUMNS = [
    "Prénom",
    "Nom",
    "Poste Actuel",
    "Entreprise",
    "Email Proposé",
    "Email Alternatif 1",
    "Email Alternatif 2",
    "Score de Confiance (%)",
    "Statut MX",
    "Serveur MX Actif",
    "Lien Profil LinkedIn",
    "Date d'Extraction"
]

# Dictionnaire d'alias pour mapper automatiquement les variations de noms de colonnes
COLUMN_ALIASES: Dict[str, List[str]] = {
    "Prénom": [
        "prenom", "prénom", "first name", "firstname", "first_name", "fname"
    ],
    "Nom": [
        "nom", "nom de famille", "last name", "lastname", "last_name", "lname", "surname"
    ],
    "Poste Actuel": [
        "poste actuel", "poste_actuel", "poste", "titre", "title", "job", "job title",
        "job_title", "position", "fonction", "role", "current role", "current_role"
    ],
    "Entreprise": [
        "entreprise", "société", "societe", "company", "compagnie", "organization",
        "organisation", "account", "company name", "company_name"
    ],
    "Email Proposé": [
        "email proposé", "email propose", "email_proposé", "email_propose", "email_proposee",
        "email", "mail", "e-mail", "email address", "email_address", "courriel",
        "email_1", "email 1", "email principal", "primary email"
    ],
    "Email Alternatif 1": [
        "email alternatif 1", "email_alternatif 1", "email_alternatif_1", "email alternatif",
        "email_alternatif", "email secondaire", "alt email", "alt_email", "email 2", "email_2",
        "secondary email", "email_alternatif1"
    ],
    "Email Alternatif 2": [
        "email alternatif 2", "email_alternatif 2", "email_alternatif_2", "email 3", "email_3",
        "alt email 2", "alt_email_2", "email tertiaire", "email_alternatif2"
    ],
    "Score de Confiance (%)": [
        "score de confiance (%)", "score de confiance", "score_de_confiance",
        "score_confiance", "score confiance", "score", "confidence", "confidence score",
        "confidence_score", "score (%)", "confiance", "taux_confiance"
    ],
    "Statut MX": [
        "statut mx", "statut_mx", "statut_validation", "statut validation", "statut",
        "validation", "mx status", "mx_status", "status", "etat mx", "etat_mx", "statut_mail"
    ],
    "Serveur MX Actif": [
        "serveur mx actif", "serveur_mx_actif", "serveur mx", "serveur_mx", "mx active",
        "mx_active", "has mx", "active mx", "mx valide", "mx_valide"
    ],
    "Lien Profil LinkedIn": [
        "lien profil linkedin", "url_linkedin", "url linkedin", "linkedin_url", "linkedin url",
        "lien linkedin", "profil linkedin", "linkedin", "linkedin profile", "profile_url",
        "profile url", "lien_linkedin", "url_profil_linkedin", "url_du_profil"
    ],
    "Date d'Extraction": [
        "date d'extraction", "date_d_extraction", "date extraction", "date_extraction",
        "extraction date", "extraction_date", "date", "created_at", "date_scraping"
    ]
}

def clean_string_for_matching(text: str) -> str:
    """Normalise un nom de colonne pour la comparaison d'alias."""
    if not text:
        return ""
    # Décomposer les accents
    text_norm = unicodedata.normalize("NFKD", str(text))
    text_clean = "".join([c for c in text_norm if not unicodedata.combining(c)]).lower()
    # Remplacer séparateurs par espace
    text_clean = re.sub(r"[_\-./\\]+", " ", text_clean)
    text_clean = re.sub(r"\s+", " ", text_clean).strip()
    return text_clean

def map_column_aliases(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Détecte et renomme automatiquement les colonnes selon le dictionnaire d'alias.
    """
    rename_mapping: Dict[str, str] = {}
    already_assigned = set()

    for col in df.columns:
        col_clean = clean_string_for_matching(col)
        matched = False
        
        for canonical_col, aliases in COLUMN_ALIASES.items():
            if canonical_col in already_assigned:
                continue
            clean_aliases = [clean_string_for_matching(a) for a in aliases]
            if col_clean in clean_aliases:
                rename_mapping[col] = canonical_col
                already_assigned.add(canonical_col)
                matched = True
                break
        
        if not matched:
            # Essayer de mapper par inclusion de mots clés
            for canonical_col, aliases in COLUMN_ALIASES.items():
                if canonical_col in already_assigned:
                    continue
                clean_aliases = [clean_string_for_matching(a) for a in aliases]
                if any(alias in col_clean or col_clean in alias for alias in clean_aliases if len(alias) >= 4):
                    rename_mapping[col] = canonical_col
                    already_assigned.add(canonical_col)
                    break

    if rename_mapping:
        df = df.rename(columns=rename_mapping)
        
    return df, rename_mapping

def validate_dataframe(df: pd.DataFrame, filename: str) -> Tuple[pd.DataFrame, List[str]]:
    """
    Vérifie la présence des colonnes attendues après mapping d'alias.
    Complète les colonnes manquantes avec des valeurs vides et logue les détails.
    """
    # 1. Appliquer le mapping d'alias intelligent
    df, mapped_cols = map_column_aliases(df)
    if mapped_cols:
        mapped_summary = ", ".join([f"'{k}' -> '{v}'" for k, v in mapped_cols.items() if k != v])
        if mapped_summary:
            logger.info(f"Fichier '{filename}': Colonnes mappées avec succès ({mapped_summary}).")

    # 2. Vérifier les colonnes manquantes
    missing_cols = [col for col in EXPECTED_COLUMNS if col not in df.columns]
    
    if missing_cols:
        logger.warning(
            f"Fichier '{filename}': {len(missing_cols)} colonne(s) non trouvée(s) : {missing_cols}. "
            f"Colonnes disponibles : {list(df.columns)}"
        )
    else:
        logger.info(f"Fichier '{filename}': structure 100% conforme.")

    # 3. Harmoniser le DataFrame avec toutes les colonnes attendues
    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = None

    # Réordonner selon l'ordre standard tout en préservant les colonnes additionnelles éventuelles
    extra_cols = [c for c in df.columns if c not in EXPECTED_COLUMNS]
    ordered_cols = EXPECTED_COLUMNS + extra_cols
    return df[ordered_cols], missing_cols

def read_single_excel(file_source: Union[str, BinaryIO, io.BytesIO], filename: str = "Inconnu") -> pd.DataFrame:
    """
    Lit un fichier Excel individuel (.xlsx ou .xls).
    Gère les erreurs de corruption, fichiers vides et formats invalides.
    """
    try:
        # Lire le fichier Excel
        df = pd.read_excel(file_source, engine=None)
        
        if df.empty or len(df.columns) == 0:
            logger.warning(f"Fichier '{filename}' ignoré car il est vide.")
            return pd.DataFrame(columns=EXPECTED_COLUMNS)

        # Nettoyer les espaces résiduels dans les noms de colonnes
        df.columns = [str(col).strip() for col in df.columns]
        
        # Valider et harmoniser avec mapping d'alias
        df_valid, _ = validate_dataframe(df, filename)
        
        # Ajouter le fichier source pour traçabilité interne
        df_valid["_Fichier_Source"] = filename
        
        logger.info(f"Fichier '{filename}' chargé avec succès ({len(df_valid)} lignes).")
        return df_valid

    except Exception as e:
        logger.error(f"Erreur lors de la lecture du fichier '{filename}': {str(e)}")
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

def read_excel_files(files: List[Union[str, BinaryIO, io.BytesIO, Tuple[Union[str, BinaryIO], str]]]) -> Tuple[pd.DataFrame, int, int]:
    """
    Lit et concatène une liste de fichiers Excel.
    
    Retourne :
      - DataFrame unifié concaténé
      - Nombre de fichiers lus avec succès
      - Nombre total de lignes brutes
    """
    dataframes: List[pd.DataFrame] = []
    successful_files = 0

    for item in files:
        if isinstance(item, tuple):
            file_obj, filename = item
        elif hasattr(item, "name"):
            file_obj = item
            filename = getattr(item, "name", "Inconnu")
        elif isinstance(item, str):
            file_obj = item
            filename = os.path.basename(item)
        else:
            file_obj = item
            filename = "Fichier_Upload"

        df = read_single_excel(file_obj, filename=filename)
        if not df.empty:
            dataframes.append(df)
            successful_files += 1

    if not dataframes:
        logger.warning("Aucun fichier valide n'a pu être chargé.")
        empty_df = pd.DataFrame(columns=EXPECTED_COLUMNS + ["_Fichier_Source"])
        return empty_df, 0, 0

    concat_df = pd.concat(dataframes, ignore_index=True)
    total_raw_rows = len(concat_df)
    logger.info(f"Concaténation terminée: {successful_files} fichier(s) traité(s), {total_raw_rows} lignes brutes au total.")
    return concat_df, successful_files, total_raw_rows
