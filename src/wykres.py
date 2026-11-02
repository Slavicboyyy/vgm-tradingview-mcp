#!/usr/bin/env python3
"""VGM MCP — warstwa wykresu. Steruje otwartą kartą TradingView przez CDP.

W przeciwieństwie do warstwy danych ta wymaga uruchomionej przeglądarki
z otwartą kartą TradingView. Port bierze wyłącznie ze zmiennej VGM_CDP_PORT;
bez niej warstwa wykresu zgłasza czytelny błąd, a `zdrowie()` mówi, czego brakuje.

Sięga po wewnętrzne API strony: `window.TradingViewApi._activeChartWidgetWV.value()`.
To nie jest udokumentowane przez TradingView i może przestać działać po ich
aktualizacji — dlatego `zdrowie()` sprawdza dostępność, zanim cokolwiek zrobisz.
"""
from __future__ import annotations

import importlib
import json
import os
import time
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import walidacja as wal  # noqa: E402

if TYPE_CHECKING:  # same typy, bez wymogu ścieżki przy imporcie
    from typy import Json, Swieca

websocket: Any
try:
    websocket = importlib.import_module("websocket")
except ImportError:  # pragma: no cover
    websocket = None


API = "window.TradingViewApi._activeChartWidgetWV.value()"
_licznik = [0]


class BladWykresu(Exception):
    """Cokolwiek, co uniemożliwia sterowanie wykresem — z czytelnym powodem."""


def _port_cdp() -> int:
    """Port zdalnego debugowania przeglądarki — tylko ze zmiennej VGM_CDP_PORT.

    Nie ma wartości domyślnej ani sprawdzania kolejnych portów: czytany przy
    każdym użyciu, więc zły albo brakujący port nie blokuje importu modułu,
    tylko daje błąd narzędzia wykresu."""
    z_env = os.environ.get("VGM_CDP_PORT", "").strip()
    if not z_env:
        raise BladWykresu(
            "brak zmiennej VGM_CDP_PORT — ustaw ją na port, z którym uruchomiono "
            "przeglądarkę (flaga --remote-debugging-port)")
    if not (z_env.isascii() and z_env.isdigit()) or not 1 <= int(z_env) <= 65535:
        raise BladWykresu(f"VGM_CDP_PORT={z_env[:20]!r} nie jest portem (1–65535)")
    return int(z_env)


def _to_tradingview(url: str) -> bool:
    """Host karty to tradingview.com albo jego subdomena, po HTTPS.

    Samo `"tradingview.com" in url` łapie też evil.com/?tradingview.com
    i tradingview.com.evil.com — wykonywalibyśmy kod na obcej stronie."""
    u = urllib.parse.urlsplit(url)
    h = u.hostname or ""
    return u.scheme == "https" and (h == "tradingview.com" or h.endswith(".tradingview.com"))


def _karta() -> Json:
    """Pierwsza karta przeglądarki z TradingView po HTTPS; inaczej BladWykresu."""
    if websocket is None:
        raise BladWykresu(
            "brakuje pakietu websocket-client — zainstaluj: pip install websocket-client")
    port = _port_cdp()
    try:
        surowe = urllib.request.urlopen(
            f"http://localhost:{port}/json", timeout=10).read()
    except Exception as e:
        raise BladWykresu(
            f"przeglądarka nie odpowiada na porcie {port} ({type(e).__name__}). "
            "Uruchom ją z debugowaniem na tym porcie albo popraw VGM_CDP_PORT."
        ) from e

    for t in json.loads(surowe):
        if t.get("type", "page") == "page" and _to_tradingview(t.get("url", "")):
            karta: Json = t
            return karta
    raise BladWykresu(
        "żadna karta nie ma otwartego TradingView — otwórz wykres i spróbuj ponownie")


