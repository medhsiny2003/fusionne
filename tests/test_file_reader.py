"""
Tests unitaires pour le module file_reader.
"""

import io
import pandas as pd
import pytest
from core.file_reader import read_excel_files, read_single_excel

def create_sample_excel_bytes(data: dict) -> io.BytesIO:
    """Helper pour générer un fichier Excel binaire en mémoire."""
    df = pd.DataFrame(data)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    buffer.seek(0)
    return buffer

def test_read_preserves_exact_columns():
    """Vérifie que 100% des colonnes d'origine sont préservées sans aucune altération."""
    custom_data = {
        "Prénom": ["Katharina", "Lalla"],
        "Nom": ["Maillot", "Coulibaly"],
        "Poste": ["Technicienne", "Axians Maroc"],
        "Entreprise": ["Citeos", "Axians"],
        "Email_proposé": ["katharina.ma@citeos.com", "lalla.coulibaly@axians.com"],
        "Email_alternatif": ["katharinamai@gmail.com", "lallacoulibaly@gmail.com"],
        "Score_confiance": ["95%", "95%"],
        "Statut_validation": ["Validé", "Validé"],
        "URL_LinkedIn": ["https://re.linkedin.com/in/katharina-maillot", "https://ma.linkedin.com/in/lalla-coulibaly"]
    }
    excel_bytes = create_sample_excel_bytes(custom_data)
    df = read_single_excel(excel_bytes, filename="prospects.xlsx")

    assert len(df) == 2
    # L'ordre et les noms exacts doivent être strictement identiques
    assert list(df.columns) == list(custom_data.keys())

def test_read_empty_excel():
    """Vérifie le traitement d'un fichier Excel vide."""
    empty_df = pd.DataFrame()
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        empty_df.to_excel(writer, index=False)
    buffer.seek(0)

    df = read_single_excel(buffer, filename="vide.xlsx")
    assert df.empty

def test_read_corrupted_excel():
    """Vérifie qu'un fichier corrompu ne fait pas planter l'application."""
    corrupted_bytes = io.BytesIO(b"CECI N EST PAS UN FICHIER EXCEL VALIDE")
    df = read_single_excel(corrupted_bytes, filename="corrupt.xlsx")
    assert df.empty

def test_read_multiple_excel_files_preserves_structure():
    """Vérifie la lecture et concaténation fidèle de plusieurs fichiers."""
    cols = ["Prénom", "Nom", "Poste", "Entreprise", "Email_proposé", "Email_alternatif", "Score_confiance", "Statut_validation", "URL_LinkedIn"]
    data1 = {c: [f"F1_{c}"] for c in cols}
    data2 = {c: [f"F2_{c}"] for c in cols}
    
    f1 = (create_sample_excel_bytes(data1), "f1.xlsx")
    f2 = (create_sample_excel_bytes(data2), "f2.xlsx")

    concat_df, count_success, total_rows = read_excel_files([f1, f2])
    
    assert count_success == 2
    assert total_rows == 2
    assert len(concat_df) == 2
    assert list(concat_df.columns) == cols
