#!/usr/bin/env python3
"""VGM MCP — walidacja wszystkiego, co przychodzi od klienta.

Argumenty narzędzi pisze model, a model czyta cudze strony i cudze pliki,
więc traktujemy je jak wejście od przeciwnika: sprawdzamy typ, długość,
zakres i znaki, zanim trafią do adresu URL, ścieżki pliku albo kodu JS.

Moduł nie ma zależności poza biblioteką standardową, żeby dało się go
testować bez sieci i bez przeglądarki.
"""
from __future__ import annotations

import math
import os
import re
import tempfile
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


class BladWejscia(ValueError):
    """Argument od klienta odrzucony — komunikat mówi, który i dlaczego."""


# ── limity ──────────────────────────────────────────────────────────────
MAX_KOD_PINE = 200_000        # znaków; kompilator TradingView i tak odrzuca więcej
MAX_PLIK_PINE = 400_000       # bajtów pliku z kodem
MAX_ELEMENTOW = 50            # długość każdej listy od klienta
MAX_WARUNKOW = 10
MAX_INSTRUMENTOW = 10         # każdy to kilkanaście–kilkadziesiąt sekund pracy wykresu
MAX_WYNIK_ZNAKOW = 1_000_000  # odpowiedź większa niż to jest odrzucana

_SYMBOL = re.compile(r"^[A-Za-z0-9_.!\-]{1,40}(:[A-Za-z0-9_.!\-]{1,60})?$")
_INTERWAL = re.compile(r"^(\d{1,4}[SDWMH]?|[DWM])$")
_POLE = re.compile(r"^[A-Za-z0-9_.+\-]{1,48}(\|(\d{1,4}[SDWMH]?|[DWM]))?$")
_ID = re.compile(r"^[A-Za-z0-9_;.\-]{1,100}$")

OPERACJE = {"less", "greater", "equal", "nequal", "eless", "egreater",
            "in_range", "not_in_range", "above_pct", "below_pct",
            "crosses", "crosses_above", "crosses_below", "has", "has_none_of"}


def _bez_sterujacych(t: str) -> bool:
    return not any(ord(c) < 32 or ord(c) == 127 for c in t)


