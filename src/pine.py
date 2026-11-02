#!/usr/bin/env python3
"""VGM MCP — warstwa Pine Script.

Sprawdzanie kodu idzie wprost do kompilatora TradingView, bez przeglądarki
i bez konta. Odpowiedź wraca w około sekundę i podaje dokładną linię oraz
kolumnę błędu.

Kolejność pracy jest obowiązkowa: najpierw `sprawdz`, dopiero potem
wstawianie na wykres. Skrypt ma być udowodniony, zanim dotknie okna.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import siec  # noqa: E402
import walidacja as wal  # noqa: E402
from wspolne import ORIGIN_TV, REFERER_TV, UA_PRZEGLADARKI, odczekaj  # noqa: E402

ADRES = "https://pine-facade.tradingview.com/pine-facade/translate_light/"

# Zmierzone: nginx przed kompilatorem odrzuca zapytania bez Origin i Referer.
# Samo User-Agent nie wystarcza — bez tych dwóch przychodzi 403.
NAGLOWKI = {
    "Origin": ORIGIN_TV,
    "Referer": REFERER_TV,
    "User-Agent": UA_PRZEGLADARKI,
    "Content-Type": "application/x-www-form-urlencoded",
}

ODSTEP_S = 1.0
_ostatnie = [0.0]


class BladPine(Exception):
    """Cokolwiek, co uniemożliwia sprawdzenie kodu."""


def _odczekaj() -> None:
    odczekaj(_ostatnie, ODSTEP_S)


def sprawdz(kod: str) -> dict[str, Any]:
    """Kompiluje kod w kompilatorze TradingView i zwraca błędy z pozycjami.

    Zwraca:
        {"poprawny": True, "bledy": []}
        {"poprawny": False, "bledy": [{linia, kolumna, komunikat}], "podglad": "..."}
    """
    try:
        kod = wal.kod_pine(kod)
    except wal.BladWejscia as e:
        raise BladPine(str(e)) from e

    _odczekaj()
    dane = urllib.parse.urlencode({"source": kod}).encode()
    zad = urllib.request.Request(ADRES, data=dane, headers=NAGLOWKI)

    try:
        o = json.loads(siec.pobierz(zad, timeout=30))
    except siec.BladSieci as blad_sieci:
        raise BladPine(str(blad_sieci)) from blad_sieci
    except urllib.error.HTTPError as blad_http:
        if blad_http.code in (403, 429):
            raise BladPine(
                f"kompilator odmówił ({blad_http.code}). Zatrzymuję się — ponawianie "
                "przy tym kodzie prowadzi do blokady adresu."
            ) from blad_http
        raise BladPine(f"HTTP {blad_http.code} od kompilatora") from blad_http
    except Exception as blad:
        raise BladPine(f"{type(blad).__name__}: {blad}") from blad

    if not isinstance(o, dict) or not o.get("success"):
        raise BladPine(f"kompilator odrzucił zapytanie: {str(o)[:150]}")

    wynik = o.get("result", {}) or {}
    surowe = wynik.get("errors") or wynik.get("errors2") or []

    bledy = []
    for b in surowe:
        start = b.get("start") or {}
        bledy.append({
            "linia": start.get("line") or b.get("line"),
            "kolumna": start.get("column") or b.get("column"),
            "komunikat": b.get("message", ""),
        })

    odp = {"poprawny": not bledy, "bledy": bledy}
    if bledy:
        odp["podglad"] = _podglad(kod, bledy)
    ostrz = wynik.get("warnings") or []
    if ostrz:
        odp["ostrzezenia"] = [w.get("message", str(w)) for w in ostrz][:10]
    return odp


def _podglad(kod: str, bledy: list[dict[str, Any]]) -> str:
    """Pokazuje linie z błędem razem ze skargą kompilatora pod spodem."""
    linie = kod.splitlines()
    kawalki = []
    for b in bledy[:10]:
        nr = b.get("linia")
        etykieta = nr if isinstance(nr, int) else "?"
        tresc = linie[nr - 1] if isinstance(nr, int) and 1 <= nr <= len(linie) else "?"
        wciecie = " " * max(0, (b.get("kolumna") or 1) - 1)
        kawalki.append(f"{etykieta:>4} | {tresc}\n     | {wciecie}^-- {b['komunikat']}")
    return "\n".join(kawalki)


def sprawdz_plik(sciezka: str) -> dict[str, Any]:
    """To samo, ale czyta kod z pliku."""
    try:
        p = wal.sciezka_do_odczytu(sciezka)
        kod = p.read_text(encoding="utf-8")
    except (wal.BladWejscia, UnicodeDecodeError, OSError) as e:
        raise BladPine(str(e)) from e
    w = sprawdz(kod)
    w["plik"] = str(p)
    return w


SZKIELET = """//@version=5
indicator("{nazwa}", overlay={na_wykresie})

// parametry
dlugosc = input.int(14, "Długość")

// obliczenia
wartosc = ta.sma(close, dlugosc)

// rysowanie
plot(wartosc, "Średnia", color=color.blue)
"""


def szkielet(nazwa: str = "Nowy wskaźnik", na_wykresie: bool = True) -> str:
    """Zwraca poprawny szkielet skryptu — sprawdzony w kompilatorze."""
    try:
        nazwa = wal.nazwa_skryptu(nazwa, max_dl=80)
    except wal.BladWejscia as e:
        raise BladPine(str(e)) from e
    return SZKIELET.format(nazwa=nazwa,
                           na_wykresie="true" if na_wykresie else "false")


def _demo() -> None:
    print("1. kod poprawny")
    w = sprawdz('//@version=5\nindicator("test")\nplot(ta.sma(close, 20))')
    print(f"   poprawny: {w['poprawny']}, błędów: {len(w['bledy'])}")

    print("\n2. kod z literówką")
    w = sprawdz('//@version=5\nindicator("test")\nplot(ta.sma(clse, 20))')
    print(f"   poprawny: {w['poprawny']}, błędów: {len(w['bledy'])}")
    for b in w["bledy"]:
        print(f"   linia {b['linia']}, kolumna {b['kolumna']}: {b['komunikat']}")
    print("\n" + w.get("podglad", ""))

    print("\n3. kod z dwoma błędami")
    w = sprawdz('//@version=5\nindicator("test")\nx = niema(1)\nplot(tez_niema)')
    print(f"   błędów: {len(w['bledy'])}")
    for b in w["bledy"]:
        print(f"   linia {b['linia']}: {b['komunikat'][:60]}")

    print("\n4. szkielet — czy sam się kompiluje")
    w = sprawdz(szkielet("Mój wskaźnik"))
    print(f"   poprawny: {w['poprawny']}")

    print("\n5. pusty kod")
    try:
        sprawdz("")
        print("   BŁĄD: powinno rzucić wyjątek")
    except BladPine as e:
        print(f"   poprawnie zatrzymane: {e}")


if __name__ == "__main__":
    _demo()
