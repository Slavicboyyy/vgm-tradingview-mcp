"""VGM MCP — wspólne typy. Same aliasy i słowniki, żadnej logiki."""
from __future__ import annotations

from typing import Any, TypedDict

Json = dict[str, Any]


class Swieca(TypedDict):
    """Jedna świeca z wykresu, pola nazwane tak jak zwraca `wykres.swiece`."""

    czas: int
    otwarcie: float
    szczyt: float
    dolek: float
    zamkniecie: float
    wolumen: float | None
