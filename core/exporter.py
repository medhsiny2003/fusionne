"""
Module d'exportation Excel pour Fusion avec openpyxl.
Génère un classeur Excel fidèle aux données d'origine, hautement stylisé et sécurisé.
"""

import io
import os
import unicodedata
from datetime import datetime
from typing import Optional
import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from .logger import setup_logger

logger = setup_logger()

# Charte de styles
HEADER_BG_COLOR = "0A66C2"     # Bleu LinkedIn
HEADER_TEXT_COLOR = "FFFFFF"   # Blanc
BORDER_COLOR = "D0D7DE"        # Gris clair

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
    output_path: Optional[str] = None
) -> io.BytesIO:
    """
    Génère un classeur Excel openpyxl stylisé en préservant 100% des colonnes d'origine.
    """
    logger.info(f"Génération du fichier Excel pour {len(df)} contacts uniques...")

    export_df = df.copy()
    
    # Nettoyage des colonnes temporaires internes uniquement
    internal_cols = [c for c in export_df.columns if str(c).startswith("_")]
    if internal_cols:
        export_df = export_df.drop(columns=internal_cols, errors="ignore")

    # Remplacement des NaN par du vide
    export_df = export_df.fillna("")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Prospects_Fusionnés"
    ws.views.sheetView[0].showGridLines = True

    # Styles
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

    headers = list(export_df.columns)

    # 1. Écriture des en-têtes
    for col_num, header_title in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header_title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = thin_border
    ws.row_dimensions[1].height = 28

    # Détection dynamique des colonnes de statut et de score pour style spécifique
    statut_col_idx = None
    score_col_idx = None
    for idx, h in enumerate(headers, 1):
        h_norm = "".join([c for c in unicodedata.normalize("NFKD", str(h)) if not unicodedata.combining(c)]).lower()
        if "statut" in h_norm or "validation" in h_norm or "mx" in h_norm:
            statut_col_idx = idx
        elif "score" in h_norm or "confiance" in h_norm:
            score_col_idx = idx

    # 2. Écriture des données
    for row_idx, row_data in enumerate(export_df.itertuples(index=False), 2):
        ws.row_dimensions[row_idx].height = 20
        for col_idx, cell_value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=cell_value)
            cell.font = data_font
            cell.alignment = data_alignment
            cell.border = thin_border

            # Coloration conditionnelle du statut
            if col_idx == statut_col_idx and cell_value:
                val_clean = str(cell_value).strip().lower()
                if val_clean in MX_STYLES:
                    cell.fill = MX_STYLES[val_clean]["fill"]
                    cell.font = MX_STYLES[val_clean]["font"]
                    cell.alignment = Alignment(horizontal="center", vertical="center")

            # Centrage du score
            if col_idx == score_col_idx:
                cell.alignment = Alignment(horizontal="center", vertical="center")

    # 3. Auto-filtre
    if len(headers) > 0:
        max_col_letter = get_column_letter(len(headers))
        total_rows = max(len(export_df) + 1, 2)
        ws.auto_filter.ref = f"A1:{max_col_letter}{total_rows}"

    # 4. Ajustement automatique des largeurs
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(min(max_len + 4, 45), 14)

    # 5. Sauvegarde sur disque si demandée
    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        wb.save(output_path)
        logger.info(f"Fichier exporté avec succès : {output_path}")

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