def _wykonaj(kod: str, czekaj: float = 25, prob: int = 2) -> Any:
    """Wykonuje kod na karcie. Przy przeciążonej przeglądarce ponawia raz.

    Zmierzone: gdy przeglądarka ma kilkadziesiąt kart, pojedyncze wywołanie
    potrafi przekroczyć czas mimo działającej strony. Jedno ponowienie
    z dłuższym limitem wystarcza.
    """
    ostatni: Exception | None = None
    for i in range(prob):
        try:
            return _wykonaj_raz(kod, czekaj * (1 + i))
        except (BladWykresu, OSError) as e:
            ostatni = e
            if "przekroczy" in str(e).lower() or "timed out" in str(e).lower():
                time.sleep(2)
                continue
            raise
        except Exception as e:
            # timeout gniazda przychodzi jako wyjątek biblioteki, nie nasz
            ostatni = e
            if "timed out" in str(e).lower():
                time.sleep(2)
                continue
            raise BladWykresu(f"{type(e).__name__}: {str(e)[:70]}") from e
    raise BladWykresu(
        f"przeglądarka nie odpowiedziała po {prob} próbach: {str(ostatni)[:60]}")


def _cdp(metoda: str, parametry: Json, polaczenie_s: float,
         czekaj_s: float) -> tuple[Json | None, Json]:
    """Jedno polecenie CDP na aktywnej karcie: (odpowiedź albo None po czasie, karta).

    `polaczenie_s` to limit gniazda (dotyczy też pojedynczego `recv`),
    `czekaj_s` to limit na samą odpowiedź na nasze polecenie.
    """
    k = _karta()
    _licznik[0] += 1
    nr = _licznik[0]
    ws = websocket.create_connection(k["webSocketDebuggerUrl"], timeout=polaczenie_s)
    try:
        ws.send(json.dumps({"id": nr, "method": metoda, "params": parametry}))
        koniec = time.time() + czekaj_s
        while time.time() < koniec:
            o: Json = json.loads(ws.recv())
            if o.get("id") == nr:
                return o, k
        return None, k
    finally:
        ws.close()


def _wykonaj_raz(kod: str, czekaj: float = 25) -> Any:
    """Jedno Runtime.evaluate na karcie; wyjątek ze strony staje się BladWykresu."""
    o, _ = _cdp("Runtime.evaluate",
             {"expression": kod, "returnByValue": True, "awaitPromise": True},
             czekaj, czekaj)
    if o is None:
        raise BladWykresu(f"przeglądarka nie odpowiedziała w {czekaj}s")
    r = o.get("result", {})
    if "exceptionDetails" in r:
        # samo "text" to zwykle gołe "Uncaught" — prawdziwy komunikat
        # siedzi w exception.description; bez niego każda diagnoza jest ślepa
        ed = r["exceptionDetails"]
        opis = ((ed.get("exception") or {}).get("description")
                or ed.get("text") or "błąd w przeglądarce")
        raise BladWykresu(str(opis).splitlines()[0][:220])
    return r.get("result", {}).get("value")


def _na_wykresie(cialo: str) -> str:
    """Owija kod w dostęp do wykresu i przechwytywanie błędów."""
    return f"""
    (function(){{
      try {{
        var api = window.TradingViewApi;
        if (!api || !api._activeChartWidgetWV) return {{blad: 'strona nie udostępnia API wykresu'}};
        var ch = api._activeChartWidgetWV.value();
        if (!ch) return {{blad: 'wykres jeszcze się nie wczytał'}};
        {cialo}
      }} catch(e) {{ return {{blad: String(e && e.message || e)}}; }}
    }})()
    """


def _sprawdz(w: Any, wyjatek: type[Exception] = BladWykresu) -> Any:
    """Wynik z kluczem `blad` zamienia w wyjątek podanego typu."""
    if isinstance(w, dict) and "blad" in w:
        raise wyjatek(w["blad"])
    return w


def uruchom(prolog: str, kod: str, czekaj: float,
            wyjatek: type[Exception] = BladWykresu) -> Any:
    """Wykonuje `kod` poprzedzony `prolog` w funkcji natychmiastowej.

    Wspólne dla układu i odtwarzania: wynik z kluczem `blad` staje się
    wyjątkiem podanego typu.
    """
    return _sprawdz(_wykonaj("(function(){" + prolog + kod + "})()", czekaj=czekaj),
                    wyjatek)


def _na(cialo: str, czekaj: float = 25) -> Any:
    """Kod z `cialo` na aktywnym wykresie; `blad` w wyniku rzuca BladWykresu."""
    return _sprawdz(_wykonaj(_na_wykresie(cialo), czekaj=czekaj))


def _na_slownik(cialo: str, czekaj: float = 25) -> Json:
    """Jak `_na`, z wynikiem otypowanym jako słownik."""
    w: Json = _na(cialo, czekaj)
    return w


