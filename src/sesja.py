#!/usr/bin/env python3
"""VGM MCP — warstwa sesji. Funkcje dostępne tylko po zalogowaniu na TradingView.

Zmierzone na koncie pro_premium przez CDP aplikacji VGM Terminal (port 9333):
- alerty: 208 rekordów przez pricealerts.tradingview.com
- zapisane skrypty Pine: 59 przez pine-facade.tradingview.com
- lista obserwowanych: 29 symboli odczytanych z panelu wykresu

Alerty i skrypty idą zwykłym HTTP z ciasteczkami sesji — bez klikania w stronę.
Ciasteczka bierzemy z przeglądarki przez CDP, bo `sessionid` jest HttpOnly
i z JavaScriptu strony go nie widać. To był powód, dla którego wcześniejsze
sprawdzanie sesji przez `document.cookie` zawsze mówiło „brak".
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wykres  # noqa: E402
from typy import Json  # noqa: E402
from wspolne import ORIGIN_TV, REFERER_TV, UA_PRZEGLADARKI, odczekaj  # noqa: E402

ODSTEP_S = 1.2
_ostatnie = [0.0]


class BladSesji(Exception):
    """Brak sesji albo TradingView odmówił."""


def _odczekaj() -> None:
    odczekaj(_ostatnie, ODSTEP_S)


def ciasteczka() -> list[Json]:
    """Wszystkie ciasteczka TradingView z przeglądarki, łącznie z HttpOnly."""
    import websocket

    k = wykres._karta()
    ws = websocket.create_connection(k["webSocketDebuggerUrl"], timeout=30)
    try:
        ws.send(json.dumps({"id": 1, "method": "Network.getCookies",
                            "params": {"urls": ["https://www.tradingview.com"]}}))
        koniec = time.time() + 20
        while time.time() < koniec:
            o = json.loads(ws.recv())
            if o.get("id") == 1:
                cookies: list[Json] = o.get("result", {}).get("cookies", [])
                return cookies
    finally:
        ws.close()
    raise BladSesji("przeglądarka nie oddała ciasteczek w 20 s")


def czy_zalogowany() -> Json:
    """Czy w przeglądarce jest sesja TradingView — i jaki plan.

    Sprawdza dwie rzeczy niezależnie: ciasteczko `sessionid` (HttpOnly, przez CDP)
    oraz obiekt `window.user` na stronie. Zgodność obu daje pewność.
    """
    nazwy = {c["name"] for c in ciasteczka()}
    ma_sessionid = "sessionid" in nazwy

    u = wykres._wykonaj(
        "(function(){var u=window.user||(window.TradingView&&window.TradingView.user)"
        "||null; return u?{id:u.id,nazwa:u.username,plan:u.pro_plan||null}:null;})()")

    return {
        "zalogowany": bool(ma_sessionid and u and u.get("id")),
        "sessionid": ma_sessionid,
        "uzytkownik": (u.get("nazwa") or "")[:3] + "***" if u else None,
        "plan": u.get("plan") if u else None,
    }


def _naglowki() -> dict[str, str]:
    ck = ciasteczka()
    if not any(c["name"] == "sessionid" for c in ck):
        raise BladSesji("brak sesji TradingView w przeglądarce — zaloguj się")
    return {
        "Cookie": "; ".join(f"{c['name']}={c['value']}" for c in ck),
        "User-Agent": UA_PRZEGLADARKI,
        "Origin": ORIGIN_TV,
        "Referer": REFERER_TV,
        "Accept": "application/json",
    }


def _pobierz(url: str) -> Any:
    _odczekaj()
    zad = urllib.request.Request(url, headers=_naglowki())
    try:
        return json.loads(urllib.request.urlopen(zad, timeout=30).read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise BladSesji(f"TradingView odmówił ({e.code}) — sesja wygasła?") from e
        if e.code == 429:
            raise BladSesji("za dużo zapytań (429) — zatrzymuję się, nie ponawiam") from e
        raise BladSesji(f"HTTP {e.code} przy {url[:60]}") from e


def alerty() -> Json:
    """Wszystkie alerty cenowe z konta.

    Zmierzone: 208 alertów. Zwraca listę skróconą do pól, które coś znaczą.
    """
    d = _pobierz("https://pricealerts.tradingview.com/list_alerts")
    surowe = d.get("r", d) if isinstance(d, dict) else d
    if not isinstance(surowe, list):
        return {"ile": 0, "surowe": str(d)[:200]}

    def czysty_symbol(s: Any) -> Any:
        # TradingView koduje symbol alertu jako JSON z prefiksem "=",
        # np. ={"symbol":"ICMARKETS:USDCHF","session":"regular",...}
        if isinstance(s, str) and s.startswith("={"):
            try:
                return json.loads(s[1:]).get("symbol", s)
            except Exception:
                return s
        return s

    lista = []
    for a in surowe:
        lista.append({
            "id": a.get("alert_id") or a.get("id"),
            "symbol": czysty_symbol(a.get("symbol")),
            "nazwa": (a.get("name") or "")[:60],
            "aktywny": a.get("active"),
            "warunek": (a.get("condition") or {}).get("type") if isinstance(a.get("condition"), dict) else a.get("condition"),
            "interwal": a.get("resolution"),
        })
    return {"ile": len(lista), "alerty": lista}


def skrypty_pine() -> Json:
    """Skrypty Pine zapisane na koncie. Zmierzone: 59."""
    d = _pobierz("https://pine-facade.tradingview.com/pine-facade/list/?filter=saved")
    if not isinstance(d, list):
        return {"ile": 0, "surowe": str(d)[:200]}
    lista = [{
        "nazwa": (s.get("scriptName") or s.get("name") or "")[:60],
        "id": s.get("scriptIdPart"),
        "wersja": s.get("version"),
        "zmieniony": s.get("modified"),
    } for s in d]
    return {"ile": len(lista), "skrypty": lista}


def zrodlo_pine(id_skryptu: str) -> Json:
    """Kod źródłowy zapisanego skryptu po identyfikatorze z `skrypty_pine`."""
    d = _pobierz("https://pine-facade.tradingview.com/pine-facade/get/"
                 f"{urllib.parse.quote(id_skryptu, safe='')}/last")
    if isinstance(d, dict):
        return {"nazwa": d.get("scriptName"), "kod": d.get("source"),
                "wersja": d.get("version")}
    return {"surowe": str(d)[:300]}


def lista_obserwowanych() -> Json:
    """Instrumenty z listy obserwowanych otwartej w panelu wykresu.

    Czyta z panelu, nie z HTTP — TradingView nie wystawia tego prosto.
    Zmierzone: 29 symboli z listy „Forex".
    """
    w: Json = wykres._wykonaj("""(function(){
      var panel=document.querySelector('[class*="layout__area--right"]');
      if(!panel) return {blad:'panel prawy nie jest otwarty'};
      var el=panel.querySelectorAll('[data-symbol-full]');
      var lista=Array.from(el).map(function(e){return e.getAttribute('data-symbol-full');});
      var n=panel.querySelector('[class*="title"]');
      return {nazwa:n?n.innerText.slice(0,40):null, ile:lista.length, symbole:lista};
    })()""")
    if isinstance(w, dict) and "blad" in w:
        raise BladSesji(w["blad"])
    return w


def strategie_wbudowane() -> Json:
    """Wbudowane strategie TradingView. Zmierzone: 20 z 145 wbudowanych skryptów."""
    d = _pobierz("https://pine-facade.tradingview.com/pine-facade/list/?filter=standard")
    if not isinstance(d, list):
        return {"ile": 0, "surowe": str(d)[:200]}
    st = [{"nazwa": s.get("scriptName"), "id": s.get("scriptIdPart")}
          for s in d if "strateg" in ((s.get("scriptName") or "") + (s.get("scriptTitle") or "")).lower()]
    return {"wbudowanych": len(d), "strategii": len(st), "strategie": st}


def _pine_api(kod_js: str, czekaj: float = 60) -> Any:
    """Wywołuje pineEditorApi strony. Zmierzone sygnatury:
    saveNewScript({source,name}), saveExistingScript({scriptIdPart,source,name}),
    getSource(id,'last'), deleteScript(id), listSavedScripts()."""
    return wykres._wykonaj(
        "(async function(){var api=window.TradingViewApi;"
        "var p=api.pineEditorApi.call(api);" + kod_js + "})()", czekaj=czekaj)


def zapisz_pine(kod: str, nazwa: str) -> Json:
    """Zapisuje nowy skrypt Pine na koncie. Zmierzone: lista rośnie o jeden,
    zwraca success i identyfikator."""
    k, n = json.dumps(kod), json.dumps(nazwa)
    w: Json = _pine_api(f"var r=await p.saveNewScript({{source:{k},name:{n}}});"
                  "var l=await p.listSavedScripts();"
                  f"var t=l.filter(function(x){{return x.scriptName==={n}}});"
                  "return {zapisany:!!(r&&r.success), id:t.length?t[t.length-1].scriptIdPart:null, "
                  "zapisanych_teraz:l.length};")
    if isinstance(w, dict) and "blad" in w:
        raise BladSesji(w["blad"])
    return w


def usun_pine(id_skryptu: str) -> Json:
    """Usuwa zapisany skrypt po identyfikatorze z `skrypty_pine`."""
    i = json.dumps(id_skryptu)
    w: Json = _pine_api(f"var r=await p.deleteScript({i}); var l=await p.listSavedScripts();"
                  "return {usuniety:String(r)==='ok'||r===undefined||!!(r&&r.success), zapisanych_teraz:l.length};")
    if isinstance(w, dict) and "blad" in w:
        raise BladSesji(w["blad"])
    return w


def tester_raport() -> Json:
    """Otwiera Strategy Tester i czyta raport strategii, która jest na wykresie.

    Zmierzone: panel otwiera się przez bottomWidgetBar.open('backtesting'),
    raport jest tekstem panelu dolnego. Bez strategii na wykresie TradingView
    pisze, że raport wymaga choć jednej transakcji — to też zwracamy wprost.

    Wbudowanych strategii nie da się dodać przez createStudy (sprawdzone
    trzema nazwami) — na wykresie musi być własna strategia użytkownika.
    """
    wykres._wykonaj("(function(){window.TradingView.bottomWidgetBar.open('backtesting');return 1;})()")
    time.sleep(5)
    w: Json = wykres._wykonaj("""(function(){
      var d=document.querySelector('[class*="layout__area--bottom"]');
      var linie=d?d.innerText.split(String.fromCharCode(10)).map(function(x){return x.trim()}).filter(Boolean):[];
      var st=window.TradingViewApi._activeChartWidgetWV.value().getAllStudies()
             .map(function(s){return s.name||s.title||''}).filter(function(n){return /strateg/i.test(n)});
      return {otwarty:!!d&&d.offsetHeight>50, strategie_na_wykresie:st, linie:linie.slice(0,60)};
    })()""")
    if isinstance(w, dict) and "blad" in w:
        raise BladSesji(w["blad"])
    tekst = " | ".join(w.get("linie", []))
    w["ma_transakcje"] = "requires trade data" not in tekst and "even one trade" not in tekst
    return w


if __name__ == "__main__":
    print("sesja:", czy_zalogowany())
    a = alerty()
    print(f"alerty: {a['ile']}")
    for x in a.get("alerty", [])[:3]:
        print("  ", x["symbol"], "|", x["nazwa"][:40], "| aktywny:", x["aktywny"])
    s = skrypty_pine()
    print(f"skrypty Pine: {s['ile']}")
    for x in s.get("skrypty", [])[:3]:
        print("  ", x["nazwa"][:40], "|", x["id"])
    lo = lista_obserwowanych()
    print(f"lista obserwowanych „{lo.get('nazwa')}\": {lo.get('ile')} symboli")
