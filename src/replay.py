#!/usr/bin/env python3
"""VGM MCP — odtwarzanie historii (replay) na wykresie TradingView.

Wykres cofa się do wybranej daty i idzie świeca po świecy. W tym trybie
TradingView pozwala też otwierać pozycje papierowe, więc da się przejść
strategię ręcznie i zobaczyć wynik bez ryzyka.

Zmierzone na koncie pro_premium przez CDP (port 9333): `_replayApi` daje
38 metod. Działają: selectDate, doStep, toggleAutoplay, changeAutoplayDelay,
stopReplay, showReplayToolbar.

Czego tu nie ma i dlaczego: pozycji papierowych. `buy(1)` zwraca `undefined`,
a `position()` i `realizedPL()` zostają puste, także przy otwartym panelu
Replay Trading (495 px, nagłówek widoczny). Wygląda na to, że wymaga
kliknięcia w interfejsie, którego nie chcę udawać po cichu na cudzym koncie.

Uwaga o czym pamiętać: tryb odtwarzania zmienia to, co widzi użytkownik
na wykresie. Każda funkcja mówi wprost, w jakim stanie zostawia wykres,
a `stop` wraca do czasu rzeczywistego.
"""
from __future__ import annotations

import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import walidacja as wal  # noqa: E402
import wykres  # noqa: E402
from typy import Json, Swieca  # noqa: E402


class BladReplay(Exception):
    """Odtwarzanie niedostępne albo wywołanie odrzucone."""


# Wszystkie odczyty idą przez ten sam rozpakowywacz: część metod zwraca
# wartość wprost, część obiekt z metodą value().
_PROLOG = """var api=window.TradingViewApi, r=api._replayApi;
var wv=function(x){ try{ return (x&&typeof x.value==='function')?x.value():x; }catch(e){ return null; } };
"""


def _ostatnia_swieca() -> Swieca | None:
    """Ostatnia świeca z wykresu albo None.

    Bywa, że wykres nie ma ani jednej: odtwarzanie od początku historii
    na krótkim przedziale zostawia puste okno, dopóki nie zrobi się kroku
    (zmierzone na EURUSD 3 min od 2001-11-28).
    """
    try:
        s: list[Swieca] = wykres.swiece(2).get("swiece") or []
        return s[-1] if s else None
    except Exception:
        return None


def _r(kod: str, czekaj: float = 30) -> Any:
    return wykres.uruchom(_PROLOG, kod, czekaj, BladReplay)


def _na_milisekundy(data: str | float) -> int:
    """Przyjmuje 'YYYY-MM-DD', datę z godziną albo liczbę sekund.

    Zwraca milisekundy, bo `selectDate` liczy w milisekundach: podanie
    sekund wrzuca wykres na pierwszą dostępną świecę w historii
    (zmierzone: EURUSD skakał na 2001-11-28 zamiast na podaną datę).
    """
    if isinstance(data, bool):
        raise BladReplay("nie rozumiem daty: wartość logiczna")
    if isinstance(data, (int, float)):
        if not math.isfinite(data) or not 0 <= data <= 4_102_444_800:   # do roku 2100
            raise BladReplay(f"data poza zakresem: {data}")
        return int(data) * 1000
    t = str(data).strip()[:32]
    if t.isdigit():             # przez MCP liczba sekund przychodzi jako tekst
        return _na_milisekundy(int(t))
    for wzor in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(t, wzor).replace(tzinfo=timezone.utc).timestamp()) * 1000
        except ValueError:
            continue
    raise BladReplay(f"nie rozumiem daty: {data} — podaj YYYY-MM-DD albo sekundy")