def _na_liste(cialo: str, czekaj: float = 25) -> list[Json]:
    """Jak `_na`, z wynikiem otypowanym jako lista słowników."""
    w: list[Json] = _na(cialo, czekaj)
    return w


def _adres_wykresu(symbol: str, interwal: str | None) -> str:
    """Adres wykresu z symbolem i interwałem — oba sprawdzone, zanim trafią do URL."""
    adres = f"https://www.tradingview.com/chart/?symbol={urllib.parse.quote(wal.symbol(symbol))}"
    if interwal:
        adres += f"&interval={urllib.parse.quote(wal.interwal(interwal))}"
    return adres


# ── odczyt ──────────────────────────────────────────────────────────────
def zdrowie() -> Json:
    """Czy da się sterować wykresem — sprawdź to przed resztą."""
    wynik: Json = {"port": None, "przegladarka": False, "karta_tv": False,
                   "api_wykresu": False, "gotowy": False}
    try:
        wynik["port"] = _port_cdp()
    except BladWykresu as e:
        wynik["powod"] = str(e)
        return wynik
    try:
        k = _karta()
        wynik["przegladarka"] = True
        wynik["karta_tv"] = True
        wynik["tytul"] = k.get("title", "")[:70]
    except BladWykresu as e:
        wynik["powod"] = str(e)
        if "port" not in str(e):
            wynik["przegladarka"] = True
        return wynik

    try:
        w = _wykonaj(_na_wykresie("return {ok: true, symbol: ch.symbol()};"))
        if isinstance(w, dict) and w.get("ok"):
            wynik["api_wykresu"] = True
            wynik["gotowy"] = True
            wynik["symbol"] = w.get("symbol")
        else:
            wynik["powod"] = (w or {}).get("blad", "nieznany")
    except BladWykresu as e:
        wynik["powod"] = str(e)
    return wynik


def otworz_karte(symbol: str = "FX:EURUSD", interwal: str | None = None,
                 sekund: float = 20) -> Json:
    """Otwiera nową kartę z wykresem, gdy żadna nie jest otwarta.

    Karta potrafi zniknąć: ktoś ją zamknie, przeglądarka ją ubije przy
    przeciążeniu, sesja się skończy. Bez tego każde narzędzie wykresu
    przestaje działać, choć nic nie jest zepsute.
    """
    adres = _adres_wykresu(symbol, interwal)
    port = _port_cdp()

    zad = urllib.request.Request(f"http://localhost:{port}/json/new?{adres}",
                                 method="PUT")
    try:
        odp = json.loads(urllib.request.urlopen(zad, timeout=25).read())
    except Exception as e:
        raise BladWykresu(
            f"nie udało się otworzyć karty ({type(e).__name__}). "
            f"Sprawdź, czy przeglądarka słucha na porcie {port}."
        ) from e

    koniec = time.time() + sekund
    while time.time() < koniec:
        time.sleep(3)
        try:
            z = zdrowie()
            if z.get("gotowy"):
                return {"otwarta": True, "id": odp.get("id", "")[:12],
                        "symbol": z.get("symbol"), "sekund": round(sekund, 1)}
        except BladWykresu:
            pass

    return {"otwarta": False, "id": odp.get("id", "")[:12],
            "powod": f"karta powstała, ale wykres nie wczytał się w {sekund}s"}


def zapewnij_karte(symbol: str = "FX:EURUSD") -> Json:
    """Sprawdza wykres i otwiera kartę, gdy jej nie ma. Nic nie robi, gdy jest."""
    z = zdrowie()
    if z.get("gotowy"):
        return {"bylo_gotowe": True, "symbol": z.get("symbol")}
    return {"bylo_gotowe": False, **otworz_karte(symbol)}


def stan() -> Json:
    """Co jest teraz na wykresie: instrument, przedział czasu, typ, wskaźniki."""
    return _na_slownik("""
        var st = [];
        try {
          st = ch.getAllStudies().map(function(s){
            return {id: s.id, nazwa: s.name || s.title || '?'};
          });
        } catch(e) {}
        var ks = [];
        try {
          ks = ch.getAllShapes().map(function(s){
            return {id: s.id, nazwa: s.name || '?'};
          });
        } catch(e) {}
        return {
          symbol: ch.symbol(),
          interwal: ch.resolution(),
          typ_wykresu: ch.chartType(),
          wskazniki: st,
          rysunki: ks
        };
    """)


