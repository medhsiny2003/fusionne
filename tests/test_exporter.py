"""
Tests unitaires pour le module d'exportation Excel.
"""

import io
import os
import openpyxl
import pandas as pd
import pytest
from core.exporter import export_to_excel, generate_export_filename, MX_STYLES

def test_export_to_excel_buffer():
    """Vérifie la génération du buffer binaire Excel stylisé avec colonnes personnalisées."""
    cols = ["Prénom", "Nom", "Poste", "Entreprise", "Email_proposé", "Email_alternatif", "Score_confiance", "Statut_validation", "URL_LinkedIn"]
    df = pd.DataFrame([
        {
            "Prénom": "Alice",
            "Nom": "Vasseur",
            "Poste": "CEO",
            "Entreprise": "Innovate",
            "Email_proposé": "alice@innovate.com",
            "Email_alternatif": "",
            "Score_confiance": "98%",
            "Statut_validation": "Validé",
            "URL_LinkedIn": "https://linkedin.com/in/alice"
        },
        {
            "Prénom": "Bob",
            "Nom": "Durand",
            "Poste": "CTO",
            "Entreprise": "TechSoft",
            "Email_proposé": "bob@techsoft.com",
            "Email_alternatif": "",
            "Score_confiance": "45%",
            "Statut_validation": "Invalide",
            "URL_LinkedIn": "https://linkedin.com/in/bob"
        },
    ])

    buffer = export_to_excel(df)
    assert isinstance(buffer, io.BytesIO)
    buffer.seek(0)

    # Recharger avec openpyxl pour vérifier les styles
    wb = openpyxl.load_workbook(buffer)
    ws = wb.active
    assert ws.max_row == 3 # 1 header + 2 data
    assert ws.max_column == len(cols)

    # Vérification des couleurs d'en-tête
    header_cell = ws.cell(row=1, column=1)
    assert header_cell.fill.start_color.rgb in ["000A66C2", "0A66C2"]
    assert header_cell.font.bold is True

    # Vérification de l'auto-filtre
    assert ws.auto_filter.ref is not None

def test_export_to_file(tmp_path):
    """Vérifie l'écriture de l'exportation sur le disque."""
    df = pd.DataFrame([{"Prénom": "Test", "Nom": "User", "Statut_validation": "Validé"}])
    export_file = tmp_path / "test_out.xlsx"
    
    export_to_excel(df, output_path=str(export_file))
    assert os.path.exists(export_file)
    assert os.path.getsize(export_file) > 0

def test_generate_export_filename():
    """Vérifie le format du nom de fichier généré."""
    filename = generate_export_filename()
    assert filename.startswith("contacts_fusionnes_")
    assert filename.endswith(".xlsx")
