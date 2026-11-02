"""Zaślepki do testów integracyjnych: sieć HTTP, przeglądarka z CDP i zegar.

Nic tu nie dotyka prawdziwego TradingView ani prawdziwej przeglądarki.

- `Siec` podmienia `urllib.request.urlopen` i odpowiada jak publiczne punkty
  TradingView (scanner, kompilator Pine, alerty, pine-facade) oraz jak punkt
  HTTP przeglądarki (`/json`, `/json/version`, `/json/new`).
- `CDP` udaje kartę z wykresem po drugiej stronie gniazda websocket. Nie
  wykonuje JavaScriptu — rozpoznaje fragmenty kodu, które wysyłają moduły
  `wykres`, `sesja`, `replay` i `uklad`, i odpowiada tym, co zwróciłaby
  strona. Stan wykresu (symbol, przedział, wskaźniki, odtwarzanie, układ)
  jest trzymany tutaj, więc kolejne wywołania widzą skutki poprzednich.
- `Zegar` zastępuje `time.time` i `time.sleep` czasem umownym: `sleep`
  przesuwa zegar zamiast czekać, więc pętle z limitem czasu kończą się od razu,
  a test może sprawdzić, ile czasu umownego zajęło wywołanie.

Tryby awarii ustawia się na obiektach wprost: `siec.awaria[...]`,
`cdp.tryb = "cisza"` i podobne. Opis przy każdej klasie.
"""
from __future__ import annotations

import base64
import contextlib
import importlib
import io
import json
import math
import re
import socket
import sys
import threading
import time as _time
import types
import urllib.error
import urllib.parse
import urllib.request

try:  # prawdziwe klasy wyjątków, jeśli pakiet jest — moduły sprawdzają ich treść
    import websocket as _prawdziwy_ws
except ImportError:  # pragma: no cover
    _prawdziwy_ws = None


# ── zegar ───────────────────────────────────────────────────────────────
class Zegar:
    """Czas umowny. `sleep` przesuwa zegar, `time` go odczytuje."""

    def __init__(self, start: float = 1_760_000_000.0):
        self.teraz = start
        self.przespane = 0.0
        self._blokada = threading.Lock()

    def time(self) -> float:
        with self._blokada:
            return self.teraz

    def sleep(self, s: float) -> None:
        with self._blokada:
            s = max(0.0, float(s))
            self.teraz += s
            self.przespane += s

    def przesun(self, s: float) -> None:
        with self._blokada:
            self.teraz += s


# ── sieć ────────────────────────────────────────────────────────────────
CENY = {"FX:EURUSD": 1.1, "FX:GBPUSD": 1.27, "FX:USDJPY": 150.0, "FX:AUDUSD": 0.66,
        "COINBASE:BTCUSD": 60000.0, "COMEX:GC1!": 2400.0, "NASDAQ:NVDA": 120.0}

# Wartości pól dla ceny 1.0 — skalowane ceną instrumentu tam, gdzie pole jest ceną.
_POLA_CENOWE = {"close": 1.0, "open": 0.998, "high": 1.004, "low": 0.995, "VWAP": 1.0,
                "BB.upper": 1.01, "BB.lower": 0.99, "EMA5": 1.0005, "EMA10": 1.0003,
                "EMA20": 1.0, "EMA30": 0.999, "EMA50": 0.998, "EMA100": 0.995,
                "EMA200": 0.99, "price_52_week_high": 1.08, "price_52_week_low": 0.92,
                "ATR": 0.006, "change_abs": 0.002}
_POLA_STALE = {"RSI": 52.0, "ADX": 31.0, "Recommend.All": 0.2, "change": 0.25,
               "volume": 1000.0, "relative_volume_10d_calc": 1.3}
# Przedziały mają własne RSI, żeby zgodność miała co liczyć; 240 celowo puste.
_RSI_PRZEDZIALY = {"1": 61.0, "5": 60.0, "15": 58.0, "60": 40.0, "240": None, "1W": 50.0}