def wskazniki() -> list[Json]:
    """Lista wskaźników wiszących na wykresie."""
    return _na_liste("""
        return ch.getAllStudies().map(function(s){
          return {id: s.id, nazwa: s.name || s.title || '?'};
        });
    """)


def rysunki() -> list[Json]:
    """Lista rysunków na wykresie: linie, poziomy, kształty."""
    return _na_liste("""
        return ch.getAllShapes().map(function(s){
          return {id: s.id, nazwa: s.name || '?'};
        });
    """)


# ── zmiany ──────────────────────────────────────────────────────────────
def ustaw_symbol(symbol: str) -> Json:
    """Zmienia instrument na wykresie."""
    s = json.dumps(wal.symbol(symbol))
    return _na_slownik(f"""
        ch.setSymbol({s});
        return {{ok: true, symbol: {s}}};
    """)


def ustaw_interwal(interwal: str) -> Json:
    """Zmienia przedział czasu. Przyjmuje 1, 5, 15, 60, 240, D, W, M."""
    i = json.dumps(wal.interwal(interwal))
    return _na_slownik(f"""
        ch.setResolution({i});
        return {{ok: true, interwal: {i}}};
    """)


def ustaw_typ(typ: int) -> Json:
    """Zmienia typ wykresu. 0 słupki, 1 świece, 3 linia, 9 Heikin Ashi."""
    typ = wal.calkowita(typ, "typ", 0, 30)
    return _na_slownik(f"""
        ch.setChartType({typ});
        return {{ok: true, typ: {typ}}};
    """)


def swiece(ile: int = 100) -> Json:
    """Świece historyczne z wykresu: czas, otwarcie, szczyt, dołek, zamknięcie, wolumen.

    Bierze je z serii, którą wykres i tak ma wczytaną, więc nie potrzeba osobnego
    źródła danych ani konta. Ile świec jest dostępnych, zależy od tego, ile
    wykres zdążył wczytać — zwykle kilkaset.
    """
    n = wal.calkowita(ile, "ile", 1, 5000)
    w = _na(f"""
        var cw = ch._chartWidget;
        if (!cw) return {{blad: 'brak dostępu do modelu wykresu'}};
        var zrodla = cw.model().model().dataSources();
        var seria = null;
        for (var i = 0; i < zrodla.length; i++) {{
          if (!zrodla[i].metaInfo && zrodla[i].bars) {{ seria = zrodla[i]; break; }}
        }}
        if (!seria) return {{blad: 'nie znalazłem serii świec'}};
        var b = seria.bars();
        var pierwszy = b.firstIndex(), ostatni = b.lastIndex();
        var od = Math.max(pierwszy, ostatni - {n} + 1);
        var out = [];
        for (var k = od; k <= ostatni; k++) {{
          var v = b.valueAt(k);
          if (v) out.push(v);
        }}
        return {{dostepnych: b.size(), zwrocono: out.length, swiece: out}};
    """, czekaj=40)

    nazwane: list[Swieca] = []
    for s in w.get("swiece", []):
        if len(s) >= 5:
            nazwane.append({
                "czas": s[0],
                "otwarcie": s[1], "szczyt": s[2], "dolek": s[3], "zamkniecie": s[4],
                "wolumen": s[5] if len(s) > 5 else None,
            })
    return {"dostepnych": w.get("dostepnych"), "zwrocono": len(nazwane), "swiece": nazwane}


