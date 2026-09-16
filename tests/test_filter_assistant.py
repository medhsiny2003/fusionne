"""
Tests unitaires pour le module filter_assistant.
"""

import pandas as pd
import pytest
from core.filter_assistant import (
    parse_line_ranges,
    delete_by_indices,
    delete_by_companies,
    execute_smart_command
)

def test_parse_line_ranges():
    """Vérifie le parsing de plages et indices de lignes."""
    # Saisie simple
    assert parse_line_ranges("1-5", 10) == {0, 1, 2, 3, 4}
    assert parse_line_ranges("1 à 3, 8", 10) == {0, 1, 2, 7}
    assert parse_line_ranges("2, 4, 6", 10) == {1, 3, 5}
    assert parse_line_ranges("10-15", 12) == {9, 10, 11} # limité par max_index

def test_delete_by_indices():
    """Vérifie la suppression par indices."""
    df = pd.DataFrame({"Nom": ["A", "B", "C", "D", "E"]})
    res, count = delete_by_indices(df, {0, 2})
    assert count == 2
    assert list(res["Nom"]) == ["B", "D", "E"]

def test_delete_by_companies():
    """Vérifie la suppression de toutes les lignes d'une ou plusieurs sociétés."""
    df = pd.DataFrame({
        "Nom": ["User1", "User2", "User3", "User4"],
        "Entreprise": ["Thales", "Airbus", "Thales", "Naval Group"]
    })
    res, count = delete_by_companies(df, ["Thales"])
    assert count == 2
    assert len(res) == 2
    assert "Thales" not in list(res["Entreprise"])

def test_execute_smart_command():
    """Vérifie l'exécution des commandes en langage naturel."""
    df = pd.DataFrame({
        "Prénom": ["Alice", "Bob", "Charlie", "David"],
        "Nom": ["Dupont", "Martin", "Lefebvre", "Bernard"],
        "Entreprise": ["Thales", "Airbus", "Thales", "Safran"],
        "Score_confiance": ["95%", "60%", "40%", "90%"],
        "Statut_validation": ["Validé", "Invalide", "À vérifier", "Validé"],
        "Email_proposé": ["alice@thales.com", "bob@airbus.com", "fake", "david@safran.com"]
    })

    # Commande 1 : suppression de lignes
    res1, msg1, ok1 = execute_smart_command(df, "supprimer les lignes 1 à 2")
    assert ok1 is True
    assert len(res1) == 2

    # Commande 2 : suppression d'entreprise
    res2, msg2, ok2 = execute_smart_command(df, "supprimer entreprise Thales")
    assert ok2 is True
    assert len(res2) == 2
    assert "Thales" not in list(res2["Entreprise"])

    # Commande 3 : suppression par statut invalide
    res3, msg3, ok3 = execute_smart_command(df, "supprimer statut invalide")
    assert ok3 is True
    assert len(res3) == 3

    # Commande 4 : suppression par score
    res4, msg4, ok4 = execute_smart_command(df, "supprimer score < 70")
    assert ok4 is True
    assert len(res4) == 2

    # Commande 5 : suppression sans email valide
    res5, msg5, ok5 = execute_smart_command(df, "supprimer sans email")
    assert ok5 is True
    assert len(res5) == 3
