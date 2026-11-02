#!/usr/bin/env python3
"""Sprawdzenie, czy VGM MCP nadal działa. Uruchom: python3 test_vgm.py

Sprawdza to, co realnie może się zepsuć: pola, które TradingView wycofa,
rynki, które przestaną odpowiadać, kompilator Pine, warstwę wykresu.

Warstwa wykresu jest pomijana, gdy przeglądarka nie odpowiada — to nie błąd,
tylko brak środowiska.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

ZALICZONE = []
OBLANE = []
POMINIETE = []


def sprawdz(nazwa, warunek, szczegol=""):
    if warunek:
        ZALICZONE.append(nazwa)
        print(f"  ok    {nazwa}" + (f"  ({szczegol})" if szczegol else ""))
    else:
        OBLANE.append((nazwa, szczegol))
        print(f"  BŁĄD  {nazwa}" + (f"  ({szczegol})" if szczegol else ""))


def pomin(nazwa, powod):
    POMINIETE.append(nazwa)
    print(f"  pom.  {nazwa}  ({powod})")


def dane_i_pola():
    import dane
    import pola

    print("\ndane i pola")
    w = dane.odczyt("FX:EURUSD", pola.WSZYSTKIE)
    dziala = sum(1 for v in w.values() if v is not None)
    sprawdz("wszystkie pola odpowiadają", dziala == len(pola.WSZYSTKIE),
            f"{dziala} z {len(pola.WSZYSTKIE)}")

    time.sleep(1)
    m = dane.mtf("FX:EURUSD", ["RSI"], ["5", "60"])
    sprawdz("wiele przedziałów czasu", len(m.get("RSI", {})) == 2,
            f"{len(m.get('RSI', {}))} przedziałów")

    time.sleep(1)
    z = dane.zgodnosc("FX:EURUSD")
    sprawdz("zgodność przedziałów", "za_kupnem" in z and "rsi" in z)

    time.sleep(1)
    try:
        dane.odczyt("NIE-ISTNIEJE-XYZ")
        sprawdz("błąd przy złej nazwie", False, "nie zgłosił błędu")
    except dane.BladTV:
        sprawdz("błąd przy złej nazwie", True)


def rynki():
    import dane
    import pola

    print("\nrynki")
    for nazwa in pola.RYNKI:
        try:
            w = dane.przeglad(nazwa, [{"left": "RSI", "operation": "less", "right": 45}],
                              ["close", "RSI"], 2)
            sprawdz(f"rynek {nazwa}", bool(w), f"{len(w)} wyników")
        except Exception as e:
            sprawdz(f"rynek {nazwa}", False, str(e)[:40])
        time.sleep(1.2)


def analiza_():
    import analiza

    print("\nanaliza")
    p = analiza.polozenie("FX:EURUSD")
    sprawdz("położenie ceny", p.get("cena") is not None
            and p.get("w_kanale_bollingera_proc") is not None)

    time.sleep(1)
    u = analiza.uklad_srednich("FX:EURUSD")
    sprawdz("układ średnich", u.get("par_razem", 0) > 0, f"{u.get('par_razem')} par")

    time.sleep(1)
    o = analiza.obraz("FX:EURUSD")
    grupy = sum(1 for k, v in o.items() if isinstance(v, dict) and v)
    sprawdz("pełny obraz", grupy >= 8, f"{grupy} grup")


def pine_():
    import pine

    print("\nPine Script")
    w = pine.sprawdz('//@version=5\nindicator("t")\nplot(ta.sma(close,20))')
    sprawdz("kod poprawny przechodzi", w["poprawny"])

    time.sleep(1)
    w = pine.sprawdz('//@version=5\nindicator("t")\nplot(ta.sma(clse,20))')
    sprawdz("literówka wykryta", not w["poprawny"] and len(w["bledy"]) == 1,
            f"{len(w['bledy'])} błędów")
    sprawdz("błąd ma pozycję", w["bledy"][0].get("linia") == 3,
            f"linia {w['bledy'][0].get('linia')}")

    time.sleep(1)
    sprawdz("szkielet się kompiluje", pine.sprawdz(pine.szkielet("Test"))["poprawny"])


def wykres_():
    import wykres

    print("\nwykres")
    z = wykres.zdrowie()
    if not z.get("gotowy"):
        pomin("cała warstwa wykresu", z.get("powod", "brak przeglądarki")[:50])
        return

    s = wykres.stan()
    sprawdz("stan wykresu", "symbol" in s and "interwal" in s,
            f"{s.get('symbol')} {s.get('interwal')}")

    w = wykres.wartosci()
    sprawdz("wartości wskaźników", isinstance(w, list), f"{len(w)} wskaźników")

    c = wykres.swiece(20)
    sprawdz("świece", c.get("zwrocono", 0) > 0, f"{c.get('zwrocono')} świec")
    if c.get("swiece"):
        pierwsza = c["swiece"][0]
        sprawdz("świeca ma komplet pól",
                all(k in pierwsza for k in ("czas", "otwarcie", "szczyt", "dolek", "zamkniecie")))


def kompletnosc_serwera():
    """Czy każde zadeklarowane narzędzie ma obsługę w serwerze.

    Zmierzone raz: narzędzie potrafi być w spisie, a wywołanie zwraca „nieznane
    narzędzie", bo lista kierująca go nie obejmuje. Nic tego nie sygnalizuje —
    spis wygląda kompletnie, testy ścieżkowe przechodzą.

    Tu sprawdzamy sam rozdział wywołań, bez dotykania rynku, żeby test był szybki.
    """
    import asyncio

    import serwer

    print("\nkompletność serwera")

    async def zbierz():
        return [n.name for n in await serwer.lista_narzedzi()]

    nazwy = asyncio.run(zbierz())
    sprawdz("spis narzędzi niepusty", len(nazwy) > 0, f"{len(nazwy)} narzędzi")

    async def bez_obslugi():
        brak = []
        for n in nazwy:
            odp = await serwer.wywolaj(n, {})
            tresc = odp[0].text
            if "nieznane narzędzie" in tresc:
                brak.append(n)
        return brak

    brak = asyncio.run(bez_obslugi())
    sprawdz("każde narzędzie ma obsługę", not brak,
            "wszystkie" if not brak else f"BEZ OBSŁUGI: {', '.join(brak)}")


def main():
    print("Sprawdzenie VGM MCP")
    for f in (dane_i_pola, rynki, analiza_, pine_, wykres_, kompletnosc_serwera):
        try:
            f()
        except Exception as e:
            OBLANE.append((f.__name__, f"{type(e).__name__}: {e}"))
            print(f"  BŁĄD  {f.__name__}: {type(e).__name__}: {str(e)[:60]}")

    print(f"\nzaliczone {len(ZALICZONE)} · oblane {len(OBLANE)} · pominięte {len(POMINIETE)}")
    if OBLANE:
        print("\noblane:")
        for n, s in OBLANE:
            print(f"  {n}  {s}")
    return 1 if OBLANE else 0


if __name__ == "__main__":
    sys.exit(main())