def zrzut(sciezka: str | None = None, zamknij_okna: bool = True) -> Json:
    """Zapisuje obraz wykresu do pliku PNG.

    Dzięki temu model może wykres OBEJRZEĆ, nie tylko odczytać z niego liczby.
    Domyślnie najpierw zamyka okna zachęt, które lubią zasłonić widok.
    """
    import base64
    import pathlib
    import tempfile

    import walidacja

    if sciezka is not None:
        try:
            sciezka = str(walidacja.sciezka_do_zapisu(sciezka))
        except walidacja.BladWejscia as e:
            raise BladWykresu(str(e)) from e

    if zamknij_okna:
        try:
            _wykonaj("""
                (function(){
                  var n = 0;
                  document.querySelectorAll(
                    'button[aria-label*="lose"],button[data-name="close"],[class*="closeButton"]'
                  ).forEach(function(b){ try { b.click(); n++; } catch(e){} });
                  document.dispatchEvent(new KeyboardEvent('keydown',
                    {key:'Escape', keyCode:27, bubbles:true}));
                  return n;
                })()
            """)
            time.sleep(1.5)
        except BladWykresu:
            pass  # zamykanie okien to wygoda, nie warunek

    o, k = _cdp("Page.captureScreenshot", {"format": "png"}, 45, 45)
    if o is None:
        raise BladWykresu("przeglądarka nie odpowiedziała w 45s")
    d = o.get("result", {}).get("data")
    if not d:
        raise BladWykresu("przeglądarka nie zwróciła obrazu")
    surowe = base64.b64decode(d)
    if sciezka is None:
        sciezka = tempfile.NamedTemporaryFile(
            suffix=".png", delete=False, prefix="vgm-wykres-").name
    p = pathlib.Path(sciezka)
    p.write_bytes(surowe)
    return {"plik": str(p), "bajtow": len(surowe),
            "tytul": k.get("title", "")[:70]}


def wartosci() -> list[Json]:
    """Bieżące wartości wszystkich wskaźników NA WYKRESIE.

    To jest powód, dla którego warstwa przeglądarki w ogóle istnieje: czyta
    również wskaźniki własne, napisane w Pine, których publiczne API nie zna.
    """
    return _na_liste("""
        var cw = ch._chartWidget;
        if (!cw) return {blad: 'brak dostępu do modelu wykresu'};
        var zrodla = cw.model().model().dataSources();
        var wynik = [];
        for (var i = 0; i < zrodla.length; i++) {
          var s = zrodla[i];
          if (!s.metaInfo) continue;
          try {
            var meta = s.metaInfo();
            var nazwa = meta.description || meta.shortDescription || '';
            if (!nazwa) continue;
            var wart = [];
            try {
              var d = s.data && s.data();
              var b = d && d.last ? d.last() : null;
              if (b && b.value) wart = b.value.slice(1);
            } catch(e) {}
            if (wart.length) wynik.push({nazwa: nazwa, wartosci: wart});
          } catch(e) {}
        }
        return wynik;
    """)


def dodaj_wskaznik(nazwa: str, czekaj_na_dane: bool = True,
                   sekund: float = 12) -> Json:
    """Dodaje wskaźnik na wykres po pełnej nazwie.

    Nazwa musi być dokładna, tak jak w oknie wyboru wskaźników TradingView,
    np. "Relative Strength Index", "Moving Average Exponential", "Volume".

    🔴 Zmierzone ograniczenie: BEZ ZALOGOWANIA TradingView liczy tylko JEDEN
    wskaźnik naraz. Kolejne pojawiają się na liście, ale ich serie zostają puste
    i `wartosci()` ich nie widzi. Sprawdzone po wyczyszczeniu wykresu: pierwszy
    dodany zaczyna liczyć, drugi i trzeci już nie.

    Chcesz kilku wskaźników naraz — zaloguj się na TradingView w tej przeglądarce.
    Chcesz jednego — usuń poprzedni przez `usun_wskaznik`, zanim dodasz następny.

    Dlatego domyślnie czekamy, aż wskaźnik zacznie zwracać liczby, i mówimy wprost,
    gdy się nie doczekał.
    """
    nazwa = wal.tekst(nazwa, "nazwa", 120)
    n = json.dumps(nazwa)
    w: Json = _na(f"""
        var cel = (ch._chartWidget && ch._chartWidget.createStudy) ? ch._chartWidget : ch;
        if (!cel.createStudy) return {{blad: 'ta wersja strony nie pozwala dodać wskaźnika'}};
        cel.createStudy({n}, false, false, []);
        return {{ok: true, dodano: {n}}};
    """)
    time.sleep(2)

    if not czekaj_na_dane:
        return w

    koniec = time.time() + sekund
    while time.time() < koniec:
        try:
            if any(nazwa.lower() in x["nazwa"].lower() for x in wartosci()):
                return {**w, "liczy": True}
        except BladWykresu:
            pass
        time.sleep(2)

    ile_liczy = 0
    try:
        ile_liczy = len([x for x in wartosci() if "Volume" not in x["nazwa"]])
    except BladWykresu:
        pass

    return {**w, "liczy": False, "wskaznikow_liczacych": ile_liczy,
            "uwaga": ("wskaźnik jest na wykresie, ale nie zwraca wartości. "
                      "Bez zalogowania TradingView liczy tylko JEDEN wskaźnik naraz — "
                      "usuń poprzedni przez vgm_wskaznik_usun albo zaloguj się. "
                      "Druga możliwa przyczyna: dodany, zanim wykres wczytał świece.")}


