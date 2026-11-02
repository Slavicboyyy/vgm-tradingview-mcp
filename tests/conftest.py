"""Wspólna konfiguracja testów — bez sieci, bez przeglądarki, bez konta.

Moduły z `src/` importują się po nazwie (`import dane`), więc dodajemy `src/`
do ścieżki. Pakiet `mcp` jest podmieniany prostym atrapą, żeby testy nie zależały
od zainstalowanej wersji (dekoratory serwera zmieniają się między wydaniami)
ani od niczego, co otwiera połączenie.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _atrapa_mcp():
    """Minimalny zamiennik `mcp`: dekoratory zwracają funkcję bez zmian."""

    class Server:
        def __init__(self, nazwa):
            self.name = nazwa

        def list_tools(self):
            return lambda f: f

        def call_tool(self):
            return lambda f: f

    class Tool:
        def __init__(self, name, description, inputSchema):
            self.name = name
            self.description = description
            self.inputSchema = inputSchema

    class TextContent:
        def __init__(self, type, text):
            self.type = type
            self.text = text

    mod = types.ModuleType("mcp")
    serv = types.ModuleType("mcp.server")
    serv.Server = Server
    stdio = types.ModuleType("mcp.server.stdio")
    stdio.stdio_server = lambda: None
    typy = types.ModuleType("mcp.types")
    typy.Tool = Tool
    typy.TextContent = TextContent
    mod.server, mod.types = serv, typy
    serv.stdio = stdio
    return {"mcp": mod, "mcp.server": serv, "mcp.server.stdio": stdio,
            "mcp.types": typy}


sys.modules.update(_atrapa_mcp())


@pytest.fixture(autouse=True)
def bez_czekania(monkeypatch):
    """Żadnych realnych opóźnień: ani odstępu między zapytaniami, ani sleepów."""
    import dane

    monkeypatch.setattr(dane, "_odczekaj", lambda: None)
    monkeypatch.setattr(dane.time, "sleep", lambda s: None)


@pytest.fixture(autouse=True)
def zakaz_sieci(monkeypatch):
    """Każda próba otwarcia połączenia wywala test zamiast wyjść w świat."""
    import urllib.request

    def _nie(*a, **k):
        raise AssertionError("test próbował użyć sieci")

    monkeypatch.setattr(urllib.request, "urlopen", _nie)


class AtrapaTV:
    """Udaje `dane.odczyt`: zwraca wartości z tabeli dla każdego pytanego pola.

    Pole z sufiksem interwału (`RSI|60`) czyta wartość bazową, chyba że tabela
    ma wpis z pełnym kluczem.
    """

    def __init__(self, tabela):
        self.tabela = tabela
        self.wywolania = []

    def __call__(self, symbol, pola=None):
        self.wywolania.append((symbol, list(pola or [])))
        return {p: self.tabela.get(p, self.tabela.get(p.split("|")[0]))
                for p in (pola or [])}


@pytest.fixture
def atrapa_tv(monkeypatch):
    import dane

    def zrob(tabela):
        a = AtrapaTV(tabela)
        monkeypatch.setattr(dane, "odczyt", a)
        return a

    return zrob
