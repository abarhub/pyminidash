"""Exceptions transverses."""
from __future__ import annotations


class ProviderError(Exception):
    """Erreur d'un provider dont le message est déjà destiné à l'utilisateur.

    Le runner affiche `str(exc)` tel quel, sans le préfixe `TypeName:` qu'il
    applique aux exceptions inattendues.
    """
