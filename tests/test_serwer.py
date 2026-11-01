"""Serwer MCP: walidacja argumentów, limity czasu i wielkości, błędy bez wycieków."""
import asyncio
import json
import sys
import types

import pytest


def _atrapa_mcp():
    """Testy nie zależą od wersji pakietu `mcp` (serwer używa dekoratorów z 1.x,
    a w 2.x ich nie ma) ani od jego działania: podstawiamy minimalną atrapę."""
    class Server:
        def __init__(self, nazwa):
            pass

        def list_tools(self):
            return lambda f: f

        def call_tool(self):
            return lambda f: f

    class Tool:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class TextContent:
        def __init__(self, type, text):
            self.type, self.text = type, text

    for nazwa in ("mcp", "mcp.server", "mcp.server.stdio", "mcp.types"):
        sys.modules[nazwa] = types.ModuleType(nazwa)
    sys.modules["mcp.server"].Server = Server
    sys.modules["mcp.server.stdio"].stdio_server = lambda: None
    sys.modules["mcp.types"].Tool = Tool
    sys.modules["mcp.types"].TextContent = TextContent


_atrapa_mcp()

import pine
import serwer
import walidacja as wal


def _wywolaj(nazwa, argumenty):
    wynik = asyncio.run(serwer.wywolaj(nazwa, argumenty))
    return json.loads(wynik[0].text)


def _bez_obslugi(monkeypatch):
    monkeypatch.setattr(serwer, "_obsluz",
                        lambda n, a: pytest.fail("zły argument doszedł do obsługi narzędzia"))


@pytest.mark.parametrize("nazwa,arg", [
    ("vgm_odczyt", {"symbol": "FX:EURUSD&x=1"}),
    ("vgm_odczyt", {"symbol": "FX:EURUSD", "pola": "RSI"}),                 # napis zamiast listy
    ("vgm_odczyt", {"symbol": "FX:EURUSD", "pola": ["RSI"] * 500}),
    ("vgm_wiele", {"symbole": ["FX:EURUSD"] * 500}),
    ("vgm_mtf", {"symbol": "FX:EURUSD", "interwaly": ["60; DROP"]}),
    ("vgm_skan_wyprzedane", {"rynek": "../../x"}),
    ("vgm_skan_wyprzedane", {"ile": 10**9}),
    ("vgm_skan_wyprzedane", {"ile": "dużo"}),
    ("vgm_skan_wyprzedane", {"prog": float("nan")}),
    ("vgm_skan", {"rynek": "forex", "warunki": [{"left": "RSI", "operation": "rm", "right": 1}]}),
    ("vgm_wykres_swiece", {"ile": 10**9}),
    ("vgm_wykres_swiece", {"ile": -5}),
    ("vgm_replay_krok", {"ile": 501}),
    ("vgm_zmierz", {"po_ilu": 10**9}),
    ("vgm_zmierz", {"wskaznik": "os.system"}),
    ("vgm_zmierz", {"kierunek": "bokiem"}),
    ("vgm_zmierz", {"spread_proc": -1}),
    ("vgm_walk_forward", {"wskaznik": "RSI", "progi": [1] * 1000}),
    ("vgm_walk_forward", {"wskaznik": "RSI", "czesc_ucz": 5}),
    ("vgm_jak_dlugo_trzymac", {"dlugosci": [10**9]}),
    ("vgm_koszt_a_przewaga", {"koszty": ["a"]}),
    ("vgm_przeglad_instrumentow", {"instrumenty": [["FX:EURUSD", "60"]] * 100}),
    ("vgm_swiece_przedzialy", {"przedzialy": ["60"] * 100}),
    ("vgm_wskaznik_usun", {"id": "a'); x('"}),
    ("vgm_zrodlo_pine", {"id": "../../x"}),
    ("vgm_uklad_wybierz", {"indeks": "abc"}),
    ("vgm_wykres_typ", {"typ": 10**9}),
    ("vgm_odczyt", ["nie", "obiekt"]),
])
def test_zly_argument_odrzucony_przed_obsluga(nazwa, arg, monkeypatch):
    _bez_obslugi(monkeypatch)
    w = _wywolaj(nazwa, arg)
    assert "niepoprawny argument" in w["blad"]
    assert w["narzedzie"] == nazwa


