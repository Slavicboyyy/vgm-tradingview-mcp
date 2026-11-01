#!/usr/bin/env python3
"""vgm — TradingView z terminala. Te same narzędzia co serwer MCP, bez klienta MCP.

    vgm odczyt FX:EURUSD                 cena i wskaźniki
    vgm obraz FX:EURUSD                  wszystkie 91 pól
    vgm polozenie FX:EURUSD              miejsce ceny względem odniesień
    vgm mtf FX:EURUSD                    wskaźnik na kilku przedziałach
    vgm zgodnosc FX:EURUSD               ile przedziałów mówi to samo
    vgm porownaj FX:EURUSD FX:GBPUSD     instrumenty obok siebie
    vgm skan trend                       przegląd rynku
    vgm pine plik.pine                   sprawdzenie kodu Pine (plik z VGM_KATALOG_PINE)
    vgm wykres stan                      co jest na wykresie
    vgm wykres symbol FX:EURUSD          zmiana instrumentu
    vgm wykres zrzut                     obraz wykresu do pliku
    vgm swiece 200                       świece z wykresu
    vgm wszystko FX:EURUSD               pełny obraz: pola, położenie, wykres

Dodaj --json, żeby dostać surowy wynik zamiast tabelki.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))


def wypisz(x, jako_json=False):
    if jako_json:
        print(json.dumps(x, ensure_ascii=False, indent=1))
        return

    if isinstance(x, dict):
        for k, v in x.items():
            if isinstance(v, dict):
                print(f"{k}:")
                for kk, vv in v.items():
                    print(f"   {kk:26} {vv}")
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                print(f"{k}: {len(v)} pozycji")
                for poz in v[:8]:
                    print("   " + "  ".join(f"{a}={b}" for a, b in poz.items()))
            else:
                print(f"{k:28} {v}")
    elif isinstance(x, list):
        for poz in x[:40]:
            if isinstance(poz, dict):
                print("  " + "  ".join(f"{a}={b}" for a, b in poz.items()))
            else:
                print(f"  {poz}")
    else:
        print(x)


def main():
    p = argparse.ArgumentParser(
        prog="vgm", description="TradingView z terminala",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--json", action="store_true", help="surowy wynik zamiast tabelki")
    pod = p.add_subparsers(dest="cmd")

    for nazwa, opis in [("odczyt", "cena i wskaźniki"), ("obraz", "wszystkie 91 pól"),
                        ("polozenie", "miejsce ceny względem odniesień"),
                        ("srednie", "układ średnich"), ("mtf", "wskaźnik na kilku przedziałach"),
                        ("zgodnosc", "ile przedziałów mówi to samo")]:
        s = pod.add_parser(nazwa, help=opis)
        s.add_argument("symbol")
        if nazwa in ("obraz", "polozenie", "srednie"):
            s.add_argument("--interwal")

    s = pod.add_parser("wszystko", help="pelny obraz instrumentu")
    s.add_argument("symbol")

    s = pod.add_parser("porownaj", help="instrumenty obok siebie")
    s.add_argument("symbole", nargs="+")

    s = pod.add_parser("skan", help="przegląd rynku")
    s.add_argument("rodzaj", choices=["wyprzedane", "wykupione", "trend", "wolumen"])
    s.add_argument("--rynek", default="forex")
    s.add_argument("--ile", type=int, default=15)

    s = pod.add_parser("pine", help="sprawdzenie kodu Pine")
    s.add_argument("plik")

    s = pod.add_parser("wykres", help="sterowanie wykresem")
    s.add_argument("co", choices=["stan", "zdrowie", "wartosci", "symbol",
                                  "interwal", "zrzut", "wskazniki"])
    s.add_argument("wartosc", nargs="?")

    s = pod.add_parser("swiece", help="świece z wykresu")
    s.add_argument("ile", type=int, nargs="?", default=50)
    s.add_argument("--statystyka", action="store_true")

    pod.add_parser("pola", help="spis dostępnych pól")

    a = p.parse_args()
    if not a.cmd:
        p.print_help()
        return 0

    import analiza
    import dane
    import pola as _pola

    try:
        if a.cmd == "odczyt":
            wypisz(dane.odczyt(a.symbol), a.json)
        elif a.cmd == "obraz":
            wypisz(analiza.obraz(a.symbol, a.interwal), a.json)
        elif a.cmd == "polozenie":
            wypisz(analiza.polozenie(a.symbol, a.interwal), a.json)
        elif a.cmd == "srednie":
            wypisz(analiza.uklad_srednich(a.symbol, a.interwal), a.json)
        elif a.cmd == "mtf":
            wypisz(dane.mtf(a.symbol), a.json)
        elif a.cmd == "zgodnosc":
            wypisz(dane.zgodnosc(a.symbol), a.json)
        elif a.cmd == "wszystko":
            wypisz(analiza.obraz_pelny(a.symbol), a.json)
        elif a.cmd == "porownaj":
            wypisz(analiza.porownaj(a.symbole), a.json)
        elif a.cmd == "pola":
            wypisz(dict(_pola.GRUPY), a.json)
        elif a.cmd == "skan":
            f = {"wyprzedane": analiza.skan_wyprzedane, "wykupione": analiza.skan_wykupione,
                 "trend": analiza.skan_silny_trend, "wolumen": analiza.skan_wolumen}[a.rodzaj]
            wypisz(f(a.rynek, ile=a.ile), a.json)
        elif a.cmd == "pine":
            import pine
            w = pine.sprawdz_plik(a.plik)
            if a.json:
                wypisz(w, True)
            elif w["poprawny"]:
                print(f"{a.plik}: kod poprawny")
            else:
                print(f"{a.plik}: {len(w['bledy'])} błędów\n")
                print(w.get("podglad", ""))
                return 1
        elif a.cmd == "swiece":
            if a.statystyka:
                wypisz(analiza.statystyka_swiec(a.ile), a.json)
            else:
                import wykres
                wypisz(wykres.swiece(a.ile), a.json)
        elif a.cmd == "wykres":
            import wykres
            if a.co == "symbol":
                wypisz(wykres.ustaw_symbol(a.wartosc), a.json)
            elif a.co == "interwal":
                wypisz(wykres.ustaw_interwal(a.wartosc), a.json)
            elif a.co == "zrzut":
                wypisz(wykres.zrzut(a.wartosc), a.json)
            else:
                wypisz(getattr(wykres, {"stan": "stan", "zdrowie": "zdrowie",
                                        "wartosci": "wartosci",
                                        "wskazniki": "wskazniki"}[a.co])(), a.json)
        return 0

    except Exception as e:
        print(f"BŁĄD: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
