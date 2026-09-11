"""
Tests unitaires pour le moteur de déduplication en cascade et de filtrage.
"""

import pandas as pd
import pytest
from core.deduplicator import deduplicate_contacts, filter_contacts, normalize_linkedin_url, normalize_email

def test_normalize_helpers():
    """Test des helpers de normalisation."""
    # LinkedIn
    assert normalize_linkedin_url("https://www.linkedin.com/in/john-doe/") == "linkedin.com/in/john-doe"
    assert normalize_linkedin_url("http://linkedin.com/in/john-doe?trk=public") == "linkedin.com/in/john-doe"
    assert normalize_linkedin_url(None) == ""
    assert normalize_linkedin_url("") == ""

    # Email
    assert normalize_email("  John.Doe@Company.COM ") == "john.doe@company.com"
    assert normalize_email("invalide") == ""
    assert normalize_email(None) == ""

def test_deduplication_criterion_1_linkedin():
    """Critère 1 : Deux lignes avec le même profil LinkedIn doivent être fusionnées."""
    df = pd.DataFrame([
        {
            "Prénom": "Jean",
            "Nom": "Dupont",
            "Poste Actuel": "CEO",
            "Entreprise": "Alpha Inc",
            "Email Proposé": "jean@alpha.com",
            "Email Alternatif 1": None,
            "Email Alternatif 2": None,
            "Score de Confiance (%)": "80%",
            "Statut MX": "Validé",
            "Serveur MX Actif": "Oui",
            "Lien Profil LinkedIn": "https://www.linkedin.com/in/jeandupont/",
            "Date d'Extraction": "2026-01-01"
        },
        {
            "Prénom": "Jean",
            "Nom": "Dupont",
            "Poste Actuel": "CEO & Founder",
            "Entreprise": "Alpha Inc",
            "Email Proposé": "j.dupont@alpha.com",
            "Email Alternatif 1": "ceo@alpha.com",
            "Email Alternatif 2": None,
            "Score de Confiance (%)": 95,
            "Statut MX": "Validé",
            "Serveur MX Actif": "Oui",
            "Lien Profil LinkedIn": "https://linkedin.com/in/jeandupont?trk=123",
            "Date d'Extraction": "2026-02-01"
        }
    ])

    dedup_df, stats = deduplicate_contacts(df)
    assert len(dedup_df) == 1
    assert stats["duplicates_removed"] == 1
    assert stats["dedup_by_linkedin"] == 1
    # La ligne avec score 95 doit être retenue en base
    assert dedup_df["Score de Confiance (%)"].iloc[0] == 95
    assert dedup_df["Poste Actuel"].iloc[0] == "CEO & Founder"
    # L'email alternatif doit contenir l'autre email fusionné
    alt_emails = [dedup_df["Email Alternatif 1"].iloc[0], dedup_df["Email Alternatif 2"].iloc[0]]
    assert "jean@alpha.com" in alt_emails or "ceo@alpha.com" in alt_emails

def test_deduplication_criterion_2_email():
    """Critère 2 : Si LinkedIn est absent, dédupliquer par Email Proposé."""
    df = pd.DataFrame([
        {
            "Prénom": "Sophie",
            "Nom": "Martin",
            "Poste Actuel": "Marketing Director",
            "Entreprise": "Beta Corp",
            "Email Proposé": "sophie.martin@beta.com",
            "Email Alternatif 1": None,
            "Email Alternatif 2": None,
            "Score de Confiance (%)": 70,
            "Statut MX": "À vérifier",
            "Serveur MX Actif": "Non",
            "Lien Profil LinkedIn": None,
            "Date d'Extraction": "2026-01-01"
        },
        {
            "Prénom": "Sophie",
            "Nom": "Martin",
            "Poste Actuel": "CMO",
            "Entreprise": "Beta Corp",
            "Email Proposé": "sophie.martin@beta.com",
            "Email Alternatif 1": None,
            "Email Alternatif 2": None,
            "Score de Confiance (%)": 85,
            "Statut MX": "Validé",
            "Serveur MX Actif": "Oui",
            "Lien Profil LinkedIn": "",
            "Date d'Extraction": "2026-02-01"
        }
    ])

    dedup_df, stats = deduplicate_contacts(df)
    assert len(dedup_df) == 1
    assert stats["duplicates_removed"] == 1
    assert stats["dedup_by_email"] == 1
    assert dedup_df["Score de Confiance (%)"].iloc[0] == 85
    assert dedup_df["Poste Actuel"].iloc[0] == "CMO"

