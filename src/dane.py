#!/usr/bin/env python3
"""VGM MCP — warstwa danych. Czyta TradingView bez logowania i bez przeglądarki.

Opiera się na publicznym punkcie `scanner.tradingview.com`, tym samym, z którego
korzysta strona. Zwraca wartości wskaźników policzone po stronie TradingView,
więc nie musimy ich liczyć u siebie ani trzymać otwartego okna.

Zasady, których ten moduł pilnuje sam:
- odstęp między zapytaniami (domyślnie 1,2 s) — nie zalewamy serwera,
- twarde zatrzymanie przy 403 i 429 zamiast ponawiania,
- nagłówek `curl/8.5.0`, bo domyślny nagłówek Pythona bywa odrzucany.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

PODSTAWA = "https://scanner.tradingview.com"
NAGLOWKI = {"User-Agent": "curl/8.5.0", "Accept": "application/json"}
ODSTEP_S = 1.2

# Pola, które TradingView liczy po swojej stronie. Nazwy są ich, nie nasze —
# zostawiamy oryginalne, żeby dało się je porównać z dokumentacją.
POLA_CENA = ["close", "open", "high", "low", "change", "change_abs", "volume"]
POLA_WSKAZNIKI = [
    "RSI", "RSI7", "Stoch.K", "Stoch.D", "CCI20", "ADX", "AO", "Mom",
    "MACD.macd", "MACD.signal", "ATR", "BB.upper", "BB.lower",
    "SMA5", "SMA10", "SMA20", "SMA50", "SMA100", "SMA200",
    "EMA5", "EMA10", "EMA20", "EMA50", "EMA100", "EMA200",
    "VWMA", "HullMA9", "Pivot.M.Classic.S1", "Pivot.M.Classic.R1",
]
POLA_OCENA = ["Recommend.All", "Recommend.MA", "Recommend.Other"]

_ostatnie = 0.0


class BladTV(Exception):
    """Cokolwiek, co uniemożliwia odczyt — z czytelnym powodem."""


def _odczekaj():
    global _ostatnie
    minelo = time.time() - _ostatnie
    if minelo < ODSTEP_S:
        time.sleep(ODSTEP_S - minelo)
    _ostatnie = time.time()


def _pobierz(sciezka: str, dane: dict | None = None, prob: int = 2):
    """Jedno zapytanie. Przy 403/429 przerywa — nie ponawia."""
    url = f"{PODSTAWA}{sciezka}"
    ciało = json.dumps(dane).encode() if dane is not None else None
    naglowki = dict(NAGLOWKI)
    if ciało:
        naglowki["Content-Type"] = "application/json"

    for i in range(prob):
        _odczekaj()
        req = urllib.request.Request(url, data=ciało, headers=naglowki)
        try:
            with urllib.request.urlopen(req, timeout=25) as o:
                return json.loads(o.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise BladTV(
                    f"TradingView odmówił ({e.code}). Zatrzymuję się — "
                    "ponawianie przy tym kodzie prowadzi do blokady adresu."
                ) from e
            if i == prob - 1:
                raise BladTV(f"HTTP {e.code} przy {sciezka}") from e
            time.sleep(2 * (i + 1))
        except Exception as e:
            if i == prob - 1:
                raise BladTV(f"{type(e).__name__}: {e}") from e
            time.sleep(2 * (i + 1))
    raise BladTV("nie udało się pobrać")


def odczyt(symbol: str, pola: list[str] | None = None) -> dict:
    """Bieżące wartości dla jednego instrumentu.

    symbol: pełna nazwa z giełdą, np. "FX:EURUSD", "NASDAQ:NVDA", "COINBASE:BTCUSD".
    pola:   lista pól TradingView; domyślnie cena + najczęstsze wskaźniki.
    """
    pola = pola or (POLA_CENA + POLA_WSKAZNIKI[:12] + POLA_OCENA)
    zap = urllib.parse.urlencode({"symbol": symbol, "fields": ",".join(pola)})
    wynik = _pobierz(f"/symbol?{zap}")
    if not isinstance(wynik, dict) or not wynik:
        raise BladTV(f"brak danych dla {symbol} — sprawdź nazwę z giełdą, np. FX:EURUSD")
    return wynik


def wiele(symbole: list[str], pola: list[str] | None = None) -> list[dict]:
    """To samo dla wielu instrumentów naraz — jedno zapytanie zamiast wielu."""
    pola = pola or (POLA_CENA[:4] + ["RSI", "ADX", "Recommend.All"])
    dane = {"symbols": {"tickers": symbole}, "columns": pola}
    o = _pobierz("/forex/scan", dane)
    wynik = []
    for wiersz in o.get("data", []):
        wynik.append({"symbol": wiersz["s"], **dict(zip(pola, wiersz["d"]))})
    return wynik


def przeglad(rynek: str = "forex", warunki: list | None = None,
             pola: list[str] | None = None, ile: int = 30) -> list[dict]:
    """Przegląd rynku z filtrem.

    rynek:   "forex", "crypto", "america", "poland"…
    warunki: lista w formacie TradingView, np.
             [{"left": "RSI", "operation": "less", "right": 30}]
    """
    pola = pola or ["close", "change", "RSI", "ADX", "volume"]
    dane = {
        "filter": warunki or [],
        "columns": pola,
        "sort": {"sortBy": "change", "sortOrder": "desc"},
        "range": [0, ile],
    }
    o = _pobierz(f"/{rynek}/scan", dane)
    return [{"symbol": w["s"], **dict(zip(pola, w["d"]))} for w in o.get("data", [])]


def mtf(symbol: str, wskazniki: list[str] | None = None,
        interwaly: list[str] | None = None) -> dict:
    """Ten sam wskaźnik na kilku interwałach — jednym zapytaniem.

    TradingView przyjmuje sufiks przy nazwie pola: `RSI|60` to RSI z godzinowego.
    Zmierzone: `|1`, `|5`, `|15`, `|60`, `|240`, `|1W` działają bez logowania.

    Zwraca {wskaźnik: {interwał: wartość}} — gotowe do sprawdzania zgodności
    między interwałami, czyli tego, co w bocie nazywa się MTF.
    """
    wskazniki = wskazniki or ["RSI", "ADX", "Recommend.All"]
    interwaly = interwaly or ["5", "15", "60", "240"]

    pola = []
    for w in wskazniki:
        for i in interwaly:
            pola.append(f"{w}|{i}" if i else w)
    surowe = odczyt(symbol, pola)

    wynik: dict[str, dict[str, float | None]] = {w: {} for w in wskazniki}
    for klucz, wartosc in surowe.items():
        if "|" in klucz:
            w, i = klucz.split("|", 1)
        else:
            w, i = klucz, "biezacy"
        if w in wynik:
            wynik[w][i] = wartosc
    return wynik


def zgodnosc(symbol: str, interwaly: list[str] | None = None,
             prog_kupno: float = 55, prog_sprzedaz: float = 45) -> dict:
    """Czy interwały mówią to samo — surowiec dla bramki wejścia.

    Nie podejmuje decyzji, tylko liczy. Próg i sposób łączenia należą do silnika,
    bo to one wymagają pomiaru, a nie ten odczyt.
    """
    interwaly = interwaly or ["5", "15", "60", "240"]
    dane = mtf(symbol, ["RSI"], interwaly)["RSI"]

    kupno = [i for i, v in dane.items() if v is not None and v >= prog_kupno]
    sprzedaz = [i for i, v in dane.items() if v is not None and v <= prog_sprzedaz]
    brak = [i for i in interwaly if dane.get(i) is None]

    return {
        "symbol": symbol,
        "rsi": dane,
        "za_kupnem": sorted(kupno),
        "za_sprzedaza": sorted(sprzedaz),
        "bez_danych": sorted(brak),
        "wszystkie_zgodne": len(kupno) == len(interwaly) or len(sprzedaz) == len(interwaly),
    }


def _demo():
    """Sprawdzenie na żywych danych — uruchom ten plik wprost."""
    print("1. odczyt jednego instrumentu")
    d = odczyt("FX:EURUSD", ["close", "change", "RSI", "SMA50", "ATR", "Recommend.All"])
    for k, v in d.items():
        print(f"   {k:16} {v}")

    print("\n2. kilka instrumentów jednym zapytaniem")
    for w in wiele(["FX:EURUSD", "FX:GBPUSD", "FX:USDJPY"]):
        print(f"   {w['symbol']:14} close={w.get('close')} RSI={w.get('RSI')}")

    print("\n3. przegląd rynku — wyprzedane pary (RSI < 35)")
    for w in przeglad("forex", [{"left": "RSI", "operation": "less", "right": 35}], ile=5):
        print(f"   {w['symbol']:14} RSI={w.get('RSI')} zmiana={w.get('change')}")

    print("\n4. wiele interwałów jednym zapytaniem")
    for w, poz in mtf("FX:EURUSD", ["RSI", "ADX"], ["5", "15", "60", "240"]).items():
        opis = "  ".join(f"{i}m={v:.1f}" if v else f"{i}m=brak" for i, v in sorted(poz.items(), key=lambda x: int(x[0])))
        print(f"   {w:16} {opis}")

    print("\n5. zgodność interwałów — surowiec dla bramki")
    z = zgodnosc("FX:EURUSD")
    print(f"   za kupnem:    {z[chr(39)+chr(122)+chr(97)+chr(95)+chr(107)+chr(117)+chr(112)+chr(110)+chr(101)+chr(109)+chr(39)] if False else z["za_kupnem"]}")
    print(f"   za sprzedażą: {z["za_sprzedaza"]}")
    print(f"   wszystkie zgodne: {z["wszystkie_zgodne"]}")

    print("\n6. obsługa błędu — zła nazwa")
    try:
        odczyt("TO-NIE-ISTNIEJE")
        print("   BŁĄD: powinno rzucić wyjątek")
    except BladTV as e:
        print(f"   poprawnie zatrzymane: {str(e)[:70]}")


if __name__ == "__main__":
    _demo()