def usun_wskaznik(identyfikator: str) -> Json:
    """Usuwa jeden wskaźnik po identyfikatorze z `wskazniki()`."""
    i = json.dumps(wal.identyfikator(identyfikator))
    return _na_slownik(f"""
        var lista = ch.getAllStudies();
        for (var k = 0; k < lista.length; k++) {{
          if (lista[k].id === {i}) {{
            ch.removeEntity ? ch.removeEntity({i}) : null;
            return {{ok: true, usuniete: {i}}};
          }}
        }}
        return {{blad: 'nie ma wskaźnika o takim identyfikatorze'}};
    """)


def czekaj_na_dane(symbol: str, sekund: float = 25, tolerancja: float = 0.05) -> Json:
    """Czeka, aż świece na wykresie naprawdę należą do podanego instrumentu.

    Zmierzone zachowanie TradingView: po zmianie symbolu `ch.symbol()` i nazwa
    serii zmieniają się natychmiast, ale świece przez chwilę pozostają stare.
    `dataReady` i `whenChartReady` wracają od razu i tego nie wychwytują.

    Dlatego sprawdzamy inaczej: pobieramy cenę z publicznego punktu TradingView
    i czekamy, aż ostatnia świeca się z nią zgodzi. To porównanie krzyżowe,
    niezależne od tego, co mówi sama strona.
    """
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    import dane as _dane

    try:
        odn = _dane.odczyt(symbol, ["close"]).get("close")
    except Exception as e:
        return {"potwierdzone": False, "powod": f"brak ceny odniesienia: {e}"}

    if not odn:
        return {"potwierdzone": False, "powod": "punkt publiczny nie zwrócił ceny"}

    koniec = time.time() + sekund
    ostatnia = None
    odstep = 0.3          # na początku sprawdzamy często, potem coraz rzadziej
    while time.time() < koniec:
        try:
            w = swiece(2)
            if w.get("swiece"):
                ostatnia = w["swiece"][-1]["zamkniecie"]
                if ostatnia and abs(ostatnia - odn) / odn <= tolerancja:
                    return {"potwierdzone": True, "cena_wykresu": ostatnia,
                            "cena_odniesienia": odn}
        except BladWykresu:
            pass
        time.sleep(odstep)
        odstep = min(odstep * 1.6, 2.0)

    return {"potwierdzone": False,
            "powod": f"po {sekund}s świece nadal nie pasują do instrumentu",
            "cena_wykresu": ostatnia, "cena_odniesienia": odn}


def _przejdz(url: str) -> None:
    """Przeładowuje kartę pod wskazany adres."""
    _cdp("Page.navigate", {"url": url}, 30, 20)


# Ile sekund powinno dzielić dwie sąsiednie świece przy danym przedziale.
ODSTEP_SEKUND = {
    "1": 60, "3": 180, "5": 300, "15": 900, "30": 1800,
    "60": 3600, "120": 7200, "180": 10800, "240": 14400,
    "D": 86400, "1D": 86400, "W": 604800, "1W": 604800,
}


