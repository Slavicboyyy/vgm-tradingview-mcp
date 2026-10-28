#!/usr/bin/env python3
"""VGM MCP — układ wykresów: kilka wykresów obok siebie w jednym oknie.

TradingView potrafi podzielić okno na 2, 3, 4, 6 albo 8 wykresów. Każdy ma
własny instrument i przedział, więc da się patrzeć na ten sam rynek w kilku
przedziałach naraz albo porównać kilka instrumentów bez przełączania.

Zmierzone na koncie pro_premium przez CDP (port 9333): `layout`, `setLayout`,
`chartsCount`, `activeChartIndex`, `setActiveChart` po stronie API strony,
plus `paneWidgets` dla paneli wewnątrz jednego wykresu (cena, wskaźniki).

Czego tu nie ma i dlaczego: zapisu układu na konto. `_saveChartService` daje
`saveChartAs` i `saveNewChart`, ale nie ma w nim metody kasowania — każdy test
zostawiłby śmieć na koncie użytkownika, a bez testu na żywo nic nie wchodzi do
serwera. `stan` mówi tylko, czy układ ma niezapisane zmiany.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wykres  # noqa: E402
from typy import Json  # noqa: E402

# Kody układów TradingView. Pierwsza litera to liczba wykresów, reszta opisuje
# podział. 's' znaczy jeden wykres na całe okno.
UKLADY: dict[str, str] = {
    "s": "jeden wykres",
    "2h": "dwa obok siebie w poziomie",
    "2v": "dwa jeden nad drugim",
    "2-1": "dwa u góry, jeden pod nimi",
    "3h": "trzy w poziomie",
    "3v": "trzy w pionie",
    "4": "cztery, dwa na dwa",
    "6": "sześć, trzy na dwa",
    "8": "osiem, cztery na dwa",
}


class BladUkladu(Exception):
    """Układ odrzucił wywołanie."""


_PROLOG = """var api=window.TradingViewApi;
var wv=function(x){ try{ return (x&&typeof x.value==='function')?x.value():x; }catch(e){ return null; } };
"""


def _u(kod: str, czekaj: float = 30) -> Any:
    return wykres.uruchom(_PROLOG, kod, czekaj, BladUkladu)


def stan() -> Json:
    """Jaki jest układ okna, ile jest wykresów i co na nich stoi.

    `paneli_w_wykresie` liczy panele wewnątrz aktywnego wykresu: pierwszy to
    cena, kolejne to wskaźniki w osobnych oknach (RSI, MACD).
    """
    w: Json = _u("""var o={uklad:String(wv(api.layout())||''), nazwa:String(wv(api.layoutName())||''),
      wykresow:wv(api.chartsCount()), aktywny:wv(api.activeChartIndex())};
    var cw=api._activeChartWidgetWV.value(), c=cw._chartWidget||cw;
    try{ o.paneli_w_wykresie=c.paneWidgets().length; }catch(e){ o.paneli_w_wykresie=null; }
    try{ o.niezapisane_zmiany=!!wv(api._saveChartService.hasChanges()); }catch(e){ o.niezapisane_zmiany=null; }
    return o;""")
    w["uklad_opis"] = UKLADY.get(w.get("uklad") or "", "nieznany")

    # Co stoi na poszczególnych wykresach czytamy przez przełączanie aktywnego
    # i odczyt stanu. `_chartWidgets` jest obiektem bez długości i bez kluczy
    # (zmierzone), więc nie da się po nim przejść pętlą.
    if (w.get("wykresow") or 1) > 1:
        byl = w.get("aktywny") or 0
        w["wykresy"] = []
        for i in range(w["wykresow"]):
            try:
                _u(f"api.setActiveChart({i}); return 1;")
                time.sleep(0.8)
                s = wykres.stan()
                w["wykresy"].append({"indeks": i, "symbol": s.get("symbol"),
                                     "interwal": s.get("interwal")})
            except Exception:
                w["wykresy"].append({"indeks": i, "symbol": None, "interwal": None})
        _u(f"api.setActiveChart({byl}); return 1;")
        time.sleep(0.5)
    return w


def ustaw(kod: str = "s") -> Json:
    """Dzieli okno na wykresy według kodu układu z `UKLADY`.

    Zmienia to, co widzi użytkownik. Zwracamy `zgodny`, bo TradingView
    przyjmuje wywołanie i przy nieobsługiwanym kodzie nic nie robi.
    """
    k = str(kod).strip()
    if k not in UKLADY:
        raise BladUkladu(f"nieznany układ: {kod} — dostępne: {', '.join(UKLADY)}")
    _u(f"api.setLayout({k!r}); return 1;")
    time.sleep(2.5)
    s = stan()
    return {**s, "zgodny": s.get("uklad") == k,
            "uwaga": "układ okna zmieniony — wróć przez vgm_uklad_ustaw z kodem s"}


def wybierz(indeks: int = 0) -> Json:
    """Ustawia, który z wykresów w układzie jest aktywny.

    Wszystkie narzędzia wykresu działają na aktywnym, więc to jest przełącznik
    dla `vgm_wykres_symbol`, `vgm_wskaznik_dodaj` i pozostałych.
    """
    i = int(indeks)
    s = stan()
    ile = s.get("wykresow") or 1
    if not 0 <= i < ile:
        raise BladUkladu(f"indeks {i} poza zakresem — wykresów jest {ile}")
    _u(f"api.setActiveChart({i}); return 1;")
    time.sleep(1.5)
    p = stan()
    return {**p, "zgodny": p.get("aktywny") == i}


def symbol_w_wykresie(indeks: int, symbol: str, interwal: str | None = None) -> Json:
    """Ustawia instrument na wybranym wykresie układu, nie na aktywnym.

    Robi to przez chwilowe przełączenie aktywnego wykresu, więc po wywołaniu
    aktywny zostaje ten, który zmieniliśmy.
    """
    wybierz(indeks)
    if interwal:
        wykres.przelacz(symbol, interwal)
    else:
        wykres.ustaw_symbol(symbol)
    time.sleep(1)
    s = wykres.stan()
    return {"indeks": indeks, "symbol": s.get("symbol"), "interwal": s.get("interwal"),
            "zgodny": symbol.split(":")[-1].upper() in str(s.get("symbol", "")).upper(),
            "uklad": stan()}


if __name__ == "__main__":
    print("stan:", stan())
