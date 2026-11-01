"""Dokumentacja narzędzi (docs/NARZEDZIA.md) zgodna z serwerem — bez sieci.

Sprawdza w obie strony: każde zarejestrowane narzędzie ma opis w serwerze
i sekcję w dokumencie, a każda sekcja dokumentu odpowiada zarejestrowanemu
narzędziu. Tabela wejścia w sekcji musi mieć dokładnie parametry ze schematu,
z tą samą wymaganością i wartością domyślną, a przykład wywołania musi
przejść walidację serwera. Dodatkowo: każda funkcja i klasa najwyższego
poziomu w src/ ma docstring.

Pakiet `mcp` jest atrapą z conftest.py, więc nic nie łączy się z siecią.
"""
from __future__ import annotations

import ast
import asyncio
import json
import re
from pathlib import Path

import pytest

import serwer

KORZEN = Path(__file__).resolve().parent.parent
DOKUMENT = KORZEN / "docs" / "NARZEDZIA.md"
SRC = KORZEN / "src"

NAGLOWEK = re.compile(r"^### `(vgm_[a-z0-9_]+)`\s*$", re.M)
SEKCJE = ("**Wejście**", "**Wyjście**", "**Przykład**", "**Błędy**")
WIERSZ = re.compile(r"^\| `([a-z_]+)` \|([^|]*)\|([^|]*)\|([^|]*)\|")
BLOK_JSON = re.compile(r"```json\n(.*?)\n```", re.S)


def sekcje(tekst: str) -> dict[str, str]:
    """{nazwa narzędzia: treść sekcji do następnego nagłówka ## albo ###}."""
    wynik: dict[str, str] = {}
    trafienia = list(NAGLOWEK.finditer(tekst))
    for i, m in enumerate(trafienia):
        koniec = trafienia[i + 1].start() if i + 1 < len(trafienia) else len(tekst)
        cialo = tekst[m.end():koniec]
        nastepny_rozdzial = re.search(r"^## ", cialo, re.M)
        if nastepny_rozdzial:
            cialo = cialo[:nastepny_rozdzial.start()]
        assert m.group(1) not in wynik, f"sekcja {m.group(1)} występuje dwa razy"
        wynik[m.group(1)] = cialo
    return wynik


def tabela_wejscia(cialo: str) -> dict[str, tuple[str, str]]:
    """{parametr: (kolumna „wym.", kolumna „domyślnie")} z tabeli pod **Wejście**."""
    wejscie = cialo.split("**Wejście**", 1)[1].split("**Wyjście**", 1)[0]
    wiersze: dict[str, tuple[str, str]] = {}
    for linia in wejscie.splitlines():
        m = WIERSZ.match(linia)
        if m:
            assert m.group(1) not in wiersze, f"parametr {m.group(1)} dwa razy"
            wiersze[m.group(1)] = (m.group(3).strip(), m.group(4).strip())
    return wiersze


@pytest.fixture(scope="module")
def narzedzia():
    return {t.name: t for t in asyncio.run(serwer.lista_narzedzi())}


@pytest.fixture(scope="module")
def dokument():
    assert DOKUMENT.is_file(), f"brak {DOKUMENT.relative_to(KORZEN)}"
    return sekcje(DOKUMENT.read_text(encoding="utf-8"))


def test_kazde_narzedzie_ma_wlasny_opis(narzedzia):
    for nazwa, t in narzedzia.items():
        wlasny = t.description.replace(serwer.UWAGA, "").strip()
        assert len(wlasny) >= 20, f"{nazwa}: brak opisu w serwerze"


def test_kazde_narzedzie_ma_sekcje_w_dokumencie(narzedzia, dokument):
    brak = sorted(set(narzedzia) - set(dokument))
    assert brak == [], f"narzędzia bez sekcji w docs/NARZEDZIA.md: {brak}"


def test_kazda_sekcja_dokumentu_to_zarejestrowane_narzedzie(narzedzia, dokument):
    nadmiar = sorted(set(dokument) - set(narzedzia))
    assert nadmiar == [], f"sekcje bez narzędzia w serwerze: {nadmiar}"


def test_sekcja_ma_wejscie_wyjscie_przyklad_bledy_w_tej_kolejnosci(dokument):
    for nazwa, cialo in dokument.items():
        pozycje = [cialo.find(s) for s in SEKCJE]
        assert -1 not in pozycje, f"{nazwa}: brakuje {SEKCJE[pozycje.index(-1)]}"
        assert pozycje == sorted(pozycje), f"{nazwa}: zła kolejność podsekcji"
        assert "Na żywym rynku" in cialo, f"{nazwa}: brak informacji o sprawdzeniu na żywym rynku"


def test_tabela_wejscia_zgodna_ze_schematem(narzedzia, dokument):
    for nazwa, t in narzedzia.items():
        wlasciwosci = t.inputSchema.get("properties", {})
        wymagane = set(t.inputSchema.get("required", []))
        tabela = tabela_wejscia(dokument[nazwa])
        assert set(tabela) == set(wlasciwosci), (
            f"{nazwa}: parametry w dokumencie {sorted(tabela)} "
            f"≠ schemat {sorted(wlasciwosci)}")
        if not wlasciwosci:
            assert "Brak parametrów." in dokument[nazwa], nazwa
        for param, (wym, domyslnie) in tabela.items():
            assert wym == ("tak" if param in wymagane else "nie"), f"{nazwa}.{param}: wym. = {wym}"
            if "default" in wlasciwosci[param]:
                oczekiwane = f"`{json.dumps(wlasciwosci[param]['default'], ensure_ascii=False)}`"
                assert domyslnie == oczekiwane, f"{nazwa}.{param}: domyślnie {domyslnie} ≠ {oczekiwane}"
            else:
                assert domyslnie == "—", f"{nazwa}.{param}: schemat nie ma wartości domyślnej"


def test_przyklad_wywoluje_to_narzedzie_i_przechodzi_walidacje(narzedzia, dokument):
    for nazwa, cialo in dokument.items():
        przyklad = cialo.split("**Przykład**", 1)[1].split("**Błędy**", 1)[0]
        bloki = BLOK_JSON.findall(przyklad)
        assert bloki, f"{nazwa}: przykład bez bloku ```json"
        wywolanie = json.loads(bloki[0])
        assert wywolanie["name"] == nazwa, f"{nazwa}: przykład woła {wywolanie['name']}"
        argumenty = wywolanie["arguments"]
        schemat = narzedzia[nazwa].inputSchema
        assert set(argumenty) <= set(schemat.get("properties", {})), nazwa
        assert set(schemat.get("required", [])) <= set(argumenty), f"{nazwa}: przykład bez wymaganych"
        serwer.zwaliduj(nazwa, argumenty)   # rzuca BladWejscia przy złym przykładzie


def _bez_docstringu(drzewo: ast.Module, plik: str) -> list[str]:
    brak = [] if ast.get_docstring(drzewo) else [f"{plik}: moduł"]

    def obejdz(cialo: list[ast.stmt], prefiks: str) -> None:
        for n in cialo:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not ast.get_docstring(n):
                    brak.append(f"{plik}:{n.lineno} {prefiks}{n.name}")
                if isinstance(n, ast.ClassDef):
                    obejdz(n.body, f"{n.name}.")

    obejdz(drzewo.body, "")
    return brak


def test_funkcje_i_klasy_w_src_maja_docstringi():
    brak = []
    for p in sorted(SRC.glob("*.py")):
        brak += _bez_docstringu(ast.parse(p.read_text(encoding="utf-8")), p.name)
    assert brak == [], "bez docstringu: " + ", ".join(brak)