def test_poprawne_argumenty_dochodza_do_obslugi(monkeypatch):
    zapisane = {}
    monkeypatch.setattr(serwer, "_obsluz", lambda n, a: zapisane.update(n=n, a=a) or '{"ok": 1}')
    w = _wywolaj("vgm_skan_wyprzedane", {"rynek": "forex", "prog": 25, "ile": 200})
    assert w == {"ok": 1}
    assert zapisane["a"] == {"rynek": "forex", "prog": 25, "ile": 200}


def test_brak_argumentow_to_pusty_obiekt(monkeypatch):
    monkeypatch.setattr(serwer, "_obsluz", lambda n, a: '{"a": %d}' % len(a))
    assert _wywolaj("vgm_rynki", None) == {"a": 0}


def test_za_duzo_argumentow(monkeypatch):
    _bez_obslugi(monkeypatch)
    assert "niepoprawny" in _wywolaj("vgm_rynki", {f"k{i}": 1 for i in range(100)})["blad"]


# ── limit czasu: zawieszone wywołanie nie blokuje serwera ───────────────
def test_zawieszone_narzedzie_konczy_sie_limitem_czasu(monkeypatch):
    import threading

    zwolnij = threading.Event()
    monkeypatch.setattr(serwer, "CZAS_NARZEDZIA_S", 0.2)
    monkeypatch.setattr(serwer, "_obsluz", lambda n, a: zwolnij.wait(5) and "{}")
    try:
        w = _wywolaj("vgm_rynki", {})
    finally:
        zwolnij.set()
    assert "limit" in w["blad"]


def test_wywolania_sa_szeregowane(monkeypatch):
    """Wykres i limity zapytań nie są bezpieczne wątkowo — dwa wywołania nie nakładają się.

    Bez time.sleep (conftest i tak go wyłącza, więc stara wersja nigdy nie
    nakładała wywołań): pierwsze wywołanie trzyma obsługę, dopóki drugie nie
    dotrze albo do zamka, albo — gdy zamka nie ma — do samej obsługi.
    Dopiero wtedy pierwsze jest zwalniane. Wszystkie oczekiwania mają limit,
    żeby błąd kończył test, a nie zawieszał go.
    """
    import threading

    pierwszy_w_srodku = threading.Event()
    drugi_dotarl = threading.Event()
    zwolnij = threading.Event()
    licznik = threading.Lock()
    aktywne, maks, wejscia = [0], [0], [0]

    class ZamekSledzacy:
        """Prawdziwy zamek, który zgłasza, że drugie wywołanie próbuje wejść."""

        def __init__(self):
            self._zamek = threading.Lock()
            self._prob = 0

        def __enter__(self):
            with licznik:
                self._prob += 1
                if self._prob == 2:
                    drugi_dotarl.set()
            self._zamek.acquire()
            return self

        def __exit__(self, *a):
            self._zamek.release()
            return False

    def obsluga(n, a):
        with licznik:
            aktywne[0] += 1
            wejscia[0] += 1
            maks[0] = max(maks[0], aktywne[0])
            ktory = wejscia[0]
        if ktory == 1:
            pierwszy_w_srodku.set()
        else:
            drugi_dotarl.set()
        zwolnij.wait(5)
        with licznik:
            aktywne[0] -= 1
        return "{}"

    monkeypatch.setattr(serwer, "_ZAMEK", ZamekSledzacy())
    monkeypatch.setattr(serwer, "_obsluz", obsluga)

    async def scenariusz():
        pierwsze = asyncio.create_task(serwer.wywolaj("vgm_rynki", {}))
        assert await asyncio.to_thread(pierwszy_w_srodku.wait, 5), "pierwsze nie weszło"
        drugie = asyncio.create_task(serwer.wywolaj("vgm_rynki", {}))
        assert await asyncio.to_thread(drugi_dotarl.wait, 5), "drugie nie dotarło"
        zwolnij.set()
        return await asyncio.gather(pierwsze, drugie)

    try:
        wyniki = asyncio.run(scenariusz())
    finally:
        zwolnij.set()
    assert [json.loads(w[0].text) for w in wyniki] == [{}, {}]
    assert wejscia[0] == 2
    assert maks[0] == 1, "dwa wywołania były jednocześnie w obsłudze narzędzia"