def stan() -> Json:
    """Stan odtwarzania: czy dostępne, czy trwa, na której świecy stoi.

    Zwraca też pozycję papierową i wynik zrealizowany, gdy jakaś jest.
    """
    w: Json = _r("""var o={dostepne:!!wv(r.isReplayAvailable()), trwa:!!wv(r.isReplayStarted()),
      autoodtwarzanie:!!wv(r.isAutoplayStarted()), gotowe_do_gry:!!wv(r.isReadyToPlay()),
      pasek_widoczny:!!wv(r.isReplayToolbarVisible()), opoznienie:wv(r.autoplayDelay()),
      tryb:String(wv(r.replayMode())||''), historia_od:wv(r.getReplayDepth())};
    var d=wv(r.getReplaySelectedDate());
    o.wybrana_data=d?(new Date((String(d).length>11?d:d*1000))).toISOString().slice(0,16).replace('T',' '):null;
    var p=wv(r.position()); o.pozycja=p?{ilosc:p.qty||p.size||null, cena:p.avgPrice||p.price||null}:null;
    o.wynik=wv(r.realizedPL()); o.waluta=wv(r.currency());
    if(o.historia_od) o.historia_od=(new Date(o.historia_od*1000)).toISOString().slice(0,10);
    return o;""")
    if w.get("trwa"):
        # Gdzie realnie stoi odtwarzanie widać po ostatniej świecy na wykresie.
        # getReplaySelectedDate zwraca datę STARTU i nie rusza się przy krokach
        # (zmierzone: trzy kroki, ta sama wartość, a wykres urósł o trzy świece).
        ost = _ostatnia_swieca()
        if ost:
            w["stoi_na"] = datetime.fromtimestamp(ost["czas"], timezone.utc).strftime("%Y-%m-%d %H:%M")
            w["ostatnie_zamkniecie"] = ost["zamkniecie"]
        else:
            w["stoi_na"] = None
            w["uwaga_swiece"] = "wykres jeszcze nie ma świec — zrób krok albo wybierz późniejszą datę"
    return w


def start(data: str | float | None = None, czekaj_s: float = 20) -> Json:
    """Włącza odtwarzanie od podanej daty. Zostawia wykres w trybie odtwarzania.

    `data` pominięta = pierwsza dostępna świeca w historii instrumentu.
    Przyjmuje 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM' albo liczbę sekund.
    """
    if not stan()["dostepne"]:
        raise BladReplay("odtwarzanie niedostępne dla tego instrumentu lub przedziału")

    if data is None:
        wyw = "r.selectFirstAvailableDate();"
    else:
        wyw = f"r.selectDate({_na_milisekundy(data)});"
    _r("r.showReplayToolbar(); " + wyw + " return 1;")

    koniec = time.time() + czekaj_s
    while time.time() < koniec:
        s = stan()
        if s["trwa"]:
            return {**s, "uwaga": "wykres jest w trybie odtwarzania — wyjście przez vgm_replay_stop"}
        time.sleep(1)
    raise BladReplay(f"odtwarzanie nie wystartowało w {czekaj_s:.0f} s")


def krok(ile: int = 1) -> Json:
    """Przesuwa odtwarzanie o `ile` świec do przodu."""
    if not stan()["trwa"]:
        raise BladReplay("odtwarzanie nie trwa — najpierw vgm_replay_start")
    try:
        ile = wal.calkowita(ile, "ile", 1, 500)
    except wal.BladWejscia as e:
        raise BladReplay(str(e)) from e
    p = _ostatnia_swieca()
    przed = p["czas"] if p else None
    _r(f"for(var i=0;i<{ile};i++) r.doStep(); return 1;", czekaj=max(30, ile * 0.2))
    time.sleep(min(4, 1.0 + ile * 0.05))
    s = stan()
    q = _ostatnia_swieca()
    po = q["czas"] if q else None
    return {**s, "krokow": ile, "ruszyl": po is not None and po != przed}


def autoplay(wlacz: bool = True, opoznienie_ms: int | None = None) -> Json:
    """Włącza lub wyłącza samoczynne przesuwanie świec.

    `opoznienie_ms` bierze się z listy TradingView; 100 znaczy dziesięć
    świec na sekundę, większa liczba to wolniej.
    """
    s = stan()
    if not s["trwa"]:
        raise BladReplay("odtwarzanie nie trwa — najpierw vgm_replay_start")
    if opoznienie_ms is not None:
        try:
            opoznienie_ms = wal.calkowita(opoznienie_ms, "opoznienie_ms", 50, 60_000)
        except wal.BladWejscia as e:
            raise BladReplay(str(e)) from e
        _r(f"r.changeAutoplayDelay({opoznienie_ms}); return 1;")
    if bool(wlacz) != s["autoodtwarzanie"]:
        _r("r.toggleAutoplay(); return 1;")
    time.sleep(1)
    return stan()



def stop() -> Json:
    """Kończy odtwarzanie i wraca do czasu rzeczywistego."""
    s = stan()
    if not s["trwa"]:
        return {**s, "uwaga": "odtwarzanie już nie trwało"}
    if s["autoodtwarzanie"]:
        _r("r.toggleAutoplay(); return 1;")
        time.sleep(1)
    _r("r.stopReplay(); return 1;")
    time.sleep(2)
    _r("if(wv(r.isReplayToolbarVisible())) r.hideReplayToolbar(); return 1;")
    return {**stan(), "uwaga": "wykres wrócił do czasu rzeczywistego"}


if __name__ == "__main__":
    print("stan:", stan())
