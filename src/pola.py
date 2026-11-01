#!/usr/bin/env python3
"""Pełna mapa pól TradingView — zmierzona, nie przepisana z dokumentacji.

Każde pole tutaj zostało odpytane i zwróciło wartość. Sprawdzenie:
`python3 src/pola.py` odpytuje wszystkie i wypisuje, które przestały działać.

Sufiks `|<interwał>` daje tę samą wartość z innego przedziału czasu,
np. `RSI|60` to RSI z godzinowego. Zmierzone interwały: 1, 5, 15, 60, 240, 1W.
"""
from __future__ import annotations

CENA = ["close", "open", "high", "low", "gap", "change", "change_abs", "VWAP"]

WOLUMEN = [
    "volume",
    "average_volume_10d_calc",
    "relative_volume_10d_calc",   # dzisiejszy wolumen do średniej — siła ruchu
]

PED = [                            # oscylatory pędu
    "RSI", "RSI7", "Stoch.K", "Stoch.D", "Stoch.RSI.K", "Stoch.RSI.D",
    "CCI20", "Mom", "AO", "ROC", "UO", "W.R",
    "MoneyFlow", "ChaikinMoneyFlow",
]

TREND = [
    "ADX", "ADX+DI", "ADX-DI",     # siła trendu i kierunek
    "MACD.macd", "MACD.signal", "MACD.hist",
    "P.SAR",
    "Aroon.Up", "Aroon.Down",
    # pełny Ichimoku: linia bazowa, konwersji i obie linie wyprzedzające
    "Ichimoku.BLine", "Ichimoku.CLine", "Ichimoku.Lead1", "Ichimoku.Lead2",
]

SREDNIE = [
    "SMA5", "SMA10", "SMA20", "SMA30", "SMA50", "SMA100", "SMA200",
    "EMA5", "EMA10", "EMA20", "EMA30", "EMA50", "EMA100", "EMA200",
    "VWMA", "HullMA9",
]

ZMIENNOSC = [
    "ATR", "BB.upper", "BB.lower", "BBPower",
    "Volatility.D", "Volatility.W", "Volatility.M",
    # kanały: Donchiana (skrajne ceny) i Keltnera (oparty na zmienności)
    "DonchCh20.Upper", "DonchCh20.Lower",
    "KltChnl.upper", "KltChnl.lower",
]

POZIOMY = [
    # cztery systemy punktów zwrotnych — każdy liczy je inaczej
    "Pivot.M.Classic.S1", "Pivot.M.Classic.R1",
    "Pivot.M.Fibonacci.S1", "Pivot.M.Fibonacci.R1",
    "Pivot.M.Woodie.S1", "Pivot.M.Camarilla.S1", "Pivot.M.Demark.S1",
    "price_52_week_high", "price_52_week_low",
]

WYNIK = ["Perf.W", "Perf.1M", "Perf.3M", "Perf.6M", "Perf.YTD", "Perf.Y", "Perf.5Y"]

OCENA = [
    "Recommend.All", "Recommend.MA", "Recommend.Other",
    # ocena osobno dla każdego wskaźnika: -1 sprzedaj, 0 neutralnie, 1 kupuj
    "Rec.Stoch.RSI", "Rec.WR", "Rec.BBPower", "Rec.UO",
    "Rec.Ichimoku", "Rec.VWMA", "Rec.HullMA9",
]

GRUPY = {
    "cena": CENA,
    "wolumen": WOLUMEN,
    "ped": PED,
    "trend": TREND,
    "srednie": SREDNIE,
    "zmiennosc": ZMIENNOSC,
    "poziomy": POZIOMY,
    "wynik": WYNIK,
    "ocena": OCENA,
}

WSZYSTKIE = [p for g in GRUPY.values() for p in g]

# Zestawy gotowe do użycia — żeby nie wypisywać pól za każdym razem.
ZESTAW = {
    "szybki": ["close", "change", "volume", "RSI", "ADX", "Recommend.All"],
    "ped": CENA[:4] + PED,
    "trend": CENA[:4] + TREND + ["EMA50", "EMA200"],
    "zmiennosc": CENA[:4] + ZMIENNOSC,
    "pelny": WSZYSTKIE,
}

# Rynki przyjmowane przez przegląd — sprawdzone 4 września 2026, wszystkie
# zwróciły wyniki. Nazwa idzie wprost do adresu zapytania.
RYNKI = {
    "forex": "pary walutowe",
    "crypto": "kryptowaluty",
    "coin": "kryptowaluty, inny zestaw",
    "america": "akcje amerykańskie",
    "poland": "GPW i NewConnect",
    "germany": "akcje niemieckie",
    "uk": "akcje brytyjskie",
    "japan": "akcje japońskie",
    "futures": "kontrakty terminowe",
    "cfd": "kontrakty na różnicę",
}

INTERWALY = ["1", "5", "15", "30", "60", "120", "240", "1W", "1M"]
# zmierzone jako działające na FX:EURUSD (2026-09-04):
INTERWALY_PEWNE = ["1", "5", "15", "60", "240", "1W"]


def _sprawdz() -> int:
    """Odpytuje wszystkie pola i mówi, które przestały działać."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import dane

    print(f"sprawdzam {len(WSZYSTKIE)} pól na FX:EURUSD\n")
    wynik = dane.odczyt("FX:EURUSD", WSZYSTKIE)

    for nazwa, grupa in GRUPY.items():
        dziala = [p for p in grupa if wynik.get(p) is not None]
        zle = [p for p in grupa if p in wynik and wynik[p] is None]
        brak = [p for p in grupa if p not in wynik]
        stan = "wszystko" if len(dziala) == len(grupa) else f"{len(dziala)}/{len(grupa)}"
        print(f"  {nazwa:11} {stan}")
        if zle:
            print(f"    puste:    {', '.join(zle)}")
        if brak:
            print(f"    nieznane: {', '.join(brak)}")

    razem = sum(1 for p in WSZYSTKIE if wynik.get(p) is not None)
    print(f"\ndziała {razem} z {len(WSZYSTKIE)}")
    return 0 if razem == len(WSZYSTKIE) else 1


if __name__ == "__main__":
    import sys

    sys.exit(_sprawdz())
