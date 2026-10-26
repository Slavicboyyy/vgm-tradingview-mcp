#!/usr/bin/env python3
"""VGM MCP — warstwa analizy. Liczy na danych z TradingView, nic nie zgaduje.

Każda funkcja zwraca liczby i to, z czego je policzono. Żadna nie mówi
"kupuj" ani "sprzedawaj" — bo próg, który zamienia liczbę w decyzję, wymaga
pomiaru na historii, a nie wpisania z głowy.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import time  # noqa: E402

import dane  # noqa: E402
import pola  # noqa: E402


def obraz(symbol: str, interwal: str | None = None) -> dict:
    """Pełny obraz instrumentu — 91 pól pogrupowanych tematycznie.

    Jedno zapytanie zamiast dziewięciu. Z `interwal` bierze wszystko
    z podanego przedziału czasu (np. "60" = godzinowy).
    """
    lista = [f"{p}|{interwal}" if interwal else p for p in pola.WSZYSTKIE]
    surowe = dane.odczyt(symbol, lista)

    czysto = {}
    for k, v in surowe.items():
        czysto[k.split("|")[0] if "|" in k else k] = v

    wynik = {"symbol": symbol, "interwal": interwal or "biezacy"}
    for nazwa, grupa in pola.GRUPY.items():
        wynik[nazwa] = {p: czysto.get(p) for p in grupa if czysto.get(p) is not None}
    return wynik


def polozenie(symbol: str, interwal: str | None = None) -> dict:
    """Gdzie stoi cena względem swoich odniesień — w procentach, nie na oko.

    Odpowiada na pytania, które inaczej trzeba liczyć ręcznie:
    gdzie w kanale Bollingera, jak daleko od średnich, jak blisko rocznych szczytów.
    """
    p = ["close", "BB.upper", "BB.lower", "EMA20", "EMA50", "EMA200",
         "price_52_week_high", "price_52_week_low", "ATR"]
    lista = [f"{x}|{interwal}" if interwal else x for x in p]
    s = dane.odczyt(symbol, lista)
    g = lambda k: s.get(f"{k}|{interwal}" if interwal else k)

    c = g("close")
    if c is None:
        raise dane.BladTV(f"brak ceny dla {symbol}")

    bg, bd = g("BB.upper"), g("BB.lower")
    rh, rl = g("price_52_week_high"), g("price_52_week_low")
    atr = g("ATR")

    def procent(dol, gora):
        if dol is None or gora is None or gora == dol:
            return None
        return round((c - dol) / (gora - dol) * 100, 1)

    def odchylenie(sr):
        if sr is None or not sr:
            return None
        return round((c - sr) / sr * 100, 2)

    return {
        "symbol": symbol,
        "interwal": interwal or "biezacy",
        "cena": c,
        "w_kanale_bollingera_proc": procent(bd, bg),
        "w_zakresie_rocznym_proc": procent(rl, rh),
        "nad_ema20_proc": odchylenie(g("EMA20")),
        "nad_ema50_proc": odchylenie(g("EMA50")),
        "nad_ema200_proc": odchylenie(g("EMA200")),
        "szerokosc_bollingera_proc": (
            round((bg - bd) / c * 100, 2) if bg and bd and c else None
        ),
        "atr_proc_ceny": round(atr / c * 100, 3) if atr and c else None,
    }


def uklad_srednich(symbol: str, interwal: str | None = None) -> dict:
    """Czy średnie są ułożone w kolejności — bez nazywania tego trendem.

    Zwraca surowy fakt: ile średnich stoi w kolejności rosnącej lub malejącej.
    To, czy taki układ cokolwiek zapowiada, jest do zmierzenia, nie do założenia.
    """
    kolejnosc = ["EMA5", "EMA10", "EMA20", "EMA50", "EMA100", "EMA200"]
    lista = [f"{x}|{interwal}" if interwal else x for x in kolejnosc + ["close"]]
    s = dane.odczyt(symbol, lista)
    g = lambda k: s.get(f"{k}|{interwal}" if interwal else k)

    war = [(n, g(n)) for n in kolejnosc]
    war = [(n, v) for n, v in war if v is not None]
    if len(war) < 2:
        raise dane.BladTV(f"za mało średnich dla {symbol}")

    rosnaco = sum(1 for i in range(len(war) - 1) if war[i][1] > war[i + 1][1])
    malejaco = sum(1 for i in range(len(war) - 1) if war[i][1] < war[i + 1][1])
    par = len(war) - 1

    return {
        "symbol": symbol,
        "interwal": interwal or "biezacy",
        "srednie": {n: v for n, v in war},
        "cena": g("close"),
        "par_w_kolejnosci_rosnacej": rosnaco,
        "par_w_kolejnosci_malejacej": malejaco,
        "par_razem": par,
        "uporzadkowane_w_pelni": rosnaco == par or malejaco == par,
    }


def zgodnosc_pelna(symbol: str, wskazniki: list[str] | None = None,
                   interwaly: list[str] | None = None) -> dict:
    """Zgodność wielu wskaźników na wielu interwałach — jednym zapytaniem.

    Rozszerzenie `dane.zgodnosc` na dowolny zestaw. Zwraca tabelę wartości
    i zliczenia, bez wyroku.
    """
    wskazniki = wskazniki or ["RSI", "ADX", "MACD.hist", "Recommend.All"]
    interwaly = interwaly or pola.INTERWALY_PEWNE[:4]

    lista = [f"{w}|{i}" for w in wskazniki for i in interwaly]
    s = dane.odczyt(symbol, lista)

    tabela: dict[str, dict[str, float | None]] = {w: {} for w in wskazniki}
    for k, v in s.items():
        if "|" in k:
            w, i = k.split("|", 1)
            if w in tabela:
                tabela[w][i] = v

    return {
        "symbol": symbol,
        "interwaly": interwaly,
        "wartosci": tabela,
        "brakujace": [f"{w}|{i}" for w in wskazniki for i in interwaly
                      if tabela[w].get(i) is None],
    }


def porownaj(symbole: list[str], pola_do: list[str] | None = None) -> list[dict]:
    """Kilka instrumentów obok siebie, posortowane po sile ruchu."""
    pola_do = pola_do or ["close", "change", "RSI", "ADX",
                          "relative_volume_10d_calc", "Recommend.All"]
    w = dane.wiele(symbole, pola_do)
    return sorted(w, key=lambda x: abs(x.get("change") or 0), reverse=True)


# ── gotowe skany rynku ──────────────────────────────────────────────────
def skan_wyprzedane(rynek: str = "forex", prog: float = 30, ile: int = 20):
    """Instrumenty z RSI poniżej progu."""
    return dane.przeglad(rynek, [{"left": "RSI", "operation": "less", "right": prog}],
                         ["close", "change", "RSI", "ADX", "volume"], ile)


def skan_wykupione(rynek: str = "forex", prog: float = 70, ile: int = 20):
    """Instrumenty z RSI powyżej progu."""
    return dane.przeglad(rynek, [{"left": "RSI", "operation": "greater", "right": prog}],
                         ["close", "change", "RSI", "ADX", "volume"], ile)


def skan_silny_trend(rynek: str = "forex", prog_adx: float = 30, ile: int = 20):
    """Instrumenty z ADX powyżej progu — silny ruch kierunkowy."""
    return dane.przeglad(rynek, [{"left": "ADX", "operation": "greater", "right": prog_adx}],
                         ["close", "change", "ADX", "ADX+DI", "ADX-DI", "RSI"], ile)


def skan_wolumen(rynek: str = "forex", krotnosc: float = 2.0, ile: int = 20):
    """Instrumenty z wolumenem powyżej wielokrotności średniej z 10 dni."""
    return dane.przeglad(
        rynek,
        [{"left": "relative_volume_10d_calc", "operation": "greater", "right": krotnosc}],
        ["close", "change", "volume", "relative_volume_10d_calc", "RSI"], ile)


def skan_wlasny(rynek: str, warunki: list[dict], pola_do: list[str] | None = None,
                ile: int = 30):
    """Dowolny filtr TradingView — pełna swoboda.

    Przykład: [{"left": "RSI", "operation": "less", "right": 30},
               {"left": "ADX", "operation": "greater", "right": 25}]
    """
    return dane.przeglad(rynek, warunki,
                         pola_do or ["close", "change", "RSI", "ADX", "volume"], ile)


# ── liczenie na świecach z wykresu ──────────────────────────────────────
def _swiece_z_wykresu(ile=0):
    """Pobiera świece z otwartego wykresu. Osobno, żeby reszta modułu
    działała bez przeglądarki.

    ile=0 znaczy: cała historia, jaką wykres ma wczytaną. Zmierzone: na złocie
    dziennym to 2518 świec, a domyślne 300 przez kilka iteracji obcinało
    dziesięć lat do jednego roku i dawało pozorne sygnały.
    """
    import wykres
    w = wykres.swiece(ile if ile and ile > 0 else 5000)
    return w["swiece"]


def statystyka_swiec(ile: int = 200) -> dict:
    """Liczby policzone na świecach z wykresu, bez zewnętrznego źródła danych.

    Zwraca surowe miary: rozpiętość, średni zasięg świecy, udział świec
    wzrostowych, największa luka. Nie ocenia ich — ocena wymaga pomiaru.
    """
    s = _swiece_z_wykresu(ile)
    if len(s) < 2:
        raise dane.BladTV("za mało świec do policzenia czegokolwiek")

    zamkniecia = [x["zamkniecie"] for x in s]
    zasiegi = [x["szczyt"] - x["dolek"] for x in s]
    wzrostowe = sum(1 for x in s if x["zamkniecie"] > x["otwarcie"])

    luki = []
    for i in range(1, len(s)):
        luka = s[i]["otwarcie"] - s[i - 1]["zamkniecie"]
        if luka:
            luki.append(abs(luka))

    najw, najn = max(zamkniecia), min(zamkniecia)
    ostatnia = zamkniecia[-1]

    return {
        "swiec": len(s),
        "od": s[0]["czas"],
        "do": s[-1]["czas"],
        "najwyzsze_zamkniecie": najw,
        "najnizsze_zamkniecie": najn,
        "ostatnie_zamkniecie": ostatnia,
        "w_zakresie_proc": round((ostatnia - najn) / (najw - najn) * 100, 1) if najw != najn else None,
        "sredni_zasieg": round(sum(zasiegi) / len(zasiegi), 6),
        "najwiekszy_zasieg": round(max(zasiegi), 6),
        "swiec_wzrostowych": wzrostowe,
        "udzial_wzrostowych_proc": round(wzrostowe / len(s) * 100, 1),
        "najwieksza_luka": round(max(luki), 6) if luki else 0,
        "zmiana_od_poczatku_proc": round((ostatnia - zamkniecia[0]) / zamkniecia[0] * 100, 3),
    }


def zmiennosc_swiec(ile: int = 200, okno: int = 20) -> dict:
    """Zmienność liczona w dwóch oknach — świeższym i wcześniejszym.

    Podział na dwie części to ta sama zasada, którą stosujemy przy każdym
    pomiarze: liczba z jednego okresu nic nie mówi, dopóki nie zobaczysz,
    czy powtarza się w drugim.
    """
    if okno < 1:
        raise dane.BladTV(f"okno musi być co najmniej 1, jest {okno}")
    s = _swiece_z_wykresu(ile)
    if len(s) < okno * 2:
        raise dane.BladTV(f"potrzeba co najmniej {okno * 2} świec, jest {len(s)}")

    def miara(czesc):
        z = [x["szczyt"] - x["dolek"] for x in czesc]
        c = [x["zamkniecie"] for x in czesc]
        sredni = sum(z) / len(z)
        return {
            "sredni_zasieg": round(sredni, 6),
            "sredni_zasieg_proc_ceny": round(sredni / (sum(c) / len(c)) * 100, 4),
            "zakres": round(max(c) - min(c), 6),
        }

    swiezsze = s[-okno:]
    wczesniejsze = s[-okno * 2:-okno]
    a, b = miara(swiezsze), miara(wczesniejsze)

    return {
        "okno": okno,
        "swiezsze": a,
        "wczesniejsze": b,
        "stosunek_zasiegow": round(a["sredni_zasieg"] / b["sredni_zasieg"], 3) if b["sredni_zasieg"] else None,
    }


def swiece_wiele_przedzialow(przedzialy: list[str] | None = None,
                             ile: int = 100) -> dict:
    """Statystyka świec z kilku przedziałów czasu, jeden po drugim.

    Przełącza wykres na każdy przedział, pobiera świece, liczy i wraca
    na przedział wyjściowy. Trwa kilka sekund na przedział, bo wykres
    musi wczytać dane.
    """
    import wykres

    przedzialy = przedzialy or ["15", "60", "240"]
    poczatkowy = wykres.stan()["interwal"]
    wynik = {}

    for p in przedzialy:
        try:
            wykres.ustaw_interwal(p)
            time.sleep(3.5)          # wykres potrzebuje chwili na dane
            wynik[p] = statystyka_swiec(ile)
        except Exception as e:
            wynik[p] = {"blad": str(e)[:90]}

    try:
        wykres.ustaw_interwal(poczatkowy)
        time.sleep(2)
    except Exception:
        pass

    return {"przedzial_wyjsciowy": poczatkowy, "wyniki": wynik}


def obraz_pelny(symbol: str) -> dict:
    """Wszystko, co wiemy o instrumencie, w jednym wywołaniu.

    Łączy dane publiczne (91 pól, cztery przedziały czasu) z tym, co widać
    na wykresie, gdy przeglądarka jest dostępna. Bez przeglądarki zwraca
    samą część publiczną i mówi o tym wprost.
    """
    wynik = {
        "symbol": symbol,
        "pola": obraz(symbol),
        "polozenie": polozenie(symbol),
        "srednie": uklad_srednich(symbol),
        "zgodnosc": zgodnosc_pelna(symbol),
    }

    try:
        import wykres

        z = wykres.zdrowie()
        if z.get("gotowy"):
            wynik["wykres"] = wykres.stan()
            wynik["wskazniki_z_wykresu"] = wykres.wartosci()
        else:
            wynik["wykres"] = {"niedostepny": z.get("powod", "brak przeglądarki")}
    except Exception as e:
        wynik["wykres"] = {"niedostepny": str(e)[:80]}

    return wynik


def _demo():
    print("1. pełny obraz — 91 pól w dziewięciu grupach")
    o = obraz("FX:EURUSD")
    for g, w in o.items():
        if isinstance(w, dict):
            print(f"   {g:11} {len(w)} pól")

    print("\n2. położenie ceny względem odniesień")
    for k, v in polozenie("FX:EURUSD").items():
        if k not in ("symbol", "interwal"):
            print(f"   {k:28} {v}")

    print("\n3. układ średnich")
    u = uklad_srednich("FX:EURUSD")
    print(f"   rosnąco {u['par_w_kolejnosci_rosnacej']}/{u['par_razem']}  "
          f"malejąco {u['par_w_kolejnosci_malejacej']}/{u['par_razem']}  "
          f"w pełni: {u['uporzadkowane_w_pelni']}")

    print("\n4. zgodność czterech wskaźników na czterech interwałach")
    z = zgodnosc_pelna("FX:EURUSD")
    for w, poz in z["wartosci"].items():
        opis = "  ".join(f"{i}={v:.1f}" if isinstance(v, (int, float)) else f"{i}=brak"
                         for i, v in poz.items())
        print(f"   {w:14} {opis}")

    print("\n5. porównanie par")
    for x in porownaj(["FX:EURUSD", "FX:GBPUSD", "FX:USDJPY", "FX:AUDUSD"]):
        print(f"   {x['symbol']:14} zmiana={x.get('change'):.3f}  RSI={x.get('RSI'):.1f}")

    print("\n6. skan silnego trendu (ADX > 30)")
    for x in skan_silny_trend(ile=4):
        print(f"   {x['symbol']:18} ADX={x.get('ADX'):.1f}  zmiana={x.get('change'):.2f}")


if __name__ == "__main__":
    _demo()
