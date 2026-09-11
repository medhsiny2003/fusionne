"""
Module de lecture des fichiers Excel pour Fusion.
Conserve 100% des colonnes originales sans altération, suppression ou ajout forcé.
Respecte la confidentialité des données sensibles.
"""

import io
import os
from typing import List, Tuple, Union, BinaryIO, Optional
import pandas as pd
from .logger import setup_logger

logger = setup_logger()

def read_single_excel(file_source: Union[str, BinaryIO, io.BytesIO], filename: str = "Inconnu") -> pd.DataFrame:
    """
    Lit un fichier Excel individuel (.xlsx ou .xls).
    Préserve exactement les colonnes et données d'origine.
    """
    try:
        df = pd.read_excel(file_source, engine=None)
        
        if df.empty or len(df.columns) == 0:
            logger.warning(f"Fichier '{filename}' ignoré car il est vide.")
            return pd.DataFrame()

        # Nettoyer uniquement les espaces invisibles avant/après dans les noms de colonnes
        df.columns = [str(col).strip() for col in df.columns]
        
        logger.info(f"Fichier '{filename}' chargé : {len(df)} lignes, {len(df.columns)} colonnes.")
        return df

    except Exception as e:
        logger.error(f"Erreur lors de la lecture du fichier '{filename}': {str(e)}")
        return pd.DataFrame()

def read_excel_files(files: List[Union[str, BinaryIO, io.BytesIO, Tuple[Union[str, BinaryIO], str]]]) -> Tuple[pd.DataFrame, int, int]:
    """
    Lit et concatène une liste de fichiers Excel.
    Préserve l'ordre et l'intégralité des colonnes de vos fichiers sans en perdre aucune.
    """
    dataframes: List[pd.DataFrame] = []
    successful_files = 0
    reference_columns: List[str] = []

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
            if not reference_columns:
                reference_columns = list(df.columns)
            dataframes.append(df)
            successful_files += 1

    if not dataframes:
        logger.warning("Aucun fichier valide n'a pu être chargé.")
        return pd.DataFrame(), 0, 0

    # Concaténation en préservant l'ordre des colonnes du premier fichier
    concat_df = pd.concat(dataframes, ignore_index=True)
    
    # Ordonner selon le premier fichier, puis ajouter les colonnes supplémentaires s'il y en a
    ordered_cols = [c for c in reference_columns if c in concat_df.columns]
    extra_cols = [c for c in concat_df.columns if c not in ordered_cols]
    final_cols = ordered_cols + extra_cols
    concat_df = concat_df[final_cols]

    total_raw_rows = len(concat_df)
    logger.info(f"Concaténation réussie : {successful_files} fichier(s), {total_raw_rows} lignes brutes, {len(final_cols)} colonnes préservées.")
    return concat_df, successful_files, total_raw_rows