def wartosc_pola(symbol: str, pole: str):
    nazwa, _, przedzial = pole.partition("|")
    cena = CENY.get(symbol, 10.0)
    if nazwa == "RSI" and przedzial:
        return _RSI_PRZEDZIALY.get(przedzial, 50.0)
    if nazwa in _POLA_CENOWE:
        return round(_POLA_CENOWE[nazwa] * cena, 6)
    if nazwa in _POLA_STALE:
        return _POLA_STALE[nazwa]
    # każde inne pole: liczba wyliczona z nazwy, stała między wywołaniami
    return round((sum(map(ord, nazwa)) % 97) / 3.0 + 1.0, 4)


class _Odpowiedz(io.BytesIO):
    def __init__(self, tresc: bytes, status: int = 200):
        super().__init__(tresc)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _http_blad(url: str, kod: int):
    return urllib.error.HTTPError(url, kod, f"HTTP {kod}", {}, io.BytesIO(b"{}"))


class Siec:
    """Podmiana `urllib.request.urlopen`.

    `awaria` — słownik {fragment adresu: kod HTTP | wyjątek | "timeout" | "smieci"}.
    Pierwszy pasujący fragment wygrywa. "timeout" przesuwa zegar o limit
    zapytania i rzuca `socket.timeout`, "smieci" zwraca odpowiedź, która nie
    jest JSON-em.

    `zapytania` — lista (metoda, adres, ciało) wszystkich zapytań, do sprawdzania
    np. czy moduł nie ponawia po 429.
    """

    def __init__(self, zegar: Zegar, cdp: "CDP"):
        self.zegar = zegar
        self.cdp = cdp
        self.awaria: dict[str, object] = {}
        self.zapytania: list[tuple[str, str, bytes | None]] = []
        self.ciasteczko_wymagane = True
        self.alerty = [
            {"alert_id": 1, "symbol": '={"symbol":"ICMARKETS:USDCHF","session":"regular"}',
             "name": "USDCHF nad 0.9", "active": True,
             "condition": {"type": "cross"}, "resolution": "60"},
            {"alert_id": 2, "symbol": "FX:EURUSD", "name": None, "active": False,
             "condition": "greater", "resolution": "D"},
        ]
        self.skrypty = [{"scriptName": "Moj RSI", "scriptIdPart": "USER;abc", "version": 3,
                         "modified": 1700000000}]
        self.wbudowane = [{"scriptName": "MACD Strategy", "scriptIdPart": "STD;MACD"},
                          {"scriptName": "Relative Strength Index", "scriptIdPart": "STD;RSI"},
                          {"scriptName": "RSI Strategy", "scriptIdPart": "STD;RSIS"}]

    # urlopen(url | Request, data=None, timeout=...)
    def urlopen(self, zad, data=None, timeout=None, **_):
        if isinstance(zad, str):
            url, metoda, cialo, naglowki = zad, ("POST" if data else "GET"), data, {}
        else:
            url = zad.full_url
            cialo = zad.data
            metoda = zad.get_method()
            naglowki = {k.lower(): v for k, v in zad.header_items()}
        self.zapytania.append((metoda, url, cialo))

        for fragment, co in self.awaria.items():
            if fragment in url:
                if co == "timeout":
                    self.zegar.przesun(timeout or 0)
                    raise socket.timeout("timed out")
                if co == "smieci":
                    return _Odpowiedz(b"<html>502 Bad Gateway</html>")
                if isinstance(co, int):
                    raise _http_blad(url, co)
                if isinstance(co, BaseException):
                    raise co
        return self._trasa(url, metoda, cialo, naglowki)

    def _json(self, x) -> _Odpowiedz:
        return _Odpowiedz(json.dumps(x).encode())

    def _trasa(self, url, metoda, cialo, naglowki):
        u = urllib.parse.urlsplit(url)
        q = urllib.parse.parse_qs(u.query)

        if u.hostname == "localhost":
            return self.cdp.http(u.path, u.query, metoda, self.zegar)

        if u.hostname == "scanner.tradingview.com":
            if u.path == "/symbol":
                symbol = q["symbol"][0]
                if symbol not in CENY:
                    raise _http_blad(url, 400)   # tak odpowiada TradingView na złą nazwę
                return self._json({p: wartosc_pola(symbol, p)
                                   for p in q["fields"][0].split(",")})
            m = re.fullmatch(r"/([a-z]+)/scan", u.path)
            if m:
                if m.group(1) not in ("forex", "crypto", "coin", "america", "poland",
                                      "germany", "uk", "japan", "futures", "cfd"):
                    raise _http_blad(url, 404)
                z = json.loads(cialo)
                kolumny = z["columns"]
                if "symbols" in z:
                    symbole = [s for s in z["symbols"]["tickers"] if s in CENY]
                else:
                    od, do = z.get("range", [0, 30])
                    symbole = list(CENY)[od:do]
                return self._json({"totalCount": len(symbole), "data": [
                    {"s": s, "d": [wartosc_pola(s, k) for k in kolumny]} for s in symbole]})

        if u.hostname == "pine-facade.tradingview.com":
            if "translate_light" in u.path:
                if "origin" not in naglowki or "referer" not in naglowki:
                    raise _http_blad(url, 403)
                kod = urllib.parse.parse_qs(cialo.decode())["source"][0]
                return self._json(self._kompiluj(kod))
            self._wymagaj_sesji(url, naglowki)
            if "/list/" in u.path:
                return self._json(self.skrypty if q.get("filter") == ["saved"] else self.wbudowane)
            m = re.search(r"/get/([^/]+)/last", u.path)
            if m:
                ident = urllib.parse.unquote(m.group(1))
                for s in self.skrypty:
                    if s["scriptIdPart"] == ident:
                        return self._json({"scriptName": s["scriptName"], "version": 3,
                                           "source": "//@version=5\nindicator(\"x\")"})
                raise _http_blad(url, 404)

        if u.hostname == "pricealerts.tradingview.com":
            self._wymagaj_sesji(url, naglowki)
            return self._json({"s": "ok", "r": self.alerty})

        raise urllib.error.URLError(f"nieznany adres w zaślepce: {url}")

    def _wymagaj_sesji(self, url, naglowki):
        if self.ciasteczko_wymagane and "sessionid=" not in naglowki.get("cookie", ""):
            raise _http_blad(url, 401)

    @staticmethod
    def _kompiluj(kod: str) -> dict:
        bledy = []
        for nr, linia in enumerate(kod.splitlines(), 1):
            for zly in ("clse", "niema", "tez_niema"):
                k = linia.find(zly)
                if k >= 0 and not linia[k - 1:k].isalpha():
                    bledy.append({"start": {"line": nr, "column": k + 1},
                                  "message": f"Undeclared identifier '{zly}'"})
                    break
        if "BEZ_POZYCJI" in kod:      # kompilator potrafi zwrócić błąd bez pozycji
            bledy.append({"message": "Script could not be translated"})
        return {"success": True, "result": {"errors": bledy, "warnings": []}}