def sprawdz_przedzial(interwal: str, tolerancja: float = 0.2) -> Json:
    """Czy świece naprawdę mają odstęp odpowiadający przedziałowi.

    Zmierzone: `setResolution` zmienia nazwę przedziału natychmiast, ale świece
    potrafią zostać z poprzedniego. Wykres pokazuje wtedy "1D", a odstęp między
    świecami wynosi godzinę. Sama nazwa nie wystarcza, trzeba zmierzyć odstęp.
    """
    oczekiwany = ODSTEP_SEKUND.get(str(interwal).upper().lstrip("1")
                                   if str(interwal).upper() in ("1D", "1W")
                                   else str(interwal))
    if oczekiwany is None:
        return {"potwierdzone": None, "powod": f"nie znam odstępu dla {interwal}"}

    try:
        w = swiece(3)
    except BladWykresu as e:
        return {"potwierdzone": False, "powod": str(e)[:70]}

    s = w.get("swiece") or []
    if len(s) < 2:
        return {"potwierdzone": False, "powod": "za mało świec do zmierzenia odstępu"}

    faktyczny = s[-1]["czas"] - s[-2]["czas"]
    zgadza = abs(faktyczny - oczekiwany) / oczekiwany <= tolerancja

    return {
        "potwierdzone": zgadza,
        "przedzial": interwal,
        "odstep_oczekiwany_s": oczekiwany,
        "odstep_faktyczny_s": faktyczny,
        "powod": "" if zgadza else
                 f"świece mają odstęp {faktyczny}s zamiast {oczekiwany}s — "
                 "wykres nie przeładował danych",
    }


def przelacz(symbol: str, interwal: str | None = None, sekund: float = 30) -> Json:
    """Zmienia instrument i CZEKA na jego prawdziwe dane.

    Używaj tego zamiast samego `ustaw_symbol`, gdy zaraz potem czytasz świece.

    Zmierzone zachowanie TradingView: `setSymbol` zmienia nazwę instrumentu
    natychmiast, ale seria świec potrafi zostać przy poprzednim. Wykres pokazuje
    wtedy jedną nazwę, a zwraca ceny innego instrumentu — statystyka policzona
    na takich danych jest bezwartościowa, a nic tego nie sygnalizuje.

    Dlatego najpierw próbujemy normalnej zmiany, sprawdzamy krzyżowo z ceną
    z publicznego punktu, a gdy się nie zgadza, przeładowujemy stronę z symbolem
    w adresie. To zawsze daje właściwe dane, tylko trwa dłużej.
    """
    ustaw_symbol(symbol)          # waliduje symbol, zanim cokolwiek ruszy
    if interwal:
        ustaw_interwal(interwal)

    # Bez sztywnych pauz: zmierzone, że dane bywają gotowe w 0,2 s, a czekanie
    # na sztywno kosztowało cztery sekundy przy każdym przełączeniu.
    # czekaj_na_dane sprawdza w pętli i wraca, gdy tylko cena się zgodzi.
    w = czekaj_na_dane(symbol, min(sekund / 3, 8))
    p_ok = True
    p_info = {}
    if interwal:
        p_info = sprawdz_przedzial(interwal)
        p_ok = p_info.get("potwierdzone") is not False

    if w.get("potwierdzone") and p_ok:
        return {"symbol": symbol, "interwal": interwal,
                "sposob": "zmiana na miejscu", **w,
                "przedzial_sprawdzony": p_info.get("potwierdzone"),
                "odstep_swiec_s": p_info.get("odstep_faktyczny_s")}

    # dane nie nadążyły — przeładowanie z symbolem w adresie
    _przejdz(_adres_wykresu(symbol, interwal))
    time.sleep(12)

    w2 = czekaj_na_dane(symbol, sekund)
    p2 = sprawdz_przedzial(interwal) if interwal else {}
    return {"symbol": symbol, "interwal": interwal,
            "sposob": "przeładowanie strony", **w2,
            "przedzial_sprawdzony": p2.get("potwierdzone"),
            "odstep_swiec_s": p2.get("odstep_faktyczny_s"),
            "potwierdzone": bool(w2.get("potwierdzone"))
                            and p2.get("potwierdzone") is not False}


def _demo() -> int:
    """Sprawdzenie na żywej przeglądarce — uruchom ten plik wprost."""
    print("1. zdrowie")
    z = zdrowie()
    for k, v in z.items():
        print(f"   {k:14} {v}")
    if not z.get("gotowy"):
        print("\n   wykres niedostępny — reszta testów pominięta")
        return 1

    print("\n2. stan wykresu")
    s = stan()
    print(f"   symbol:     {s['symbol']}")
    print(f"   interwal:   {s['interwal']}")
    print(f"   typ:        {s['typ_wykresu']}")
    print(f"   wskazniki:  {len(s['wskazniki'])} {[w['nazwa'] for w in s['wskazniki']][:4]}")
    print(f"   rysunki:    {len(s['rysunki'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_demo())
