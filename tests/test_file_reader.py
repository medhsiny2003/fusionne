"""
Tests unitaires pour le module file_reader.
"""

import io
import pandas as pd
import pytest
from core.file_reader import read_excel_files, read_single_excel, validate_dataframe, map_column_aliases, EXPECTED_COLUMNS

def create_sample_excel_bytes(data: dict) -> io.BytesIO:
    """Helper pour générer un fichier Excel binaire en mémoire."""
    df = pd.DataFrame(data)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    buffer.seek(0)
    return buffer

def test_read_valid_excel():
    """Vérifie la lecture d'un fichier Excel 100% conforme."""
    sample_data = {col: [f"Val_{col}_1", f"Val_{col}_2"] for col in EXPECTED_COLUMNS}
    excel_bytes = create_sample_excel_bytes(sample_data)
    
    df = read_single_excel(excel_bytes, filename="contacts_test.xlsx")
    assert not df.empty
    assert len(df) == 2
    for col in EXPECTED_COLUMNS:
        assert col in df.columns
    assert df["_Fichier_Source"].iloc[0] == "contacts_test.xlsx"

def test_column_alias_mapping():
    """Vérifie le mapping automatique des colonnes personnalisées (ex: LinkedIn Prospector)."""
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
    df = read_single_excel(excel_bytes, filename="custom_prospects.xlsx")

    assert len(df) == 2
    # Vérifier que les colonnes ont été correctement mappées vers le standard
    assert "Poste Actuel" in df.columns and df["Poste Actuel"].iloc[0] == "Technicienne"
    assert "Email Proposé" in df.columns and df["Email Proposé"].iloc[0] == "katharina.ma@citeos.com"
    assert "Email Alternatif 1" in df.columns and df["Email Alternatif 1"].iloc[0] == "katharinamai@gmail.com"
    assert "Score de Confiance (%)" in df.columns and df["Score de Confiance (%)"].iloc[0] == "95%"
    assert "Statut MX" in df.columns and df["Statut MX"].iloc[0] == "Validé"
    assert "Lien Profil LinkedIn" in df.columns and "katharina-maillot" in df["Lien Profil LinkedIn"].iloc[0]

def test_read_missing_columns():
    """Vérifie qu'un fichier avec colonnes manquantes est complété automatiquement."""
    partial_data = {
        "Prénom": ["Alice"],
        "Nom": ["Dupont"],
        "Entreprise": ["TechCorp"],
        "Email Proposé": ["alice@techcorp.com"]
    }
    excel_bytes = create_sample_excel_bytes(partial_data)
    df = read_single_excel(excel_bytes, filename="partial.xlsx")
    
    assert len(df) == 1
    # Toutes les colonnes attendues doivent être présentes
    for col in EXPECTED_COLUMNS:
        assert col in df.columns
    # Les colonnes manquantes doivent avoir None / NaN
    assert pd.isna(df["Lien Profil LinkedIn"].iloc[0])

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

def test_read_multiple_excel_files():
    """Vérifie la lecture et concaténation de plusieurs fichiers."""
    data1 = {col: [f"F1_{col}"] for col in EXPECTED_COLUMNS}
    data2 = {col: [f"F2_{col}"] for col in EXPECTED_COLUMNS}
    
    f1 = (create_sample_excel_bytes(data1), "f1.xlsx")
    f2 = (create_sample_excel_bytes(data2), "f2.xlsx")
    f_corrupt = (io.BytesIO(b"corrupt"), "bad.xlsx")

    concat_df, count_success, total_rows = read_excel_files([f1, f2, f_corrupt])
    
    assert count_success == 2
    assert total_rows == 2
    assert len(concat_df) == 2
    assert set(concat_df["_Fichier_Source"]) == {"f1.xlsx", "f2.xlsx"}
