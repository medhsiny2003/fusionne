"""
Module de lecture et validation des fichiers Excel pour Fusion.
Supporte les formats .xlsx et .xls avec gestion avancée des erreurs.
"""

import io
import os
from typing import List, Tuple, Union, BinaryIO
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

def validate_dataframe(df: pd.DataFrame, filename: str) -> Tuple[pd.DataFrame, List[str]]:
    """
    Vérifie la présence des colonnes attendues dans le DataFrame.
    Complète les colonnes manquantes avec des valeurs vides et logue les avertissements.
    """
    missing_cols = [col for col in EXPECTED_COLUMNS if col not in df.columns]
    
    if missing_cols:
        logger.warning(
            f"Fichier '{filename}': {len(missing_cols)} colonne(s) manquante(s): {missing_cols}. "
            f"Colonnes trouvées: {list(df.columns)}"
        )
    else:
        logger.info(f"Fichier '{filename}': structure de colonnes 100% conforme.")

    # Harmoniser le DataFrame avec toutes les colonnes attendues
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
        
        # Valider et harmoniser
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