# ── przeglądarka i CDP ──────────────────────────────────────────────────
ODSTEP = {"1": 60, "3": 180, "5": 300, "15": 900, "30": 1800, "60": 3600, "120": 7200,
          "240": 14400, "D": 86400, "1D": 86400, "W": 604800, "1W": 604800}


class Wykres:
    """Stan jednego wykresu w układzie."""

    def __init__(self, symbol="FX:EURUSD", interwal="60"):
        self.symbol = symbol
        self.interwal = interwal
        self.typ = 1
        self.wskazniki: list[dict] = [{"id": "st1", "nazwa": "Volume"}]
        # symbol, do którego naprawdę należą świece; po setSymbol potrafi zostać stary
        self.symbol_swiec = symbol
        self.interwal_swiec = interwal


class CDP:
    """Przeglądarka z debugowaniem: punkt HTTP i gniazdo websocket.

    tryb:
      "normalny"   — odpowiada na wszystko,
      "zamknieta"  — port nie odpowiada (ConnectionRefused na HTTP i gnieździe),
      "bez_karty"  — przeglądarka jest, ale żadna karta nie ma TradingView,
      "cisza"      — gniazdo się łączy, ale odpowiedź nigdy nie przychodzi
                     (recv rzuca timeout po upływie limitu gniazda),
      "zalew"      — gniazdo zasypuje zdarzeniami bez naszego id,
      "zerwane"    — gniazdo zrywa połączenie przy pierwszym recv,
      "bez_api"    — strona bez `window.TradingViewApi` (np. wczytuje się).
    `cisza_razy`   — ile kolejnych wywołań ma przemilczeć, zanim wróci "normalny".
    `wyjatek_js`   — gdy ustawione, każde Runtime.evaluate kończy się wyjątkiem JS.
    `blokada`      — threading.Event; gdy ustawione, recv czeka na nie naprawdę
                     (do sprawdzania, czy serwer nie blokuje pętli zdarzeń).
    `swiece_spoznione` — ile odczytów świec po zmianie symbolu zwraca jeszcze
                     świece poprzedniego instrumentu.
    """

    def __init__(self, zegar: Zegar, port: int):
        self.zegar = zegar
        self.port = port
        self.tryb = "normalny"
        self.cisza_razy = 0
        self.wyjatek_js: str | None = None
        self.blokada: threading.Event | None = None
        self.swiece_spoznione = 0
        self._spoznienie_zostalo = 0
        # sekundy luki przed ostatnią świecą — np. weekend między piątkiem a poniedziałkiem
        self.luka_przed_ostatnia = 0
        self.ile_swiec = 600
        self.karty = [
            {"id": "SW1", "type": "service_worker",
             "url": "https://www.tradingview.com/service-worker.js",
             "webSocketDebuggerUrl": f"ws://localhost:{port}/devtools/page/SW1"},
            {"id": "K1", "type": "page", "title": "EURUSD 1.1 ▲ — TradingView",
             "url": "https://www.tradingview.com/chart/abc/",
             "webSocketDebuggerUrl": f"ws://localhost:{port}/devtools/page/K1"},
        ]
        self.wykresy = [Wykres()]
        self.aktywny = 0
        self.uklad = "s"
        self.zalogowany = True
        self.panel_prawy = True
        self.zapisane_pine: list[dict] = [{"scriptName": "Stary", "scriptIdPart": "USER;old"}]
        self.replay = {"dostepne": True, "trwa": False, "auto": False, "opoznienie": 1000,
                       "pasek": False, "krok": 0, "start_ms": None}
        self.wywolania: list[str] = []        # kod JS każdego Runtime.evaluate
        self.metody: list[str] = []           # metoda każdego polecenia CDP
        self.nawigacje: list[str] = []

    @property
    def ch(self) -> Wykres:
        return self.wykresy[self.aktywny]

    # punkt HTTP przeglądarki
    def http(self, sciezka, zapytanie, metoda, zegar):
        if self.tryb == "zamknieta":
            raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
        if sciezka == "/json/version":
            return _Odpowiedz(json.dumps({"Browser": "Chrome/131"}).encode())
        if sciezka in ("/json", "/json/list"):
            if self.tryb == "bez_karty":
                return _Odpowiedz(json.dumps([{"id": "X", "type": "page",
                                               "url": "about:blank",
                                               "webSocketDebuggerUrl": "ws://x"}]).encode())
            return _Odpowiedz(json.dumps(self.karty).encode())
        if sciezka == "/json/new":
            if metoda != "PUT":
                return _Odpowiedz(b"Using unsafe HTTP verb GET to invoke /json/new.", 405)
            nowa = {"id": f"K{len(self.karty) + 1}", "type": "page", "title": "TradingView",
                    "url": urllib.parse.unquote(zapytanie),
                    "webSocketDebuggerUrl": f"ws://localhost:{self.port}/devtools/page/N"}
            self.karty.append(nowa)
            if self.tryb == "bez_karty":
                self.tryb = "normalny"
            return _Odpowiedz(json.dumps(nowa).encode())
        raise _http_blad(sciezka, 404)

    # moduł websocket podstawiany zamiast websocket-client
    def modul_websocket(self) -> types.ModuleType:
        m = types.ModuleType("websocket")
        if _prawdziwy_ws is not None:
            m.WebSocketException = _prawdziwy_ws.WebSocketException
            m.WebSocketTimeoutException = _prawdziwy_ws.WebSocketTimeoutException
            m.WebSocketConnectionClosedException = _prawdziwy_ws.WebSocketConnectionClosedException
        else:  # pragma: no cover
            class WebSocketException(Exception):
                pass

            class WebSocketTimeoutException(WebSocketException):
                pass

            class WebSocketConnectionClosedException(WebSocketException):
                pass
            m.WebSocketException = WebSocketException
            m.WebSocketTimeoutException = WebSocketTimeoutException
            m.WebSocketConnectionClosedException = WebSocketConnectionClosedException
        cdp = self

        def create_connection(url, timeout=None, **_):
            if cdp.tryb == "zamknieta":
                raise ConnectionRefusedError(111, "Connection refused")
            return _Gniazdo(cdp, m, timeout)

        m.create_connection = create_connection
        return m

    # ── odpowiedzi na polecenia CDP ─────────────────────────────────────
    def polecenie(self, o: dict):
        metoda = o.get("method")
        self.metody.append(metoda)
        p = o.get("params") or {}
        if metoda == "Runtime.evaluate":
            kod = p.get("expression", "")
            self.wywolania.append(kod)
            if self.wyjatek_js:
                return {"result": {"type": "object"},
                        "exceptionDetails": {"text": "Uncaught", "exception": {
                            "description": f"TypeError: {self.wyjatek_js}\n    at <anonymous>:1:1"}}}
            return {"result": {"type": "object", "value": self.wykonaj(kod)}}
        if metoda == "Network.getCookies":
            ck = [{"name": "_ga", "value": "GA1"}, {"name": "device_t", "value": "dt"}]
            if self.zalogowany:
                ck.append({"name": "sessionid", "value": "SEKRET-SESJI"})
            return {"cookies": ck}
        if metoda == "Page.captureScreenshot":
            return {"data": base64.b64encode(b"\x89PNG\r\n\x1a\nzaslepka").decode()}
        if metoda == "Page.navigate":
            url = p["url"]
            self.nawigacje.append(url)
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            ch = self.ch
            if "symbol" in q:
                ch.symbol = ch.symbol_swiec = q["symbol"][0]
            if "interval" in q:
                ch.interwal = ch.interwal_swiec = q["interval"][0]
            self._spoznienie_zostalo = 0
            return {"frameId": "F1"}
        return {}

    # ── świece ──────────────────────────────────────────────────────────
    def _swiece(self, n: int) -> list:
        ch = self.ch
        if self._spoznienie_zostalo > 0:
            self._spoznienie_zostalo -= 1
        else:
            ch.symbol_swiec = ch.symbol
            ch.interwal_swiec = ch.interwal
        cena = CENY.get(ch.symbol_swiec, 10.0)
        krok = ODSTEP.get(str(ch.interwal_swiec).upper(), 3600)
        razem = self.ile_swiec
        koniec = int(self.zegar.time()) // krok * krok
        if self.replay["trwa"]:
            # w odtwarzaniu wykres kończy się na dacie startu plus wykonane kroki
            razem = min(razem, 50 + self.replay["krok"])
            koniec = int(self.replay["start_ms"] // 1000) // krok * krok + self.replay["krok"] * krok
        out = []
        for i in range(max(0, razem - n), razem):
            t = koniec - (razem - 1 - i) * krok
            if i < razem - 1:
                t -= self.luka_przed_ostatnia
            # kilka nakładających się fal: sygnały się zdarzają, ale nie co świecę
            z = cena * (1 + 0.01 * math.sin(i / 7.0) + 0.006 * math.sin(i / 2.3)
                        + 0.003 * math.cos(i / 1.1))
            o = z * (1 - 0.0015 * math.sin(i / 3.0))
            out.append([t, round(o, 6), round(max(o, z) * 1.002, 6),
                        round(min(o, z) * 0.998, 6), round(z, 6), 100 + i])
        return out

    # ── emulacja kodu wysyłanego przez moduły ───────────────────────────
    def wykonaj(self, kod: str):
        ch = self.ch
        bez_api = self.tryb == "bez_api"
        jest_opakowanie = "api._activeChartWidgetWV" in kod and "strona nie udostępnia" in kod
        if bez_api and jest_opakowanie:
            return {"blad": "strona nie udostępnia API wykresu"}

        # sesja
        if "window.user" in kod:
            return ({"id": 42, "nazwa": "testowy", "plan": "pro_premium"}
                    if self.zalogowany else None)
        if "data-symbol-full" in kod:
            if not self.panel_prawy:
                return {"blad": "panel prawy nie jest otwarty"}
            return {"nazwa": "Forex", "ile": 2, "symbole": ["FX:EURUSD", "FX:GBPUSD"]}
        if "pineEditorApi" in kod:
            if "saveNewScript" in kod:
                nazwa = json.loads(re.search(r"name:(\".*?\")\}", kod).group(1))
                self.zapisane_pine.append({"scriptName": nazwa,
                                           "scriptIdPart": f"USER;n{len(self.zapisane_pine)}"})
                return {"zapisany": True, "id": self.zapisane_pine[-1]["scriptIdPart"],
                        "zapisanych_teraz": len(self.zapisane_pine)}
            if "deleteScript" in kod:
                ident = json.loads(re.search(r"deleteScript\((\".*?\")\)", kod).group(1))
                self.zapisane_pine = [s for s in self.zapisane_pine
                                      if s["scriptIdPart"] != ident]
                return {"usuniety": True, "zapisanych_teraz": len(self.zapisane_pine)}
        if "bottomWidgetBar.open" in kod:
            return 1
        if "layout__area--bottom" in kod:
            return {"otwarty": True, "strategie_na_wykresie": [],
                    "linie": ["Strategy Tester", "requires trade data"]}

        # odtwarzanie historii
        if "_replayApi" in kod:
            return self._replay(kod)

        # układ okna
        if "api.setLayout(" in kod:
            kodu = re.search(r"setLayout\('([^']+)'\)", kod).group(1)
            ile = {"s": 1, "2h": 2, "2v": 2, "2-1": 3, "3h": 3, "3v": 3, "4": 4,
                   "6": 6, "8": 8}[kodu]
            self.uklad = kodu
            while len(self.wykresy) < ile:
                self.wykresy.append(Wykres("FX:GBPUSD", "15"))
            del self.wykresy[ile:]
            self.aktywny = min(self.aktywny, ile - 1)
            return 1
        if "api.setActiveChart(" in kod:
            i = int(re.search(r"setActiveChart\((\d+)\)", kod).group(1))
            if i < len(self.wykresy):
                self.aktywny = i
            return 1
        if "api.layout()" in kod:
            return {"uklad": self.uklad, "nazwa": "Moj uklad", "wykresow": len(self.wykresy),
                    "aktywny": self.aktywny, "paneli_w_wykresie": 1 + len(ch.wskazniki) - 1,
                    "niezapisane_zmiany": False}

        # wykres
        if "closeButton" in kod:
            return 0
        if "return {ok: true, symbol: ch.symbol()};" in kod:
            return {"ok": True, "symbol": ch.symbol}
        if "typ_wykresu: ch.chartType()" in kod:
            return {"symbol": ch.symbol, "interwal": ch.interwal, "typ_wykresu": ch.typ,
                    "wskazniki": [dict(w) for w in ch.wskazniki], "rysunki": []}
        if "ch.setSymbol(" in kod:
            s = json.loads(re.search(r"ch\.setSymbol\((\".*?\")\)", kod).group(1))
            ch.symbol = s
            self._spoznienie_zostalo = self.swiece_spoznione
            return {"ok": True, "symbol": s}
        if "ch.setResolution(" in kod:
            i = json.loads(re.search(r"ch\.setResolution\((\".*?\")\)", kod).group(1))
            ch.interwal = i
            return {"ok": True, "interwal": i}
        if "ch.setChartType(" in kod:
            t = int(re.search(r"setChartType\((-?\d+)\)", kod).group(1))
            ch.typ = t
            return {"ok": True, "typ": t}
        if "seria.bars()" in kod:
            n = int(re.search(r"ostatni - (\d+) \+ 1", kod).group(1))
            s = self._swiece(n)
            return {"dostepnych": self.ile_swiec, "zwrocono": len(s), "swiece": s}
        if "createStudy(" in kod:
            n = json.loads(re.search(r"createStudy\((\".*?\")", kod).group(1))
            ch.wskazniki.append({"id": f"st{len(ch.wskazniki) + 1}", "nazwa": n})
            return {"ok": True, "dodano": n}
        if "removeEntity" in kod:
            ident = json.loads(re.search(r"lista\[k\]\.id === (\".*?\")", kod).group(1))
            for w in ch.wskazniki:
                if w["id"] == ident:
                    ch.wskazniki.remove(w)
                    return {"ok": True, "usuniete": ident}
            return {"blad": "nie ma wskaźnika o takim identyfikatorze"}
        if "meta.description" in kod:
            # bez sesji TradingView liczy tylko pierwszy wskaźnik (poza wolumenem)
            wynik, liczy = [], 0
            for w in ch.wskazniki:
                if w["nazwa"] == "Volume":
                    wynik.append({"nazwa": "Volume", "wartosci": [100]})
                    continue
                if self.zalogowany or liczy == 0:
                    wynik.append({"nazwa": w["nazwa"], "wartosci": [55.5]})
                    liczy += 1
            return wynik
        if "getAllStudies().map" in kod:
            return [dict(w) for w in ch.wskazniki]
        if "getAllShapes().map" in kod:
            return []
        raise AssertionError("zaślepka CDP nie zna tego kodu:\n" + kod[:400])

    def _replay(self, kod: str):
        r = self.replay
        if "isReplayAvailable()" in kod:
            data = None
            if r["start_ms"] is not None:
                import datetime as _dt
                data = _dt.datetime.fromtimestamp(r["start_ms"] / 1000, _dt.timezone.utc
                                                  ).strftime("%Y-%m-%d %H:%M")
            return {"dostepne": r["dostepne"], "trwa": r["trwa"], "autoodtwarzanie": r["auto"],
                    "gotowe_do_gry": r["trwa"], "pasek_widoczny": r["pasek"],
                    "opoznienie": r["opoznienie"], "tryb": "", "historia_od": "2001-11-28",
                    "wybrana_data": data, "pozycja": None, "wynik": None, "waluta": "USD"}
        if "selectFirstAvailableDate" in kod or "selectDate(" in kod:
            m = re.search(r"selectDate\((\d+)\)", kod)
            r["start_ms"] = int(m.group(1)) if m else 1006905600000
            r.update(trwa=True, pasek=True, krok=0)
            return 1
        if "doStep" in kod:
            n = int(re.search(r"i<(\d+);", kod).group(1))
            r["krok"] += n
            return 1
        if "changeAutoplayDelay" in kod:
            r["opoznienie"] = int(re.search(r"changeAutoplayDelay\((\d+)\)", kod).group(1))
            return 1
        if "toggleAutoplay" in kod:
            r["auto"] = not r["auto"]
            return 1
        if "stopReplay" in kod:
            r.update(trwa=False, auto=False, start_ms=None, krok=0)
            return 1
        if "hideReplayToolbar" in kod:
            r["pasek"] = False
            return 1
        raise AssertionError("zaślepka CDP nie zna kodu odtwarzania:\n" + kod[:300])


class _Gniazdo:
    """Jedno połączenie websocket z kartą."""

    def __init__(self, cdp: CDP, modul, timeout):
        self.cdp = cdp
        self.m = modul
        self.timeout = timeout or 30
        self.kolejka: list[str] = []
        self.zamkniete = False

    def send(self, tekst: str):
        o = json.loads(tekst)
        cdp = self.cdp
        if cdp.cisza_razy > 0:
            cdp.cisza_razy -= 1
            self._milczy = True
            return
        self._milczy = cdp.tryb == "cisza"
        if self._milczy or cdp.tryb in ("zalew", "zerwane"):
            return
        # zdarzenie bez id przed odpowiedzią — moduły muszą je pominąć
        self.kolejka.append(json.dumps({"method": "Runtime.consoleAPICalled", "params": {}}))
        self.kolejka.append(json.dumps({"id": o["id"] + 1000, "result": {}}))
        self.kolejka.append(json.dumps({"id": o["id"], "result": cdp.polecenie(o)}))

    def recv(self) -> str:
        cdp = self.cdp
        if cdp.blokada is not None:
            cdp.blokada.wait(10)
        if cdp.tryb == "zerwane":
            raise self.m.WebSocketConnectionClosedException("Connection to remote host was lost.")
        if cdp.tryb == "zalew":
            cdp.zegar.przesun(0.5)
            return json.dumps({"method": "Network.dataReceived", "params": {}})
        if getattr(self, "_milczy", False) or not self.kolejka:
            cdp.zegar.przesun(self.timeout)
            raise self.m.WebSocketTimeoutException("timed out")
        cdp.zegar.przesun(0.01)
        return self.kolejka.pop(0)

    def close(self):
        self.zamkniete = True


# ── podmiana w testowanych modułach ─────────────────────────────────────
MODULY = ("dane", "pine", "sesja", "wykres", "analiza", "replay", "uklad", "pomiar")


class _CzasUmowny:
    """Zamiast modułu `time` w testowanych modułach: zegar umowny, reszta prawdziwa."""

    def __init__(self, zegar):
        self._z = zegar

    def time(self):
        return self._z.time()

    def sleep(self, s):
        self._z.sleep(s)

    def __getattr__(self, nazwa):
        return getattr(_time, nazwa)


class Srodowisko:
    def __init__(self, zegar, siec, cdp):
        self.zegar = zegar
        self.siec = siec
        self.cdp = cdp


@contextlib.contextmanager
def podmienione(port: int = 9333):
    """Na czas bloku: sieć, przeglądarka i zegar są zaślepkami.

    Wymaga katalogu `src` w sys.path. Wszystko wraca na miejsce po wyjściu,
    także po wyjątku.
    """
    zegar = Zegar()
    cdp = CDP(zegar, port)
    siec = Siec(zegar, cdp)
    ws = cdp.modul_websocket()
    czas = _CzasUmowny(zegar)

    stare = []                                   # (obiekt, atrybut, wartość)

    def ustaw(obj, nazwa, wartosc):
        stare.append((obj, nazwa, getattr(obj, nazwa)))
        setattr(obj, nazwa, wartosc)

    stary_ws = sys.modules.get("websocket", None)
    try:
        ustaw(urllib.request, "urlopen", siec.urlopen)
        sys.modules["websocket"] = ws
        for nazwa in MODULY:
            m = importlib.import_module(nazwa)
            if hasattr(m, "time"):
                ustaw(m, "time", czas)
        wykres = sys.modules["wykres"]
        ustaw(wykres, "websocket", ws)
        ustaw(wykres, "PORT", port)
        # ograniczniki tempa pamiętają czas ostatniego zapytania — zerujemy je
        ustaw(sys.modules["dane"], "_ostatnie", 0.0)
        ustaw(sys.modules["pine"], "_ostatnie", [0.0])
        ustaw(sys.modules["sesja"], "_ostatnie", [0.0])
        yield Srodowisko(zegar, siec, cdp)
    finally:
        for obj, nazwa, wartosc in reversed(stare):
            setattr(obj, nazwa, wartosc)
        if stary_ws is None:
            sys.modules.pop("websocket", None)
        else:
            sys.modules["websocket"] = stary_ws