# ── wyjątki i wielkość odpowiedzi ───────────────────────────────────────
def test_nieoczekiwany_wyjatek_bez_sladu_stosu_i_sciezek(monkeypatch):
    def pada(n, a):
        raise RuntimeError("/home/user/.ssh/id_rsa nie istnieje")

    monkeypatch.setattr(serwer, "_obsluz", pada)
    w = _wywolaj("vgm_rynki", {})
    assert w["blad"].startswith("RuntimeError")
    assert "Traceback" not in json.dumps(w)


def test_zbyt_duza_odpowiedz_nie_jest_zwracana(monkeypatch):
    monkeypatch.setattr(serwer, "_obsluz", lambda n, a: "x" * (wal.MAX_WYNIK_ZNAKOW + 1))
    assert "za duży" in _wywolaj("vgm_rynki", {})["blad"]


# ── Pine: plik i usuwanie ───────────────────────────────────────────────
def test_pine_sprawdz_plik_poza_katalogiem_bazowym(monkeypatch, tmp_path):
    sekret = tmp_path / "sekret.txt"
    sekret.write_text("haslo=123")
    baza = tmp_path / "pine"
    baza.mkdir()
    monkeypatch.setenv("VGM_KATALOG_PINE", str(baza))
    monkeypatch.setattr(pine, "sprawdz", lambda k: pytest.fail("treść pliku wysłana do TradingView"))
    for zla in (str(sekret), "../sekret.txt", "/etc/passwd"):
        w = _wywolaj("vgm_pine_sprawdz_plik", {"sciezka": zla})
        assert "blad" in w
    assert "haslo" not in json.dumps(w)


def test_pine_sprawdz_plik_z_katalogu_bazowego_dziala(monkeypatch, tmp_path):
    (tmp_path / "a.pine").write_text("//@version=5\nindicator('x')")
    monkeypatch.setenv("VGM_KATALOG_PINE", str(tmp_path))
    monkeypatch.setattr(pine, "sprawdz", lambda k: {"poprawny": True, "bledy": []})
    w = _wywolaj("vgm_pine_sprawdz_plik", {"sciezka": "a.pine"})
    assert w["poprawny"] is True


def test_szkielet_nazwa_nie_wstrzykuje_kodu_pine():
    with pytest.raises(pine.BladPine):
        pine.szkielet('x")\nstrategy.entry("a", strategy.long')
    assert 'indicator("Moja nazwa"' in pine.szkielet("Moja nazwa")


def test_usun_pine_wymaga_potwierdzenia(monkeypatch):
    import sesja
    monkeypatch.setattr(sesja, "usun_pine", lambda i: pytest.fail("usunięto bez potwierdzenia"))
    for arg in ({"id": "USER;abc"}, {"id": "USER;abc", "potwierdz": False}, {"id": "USER;abc", "potwierdz": "tak"}):
        w = _wywolaj("vgm_usun_pine", arg)
        assert "blad" in w


def test_usun_pine_z_potwierdzeniem(monkeypatch):
    import sesja
    monkeypatch.setattr(sesja, "usun_pine", lambda i: {"usuniety": True, "id": i})
    w = _wywolaj("vgm_usun_pine", {"id": "USER;abc", "potwierdz": True})
    assert w == {"usuniety": True, "id": "USER;abc"}


def test_zrzut_zla_sciezka_przez_serwer(monkeypatch, tmp_path):
    import wykres
    monkeypatch.setenv("VGM_KATALOG_ZRZUTOW", str(tmp_path))
    monkeypatch.setattr(wykres, "_karta", lambda: pytest.fail("ruszył przeglądarkę"))
    w = _wywolaj("vgm_wykres_zrzut", {"sciezka": "/root/.bashrc", "zamknij_okna": False})
    assert "blad" in w
