"""
Module d'exportation Excel stylisé pour Fusion avec openpyxl.
Applique une mise en page professionnelle (charte LinkedIn), des filtres auto,
l'ajustement dynamique des colonnes et des mises en forme conditionnelles sur le statut MX.
"""

import io
import os
from datetime import datetime
from typing import Optional, Union
import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from .logger import setup_logger

logger = setup_logger()

# Couleurs de la charte
HEADER_BG_COLOR = "0A66C2"     # Bleu LinkedIn
HEADER_TEXT_COLOR = "FFFFFF"   # Blanc
BORDER_COLOR = "D0D7DE"        # Gris clair

# Styles de statut MX
MX_STYLES = {
    "validé": {
        "fill": PatternFill(start_color="D4EDDA", end_color="D4EDDA", fill_type="solid"),
        "font": Font(color="155724", bold=True, name="Calibri", size=11),
    },
    "valide": {
        "fill": PatternFill(start_color="D4EDDA", end_color="D4EDDA", fill_type="solid"),
        "font": Font(color="155724", bold=True, name="Calibri", size=11),
    },
    "à vérifier": {
        "fill": PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid"),
        "font": Font(color="856404", bold=True, name="Calibri", size=11),
    },
    "a verifier": {
        "fill": PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid"),
        "font": Font(color="856404", bold=True, name="Calibri", size=11),
    },
    "invalide": {
        "fill": PatternFill(start_color="F8D7DA", end_color="F8D7DA", fill_type="solid"),
        "font": Font(color="721C24", bold=True, name="Calibri", size=11),
    },
}

def generate_export_filename() -> str:
    """Génère le nom de fichier horodaté standard."""
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"contacts_fusionnes_{now_str}.xlsx"

def export_to_excel(
    df: pd.DataFrame,
    output_path: Optional[str] = None,
    include_source_file: bool = False
) -> io.BytesIO:
    """
    Génère un classeur Excel openpyxl hautement stylisé à partir du DataFrame de contacts.
    
    Arguments :
      - df : DataFrame des contacts dédupliqués
      - output_path : Chemin optionnel pour sauvegarder sur disque
      - include_source_file : Si True, conserve la colonne _Fichier_Source
      
    Retourne :
      - io.BytesIO contenant le fichier binaire Excel prêt au téléchargement.
    """
    logger.info(f"Génération du fichier Excel pour {len(df)} contacts...")

    # Nettoyage des colonnes internes
    export_df = df.copy()
    internal_cols = [c for c in export_df.columns if c.startswith("_") and (c != "_Fichier_Source" or not include_source_file)]
    export_df = export_df.drop(columns=internal_cols, errors="ignore")

    # Remplacer les valeurs NaN par une chaîne vide pour un rendu propre
    export_df = export_df.fillna("")

    # Création du classeur Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Contacts Fusionnés"
    ws.views.sheetView[0].showGridLines = True

    # Définition des styles généraux
    header_fill = PatternFill(start_color=HEADER_BG_COLOR, end_color=HEADER_BG_COLOR, fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color=HEADER_TEXT_COLOR)
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    data_font = Font(name="Calibri", size=11)
    data_alignment = Alignment(vertical="center")
    
    thin_border = Border(
        left=Side(style="thin", color=BORDER_COLOR),
        right=Side(style="thin", color=BORDER_COLOR),
        top=Side(style="thin", color=BORDER_COLOR),
        bottom=Side(style="thin", color=BORDER_COLOR),
    )

    # 1. Écriture des en-têtes
    headers = list(export_df.columns)
    for col_num, header_title in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header_title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = thin_border
    ws.row_dimensions[1].height = 28

    # Identifier la colonne Statut MX pour coloration conditionnelle
    mx_col_idx = None
    confidence_col_idx = None
    for idx, h in enumerate(headers, 1):
        if str(h).strip().lower() == "statut mx":
            mx_col_idx = idx
        elif "confiance" in str(h).strip().lower():
            confidence_col_idx = idx

    # 2. Écriture des données
    for row_idx, row_data in enumerate(export_df.itertuples(index=False), 2):
        ws.row_dimensions[row_idx].height = 20
        for col_idx, cell_value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=cell_value)
            cell.font = data_font
            cell.alignment = data_alignment
            cell.border = thin_border

            # Coloration conditionnelle pour Statut MX
            if col_idx == mx_col_idx and cell_value:
                val_clean = str(cell_value).strip().lower()
                if val_clean in MX_STYLES:
                    cell.fill = MX_STYLES[val_clean]["fill"]
                    cell.font = MX_STYLES[val_clean]["font"]
                    cell.alignment = Alignment(horizontal="center", vertical="center")

            # Centrage pour le Score de Confiance
            if col_idx == confidence_col_idx:
                cell.alignment = Alignment(horizontal="center", vertical="center")

    # 3. Activation du filtre automatique sur toute la plage
    if len(headers) > 0:
        max_col_letter = get_column_letter(len(headers))
        total_rows = max(len(export_df) + 1, 2)
        ws.auto_filter.ref = f"A1:{max_col_letter}{total_rows}"

    # 4. Ajustement dynamique des largeurs de colonnes
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        # Largeur minimale de 12 et maximale de 45 avec marge
        ws.column_dimensions[col_letter].width = max(min(max_len + 4, 45), 14)

    # 5. Sauvegarde sur disque si un chemin est fourni
    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        wb.save(output_path)
        logger.info(f"Fichier Excel exporté avec succès sur disque : {output_path}")

    # 6. Écriture dans le buffer BytesIO pour téléchargement
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
