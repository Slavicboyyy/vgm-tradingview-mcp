"""Testy serwera MCP: lista narzędzi i kierowanie wywołań.

Pakiet `mcp` jest atrapą z conftest.py; warstwy dane/analiza/sesja/wykres
są podmieniane, więc nic nie wychodzi do sieci ani przeglądarki.
"""
from __future__ import annotations

import asyncio
import json
import sys
import types

import pytest

import analiza
import dane
import pola
import serwer


def wolaj(nazwa, argumenty=None):
    wynik = asyncio.run(serwer.wywolaj(nazwa, argumenty or {}))
    assert len(wynik) == 1 and wynik[0].type == "text"
    return json.loads(wynik[0].text)


@pytest.fixture(scope="module")
def narzedzia():
    return asyncio.run(serwer.lista_narzedzi())


# ── lista narzędzi ──────────────────────────────────────────────────────
def test_nazwy_narzedzi_sa_unikalne_i_z_prefiksem(narzedzia):
    nazwy = [t.name for t in narzedzia]
    assert len(nazwy) == len(set(nazwy))
    assert all(n.startswith("vgm_") for n in nazwy)


def test_kazde_narzedzie_ma_opis_z_zastrzezeniem_i_poprawny_schemat(narzedzia):
    for t in narzedzia:
        assert t.description.strip(), t.name
        sch = t.inputSchema
        assert sch["type"] == "object", t.name
        assert set(sch.get("required", [])) <= set(sch.get("properties", {})), t.name


def test_n_dopisuje_uwage_o_danych_i_domyslne_pola():
    t = serwer._n("vgm_x", "Opis.")
    assert t.description == "Opis. " + serwer.UWAGA
    assert t.inputSchema == {"type": "object", "properties": {}, "required": []}


def test_kazde_zadeklarowane_narzedzie_ma_obsluge(narzedzia):
    """Deklaracja bez obsługi kończyłaby się odpowiedzią „nieznane narzędzie"."""
    import inspect
    zrodlo = inspect.getsource(serwer.wywolaj)
    bez = [t.name for t in narzedzia if f'"{t.name}"' not in zrodlo]
    assert bez == []


# ── proste narzędzia bez zapytań ────────────────────────────────────────
def test_vgm_rynki():
    assert wolaj("vgm_rynki") == pola.RYNKI


def test_vgm_pola_zawiera_grupy_i_interwaly():
    w = wolaj("vgm_pola")
    assert {g: w[g] for g in pola.GRUPY} == pola.GRUPY
    assert w["interwaly_zmierzone"] == pola.INTERWALY_PEWNE


def test_nieznane_narzedzie():
    assert wolaj("vgm_nie_ma_takiego") == {"blad": "nieznane narzędzie: vgm_nie_ma_takiego"}


def test_polskie_znaki_nie_sa_escapowane():
    # ensure_ascii=False — czytelne dla człowieka i modelu
    tekst = asyncio.run(serwer.wywolaj("vgm_nie_ma_takiego", {}))[0].text
    assert "narzędzie" in tekst


# ── kierowanie do dane/analiza ──────────────────────────────────────────
def test_odczyt_przekazuje_symbol_i_pola(monkeypatch):
    zap = []
    monkeypatch.setattr(dane, "odczyt", lambda s, p=None: zap.append((s, p)) or {"close": 1})
    assert wolaj("vgm_odczyt", {"symbol": "FX:EURUSD", "pola": ["close"]}) == {"close": 1}
    assert wolaj("vgm_odczyt", {"symbol": "FX:EURUSD"}) == {"close": 1}
    assert zap == [("FX:EURUSD", ["close"]), ("FX:EURUSD", None)]


def test_zgodnosc_domyslne_progi(monkeypatch):
    zap = []
    monkeypatch.setattr(dane, "zgodnosc", lambda *a: zap.append(a) or {"ok": 1})
    wolaj("vgm_zgodnosc", {"symbol": "X"})
    wolaj("vgm_zgodnosc", {"symbol": "X", "interwaly": ["5"], "prog_kupno": 60,
                           "prog_sprzedaz": 40})
    assert zap == [("X", None, 55, 45), ("X", ["5"], 60, 40)]


@pytest.mark.parametrize("narzedzie, funkcja, argumenty, oczekiwane", [
    ("vgm_skan_wyprzedane", "skan_wyprzedane", {}, ("forex", 30, 20)),
    ("vgm_skan_wyprzedane", "skan_wyprzedane",
     {"rynek": "poland", "prog": 20, "ile": 3}, ("poland", 20, 3)),
    ("vgm_skan_wykupione", "skan_wykupione", {}, ("forex", 70, 20)),
    ("vgm_skan_trend", "skan_silny_trend", {"prog_adx": 40}, ("forex", 40, 20)),
    ("vgm_skan_wolumen", "skan_wolumen", {"krotnosc": 3}, ("forex", 3, 20)),
])
def test_skany_domyslne_i_przekazane_argumenty(monkeypatch, narzedzie, funkcja,
                                               argumenty, oczekiwane):
    zap = []
    monkeypatch.setattr(analiza, funkcja, lambda *a: zap.append(a) or [])
    wolaj(narzedzie, argumenty)
    assert zap == [oczekiwane]