def test_deduplication_criterion_3_triplet():
    """Critère 3 : Si LinkedIn et Email sont absents, dédupliquer par Triplet."""
    df = pd.DataFrame([
        {
            "Prénom": "Marc",
            "Nom": "Lefebvre",
            "Poste Actuel": "Developer",
            "Entreprise": "Gamma LLC",
            "Email Proposé": None,
            "Email Alternatif 1": None,
            "Email Alternatif 2": None,
            "Score de Confiance (%)": 50,
            "Statut MX": "Invalide",
            "Serveur MX Actif": "Non",
            "Lien Profil LinkedIn": None,
            "Date d'Extraction": "2026-01-01"
        },
        {
            "Prénom": "Marc",
            "Nom": "Lefebvre",
            "Poste Actuel": "Senior Developer",
            "Entreprise": "Gamma LLC",
            "Email Proposé": None,
            "Email Alternatif 1": None,
            "Email Alternatif 2": None,
            "Score de Confiance (%)": 50,
            "Statut MX": "Invalide",
            "Serveur MX Actif": "Non",
            "Lien Profil LinkedIn": None,
            "Date d'Extraction": "2026-02-01"
        }
    ])

    dedup_df, stats = deduplicate_contacts(df)
    assert len(dedup_df) == 1
    assert stats["duplicates_removed"] == 1
    assert stats["dedup_by_triplet"] == 1

def test_tie_breaking_by_completeness():
    """En cas d'égalité de score, la ligne la plus complète doit être conservée."""
    df = pd.DataFrame([
        {
            "Prénom": "Lucas",
            "Nom": "Bernard",
            "Poste Actuel": None,
            "Entreprise": "Delta SA",
            "Email Proposé": "lucas@delta.com",
            "Email Alternatif 1": None,
            "Email Alternatif 2": None,
            "Score de Confiance (%)": 90,
            "Statut MX": "Validé",
            "Serveur MX Actif": "Oui",
            "Lien Profil LinkedIn": "https://linkedin.com/in/lucasbernard",
            "Date d'Extraction": "2026-01-01"
        },
        {
            "Prénom": "Lucas",
            "Nom": "Bernard",
            "Poste Actuel": "Lead Architect",
            "Entreprise": "Delta SA",
            "Email Proposé": "lucas@delta.com",
            "Email Alternatif 1": "l.bernard@delta.com",
            "Email Alternatif 2": "lucas.b@delta.com",
            "Score de Confiance (%)": 90,
            "Statut MX": "Validé",
            "Serveur MX Actif": "Oui",
            "Lien Profil LinkedIn": "https://linkedin.com/in/lucasbernard",
            "Date d'Extraction": "2026-01-02"
        }
    ])

    dedup_df, stats = deduplicate_contacts(df)
    assert len(dedup_df) == 1
    assert dedup_df["Poste Actuel"].iloc[0] == "Lead Architect"

def test_filter_contacts():
    """Vérifie le fonctionnement des filtres de recherche."""
    df = pd.DataFrame([
        {"Prénom": "A", "Entreprise": "Google", "Statut MX": "Validé", "Score de Confiance (%)": 95},
        {"Prénom": "B", "Entreprise": "Microsoft", "Statut MX": "À vérifier", "Score de Confiance (%)": 60},
        {"Prénom": "C", "Entreprise": "Google", "Statut MX": "Invalide", "Score de Confiance (%)": 30},
    ])

    # Filtrer par statut MX
    f1 = filter_contacts(df, mx_status=["Validé"])
    assert len(f1) == 1
    assert f1["Prénom"].iloc[0] == "A"

    # Filtrer par score min
    f2 = filter_contacts(df, min_confidence=70)
    assert len(f2) == 1
    assert f2["Prénom"].iloc[0] == "A"

    # Filtrer par entreprise
    f3 = filter_contacts(df, selected_companies=["Google"])
    assert len(f3) == 2