# ── liczby ──────────────────────────────────────────────────────────────
def liczba(x: object, nazwa: str, min_: float, max_: float) -> float:
    """Skończona liczba z przedziału. Odrzuca NaN, nieskończoność, bool i tekst."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise BladWejscia(f"{nazwa}: oczekiwano liczby, jest {type(x).__name__}")
    if not math.isfinite(x):
        raise BladWejscia(f"{nazwa}: liczba nie jest skończona")
    if not min_ <= x <= max_:
        raise BladWejscia(f"{nazwa}: {x} poza zakresem {min_}–{max_}")
    return x


def calkowita(x: object, nazwa: str, min_: int, max_: int) -> int:
    """Liczba całkowita z przedziału. Float przyjmuje tylko, gdy jest całkowity."""
    if isinstance(x, float) and math.isfinite(x) and x == int(x):
        x = int(x)
    if isinstance(x, bool) or not isinstance(x, int):
        raise BladWejscia(f"{nazwa}: oczekiwano liczby całkowitej, jest {type(x).__name__}")
    if not min_ <= x <= max_:
        raise BladWejscia(f"{nazwa}: {x} poza zakresem {min_}–{max_}")
    return x


# ── teksty ──────────────────────────────────────────────────────────────
def symbol(x: object, nazwa: str = "symbol") -> str:
    if not isinstance(x, str) or not _SYMBOL.match(x):
        raise BladWejscia(f"{nazwa}: niedozwolone znaki albo zła długość "
                          "(oczekiwano np. FX:EURUSD)")
    return x


def interwal(x: object, nazwa: str = "interwal") -> str:
    if isinstance(x, int) and not isinstance(x, bool):
        x = str(x)
    if not isinstance(x, str) or not _INTERWAL.match(x):
        raise BladWejscia(f"{nazwa}: oczekiwano np. 5, 60, 240, D, W, M")
    return x


def pole(x: object, nazwa: str = "pole") -> str:
    if not isinstance(x, str) or not _POLE.match(x):
        raise BladWejscia(f"{nazwa}: niedozwolone znaki albo zła długość")
    return x


def identyfikator(x: object, nazwa: str = "id") -> str:
    if not isinstance(x, str) or not _ID.match(x):
        raise BladWejscia(f"{nazwa}: niedozwolone znaki albo zła długość")
    return x


def rynek(x: object, dozwolone: Collection[str]) -> str:
    """Rynek trafia do ścieżki URL (/{rynek}/scan), więc tylko z listy."""
    if not isinstance(x, str) or x not in dozwolone:
        raise BladWejscia(f"rynek: nieznany — dozwolone: {', '.join(sorted(dozwolone))}")
    return x


def tekst(x: object, nazwa: str, max_dl: int, pusty: bool = False, jednolinijkowy: bool = True) -> str:
    if not isinstance(x, str):
        raise BladWejscia(f"{nazwa}: oczekiwano tekstu")
    if not pusty and not x.strip():
        raise BladWejscia(f"{nazwa}: pusty")
    if len(x) > max_dl:
        raise BladWejscia(f"{nazwa}: za długi ({len(x)} znaków, limit {max_dl})")
    if jednolinijkowy and not _bez_sterujacych(x):
        raise BladWejscia(f"{nazwa}: znaki sterujące niedozwolone")
    return x


def kod_pine(x: object) -> str:
    return tekst(x, "kod", MAX_KOD_PINE, jednolinijkowy=False)


def nazwa_skryptu(x: object, nazwa: str = "nazwa", max_dl: int = 100) -> str:
    """Nazwa trafia w cudzysłów w kodzie Pine i na konto — bez cudzysłowów i ukośników."""
    t = tekst(x, nazwa, max_dl)
    if any(c in t for c in '"\\'):
        raise BladWejscia(f"{nazwa}: cudzysłów i ukośnik odwrotny niedozwolone")
    return t


# ── listy ───────────────────────────────────────────────────────────────
def lista(x: object, nazwa: str, jeden: Callable[[Any], T],
          max_el: int = MAX_ELEMENTOW) -> list[T]:
    if not isinstance(x, list):
        raise BladWejscia(f"{nazwa}: oczekiwano listy")
    if len(x) > max_el:
        raise BladWejscia(f"{nazwa}: za dużo elementów ({len(x)}, limit {max_el})")
    return [jeden(e) for e in x]


def liczby(x: object, nazwa: str, min_: float, max_: float, max_el: int = 30) -> list[float]:
    return lista(x, nazwa, lambda e: liczba(e, nazwa, min_, max_), max_el)


def calkowite(x: object, nazwa: str, min_: int, max_: int, max_el: int = 30) -> list[int]:
    return lista(x, nazwa, lambda e: calkowita(e, nazwa, min_, max_), max_el)


def pary_instrument_przedzial(x: object) -> list[tuple[str, str]]:
    """[["FX:EURUSD","60"], ...] — każda para to przełączenie wykresu."""
    def jedna(e: object) -> tuple[str, str]:
        if not isinstance(e, (list, tuple)) or len(e) != 2:
            raise BladWejscia("instrumenty: każda pozycja to [symbol, przedział]")
        return (symbol(e[0], "instrumenty.symbol"), interwal(e[1], "instrumenty.przedzial"))
    return lista(x, "instrumenty", jedna, MAX_INSTRUMENTOW)


def warunki(x: object) -> list[dict[str, Any]]:
    """Filtr skanera: [{"left": pole, "operation": op, "right": liczba|pole|[liczby]}]."""
    def jeden(w: object) -> dict[str, Any]:
        if not isinstance(w, dict) or set(w) - {"left", "operation", "right"}:
            raise BladWejscia("warunki: oczekiwano {left, operation, right}")
        if "left" not in w or "operation" not in w or "right" not in w:
            raise BladWejscia("warunki: brakuje left, operation albo right")
        if w["operation"] not in OPERACJE:
            raise BladWejscia(f"warunki: nieznana operacja {str(w['operation'])[:20]!r}")
        p = w["right"]
        prawa: list[float] | str | float
        if isinstance(p, list):
            prawa = liczby(p, "warunki.right", -1e12, 1e12, 20)
        elif isinstance(p, str):
            prawa = pole(p, "warunki.right")
        else:
            prawa = liczba(p, "warunki.right", -1e12, 1e12)
        return {"left": pole(w["left"], "warunki.left"),
                "operation": w["operation"], "right": prawa}
    return lista(x, "warunki", jeden, MAX_WARUNKOW)


# ── ścieżki plików ──────────────────────────────────────────────────────
def katalog_odczytu() -> Path:
    """Skąd wolno czytać pliki z kodem: VGM_KATALOG_PINE albo katalog roboczy."""
    return Path(os.environ.get("VGM_KATALOG_PINE") or os.getcwd()).resolve()


def katalog_zapisu() -> Path:
    """Gdzie wolno zapisywać zrzuty: VGM_KATALOG_ZRZUTOW albo <tmp>/vgm-mcp."""
    return Path(os.environ.get("VGM_KATALOG_ZRZUTOW")
                or Path(tempfile.gettempdir()) / "vgm-mcp").resolve()


def _wewnatrz(p: Path, baza: Path) -> bool:
    try:
        p.relative_to(baza)
        return True
    except ValueError:
        return False


def sciezka_do_odczytu(x: object, baza: Path | None = None) -> Path:
    """Plik z kodem Pine. Treść idzie do TradingView, więc to wyciek, jeśli
    klient może wskazać dowolny plik — dlatego tylko *.pine/*.txt z katalogu
    bazowego, po rozwiązaniu dowiązań, zwykły plik, z limitem rozmiaru."""
    t = tekst(x, "sciezka", 1024)
    baza = (baza or katalog_odczytu()).resolve()
    p = (baza / t).resolve()           # ścieżka absolutna w `t` wygrywa z bazą — łapie ją sprawdzenie niżej
    if not _wewnatrz(p, baza):
        raise BladWejscia(f"sciezka: plik poza katalogiem {baza} (zmień VGM_KATALOG_PINE)")
    if p.suffix.lower() not in (".pine", ".txt"):
        raise BladWejscia("sciezka: dozwolone tylko pliki .pine i .txt")
    if not p.is_file():
        raise BladWejscia(f"sciezka: nie ma takiego pliku: {t}")
    if p.stat().st_size > MAX_PLIK_PINE:
        raise BladWejscia(f"sciezka: plik większy niż {MAX_PLIK_PINE} bajtów")
    return p


def sciezka_do_zapisu(x: object, baza: Path | None = None) -> Path:
    """Zrzut ekranu. Zapis pod dowolną ścieżką pozwala nadpisać ~/.bashrc czy
    authorized_keys bajtami PNG — dlatego tylko *.png w katalogu bazowym,
    bez dowiązań i bez nadpisywania czegokolwiek, co nie jest zwykłym plikiem."""
    t = tekst(x, "sciezka", 1024)
    baza = (baza or katalog_zapisu()).resolve()
    baza.mkdir(parents=True, exist_ok=True)
    surowa = baza / t
    if surowa.is_symlink():
        raise BladWejscia("sciezka: dowiązania symboliczne niedozwolone")
    p = surowa.resolve()
    if not _wewnatrz(p, baza):
        raise BladWejscia(f"sciezka: poza katalogiem {baza} (zmień VGM_KATALOG_ZRZUTOW)")
    if p.suffix.lower() != ".png":
        raise BladWejscia("sciezka: dozwolone tylko pliki .png")
    if p.exists() and not p.is_file():
        raise BladWejscia("sciezka: cel nie jest zwykłym plikiem")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def wynik_nie_za_duzy(tekst_json: str) -> str:
    if len(tekst_json) > MAX_WYNIK_ZNAKOW:
        raise BladWejscia(f"wynik za duży ({len(tekst_json)} znaków) — zmniejsz `ile`")
    return tekst_json