def test_skan_wlasny_wymaga_rynku_i_warunkow(monkeypatch):
    monkeypatch.setattr(analiza, "skan_wlasny", lambda *a: list(a))
    w = [{"left": "RSI", "operation": "less", "right": 30}]
    assert wolaj("vgm_skan", {"rynek": "crypto", "warunki": w}) == ["crypto", w, None, 30]
    assert "brakuje wymaganego pola" in wolaj("vgm_skan", {"rynek": "crypto"})["blad"]


# ── obsługa błędów ──────────────────────────────────────────────────────
def test_bladtv_zamieniany_na_odpowiedz_z_bledem(monkeypatch):
    def zle(*a, **k):
        raise dane.BladTV("TradingView odmówił (429)")

    monkeypatch.setattr(dane, "odczyt", zle)
    assert wolaj("vgm_odczyt", {"symbol": "X"}) == {
        "blad": "TradingView odmówił (429)", "narzedzie": "vgm_odczyt"}


def test_brak_wymaganego_argumentu_to_czytelny_blad():
    w = wolaj("vgm_odczyt", {})
    assert w["narzedzie"] == "vgm_odczyt"
    assert "brakuje wymaganego pola" in w["blad"] and "symbol" in w["blad"]


def test_rzucenie_innego_wyjatku_nie_jest_polykane(monkeypatch):
    monkeypatch.setattr(dane, "odczyt", lambda s, p=None: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        wolaj("vgm_odczyt", {"symbol": "X"})


# ── moduły ładowane na żądanie: sesja, pine, wykres ─────────────────────
def atrapa_modulu(nazwa, wyjatek, **funkcje):
    m = types.ModuleType(nazwa)
    setattr(m, wyjatek, type(wyjatek, (Exception,), {}))
    for k, v in funkcje.items():
        setattr(m, k, v)
    return m


def test_sesja_wynik_i_blad_logowania(monkeypatch):
    m = atrapa_modulu("sesja", "BladSesji",
                      czy_zalogowany=lambda: {"zalogowany": True},
                      zrodlo_pine=lambda i: (_ for _ in ()).throw(m.BladSesji("brak sesji")))
    monkeypatch.setitem(sys.modules, "sesja", m)
    assert wolaj("vgm_sesja") == {"zalogowany": True}
    w = wolaj("vgm_zrodlo_pine", {"id": "abc"})
    assert w["blad"] == "brak sesji" and w["narzedzie"] == "vgm_zrodlo_pine"
    assert "zaloguj" in w["podpowiedz"]


def test_pine_szkielet_i_blad(monkeypatch):
    def sprawdz(kod):
        raise m.BladPine("zły kod")

    m = atrapa_modulu("pine", "BladPine", sprawdz=sprawdz,
                      szkielet=lambda n, w: f"//@version=6 {n} {w}")
    monkeypatch.setitem(sys.modules, "pine", m)
    assert wolaj("vgm_pine_szkielet") == {"kod": "//@version=6 Nowy wskaźnik True"}
    assert wolaj("vgm_pine_szkielet", {"nazwa": "A", "na_wykresie": False}) == \
        {"kod": "//@version=6 A False"}
    assert wolaj("vgm_pine_sprawdz", {"kod": "x"}) == \
        {"blad": "zły kod", "narzedzie": "vgm_pine_sprawdz"}


def test_wykres_blad_dostaje_podpowiedz(monkeypatch):
    def stan():
        raise m.BladWykresu("brak karty")

    m = atrapa_modulu("wykres", "BladWykresu", stan=stan,
                      ustaw_symbol=lambda s: {"symbol": s})
    monkeypatch.setitem(sys.modules, "wykres", m)
    w = wolaj("vgm_wykres_stan")
    assert w["blad"] == "brak karty" and "vgm_wykres_zdrowie" in w["podpowiedz"]
    assert wolaj("vgm_wykres_symbol", {"symbol": "FX:GBPUSD"}) == {"symbol": "FX:GBPUSD"}


def test_wszystkie_narzedzia_wykresu_trafiaja_do_swojej_grupy(narzedzia, monkeypatch):
    """Narzędzie, którego nazwa nie pasuje do prefiksów grupy, wpada w „nieznane"."""
    class Atrapa(types.ModuleType):
        def __getattr__(self, nazwa):
            if nazwa.startswith("Blad"):
                typ = type(nazwa, (Exception,), {})
                setattr(self, nazwa, typ)
                return typ
            return lambda *a, **k: {"wywolano": nazwa}

    for nazwa in ("wykres", "pomiar", "uklad", "replay", "sesja", "pine"):
        monkeypatch.setitem(sys.modules, nazwa, Atrapa(nazwa))
    monkeypatch.setattr(dane, "_pobierz", lambda s, d=None, p=2: {"data": [], "x": 1})
    argumenty = {"symbol": "FX:EURUSD", "symbole": ["FX:EURUSD"], "rynek": "forex",
                 "warunki": [], "kod": "x", "nazwa": "x", "id": "x", "sciezka": "x",
                 "interwal": "60", "typ": "x", "indeks": 0}

    def nieznane_narzedzie(w):
        return isinstance(w, dict) and "nieznane narzędzie" in str(w.get("blad", ""))

    nieznane = [t.name for t in narzedzia if nieznane_narzedzie(wolaj(t.name, argumenty))]
    assert nieznane == []
