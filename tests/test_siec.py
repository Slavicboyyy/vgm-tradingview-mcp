"""Warstwa HTTP: lista hostów, brak przekierowań, limit rozmiaru, błędy sieci i limity czasu."""
import io
import json
import socket
import urllib.error
import urllib.request

import pytest

import dane
import pine
import sesja
import siec


class _Odp:
    def __init__(self, tresc: bytes):
        self._b = io.BytesIO(tresc)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self._b.read(n)


class _Opener:
    def __init__(self, tresc=b"{}", wyjatek=None):
        self.tresc, self.wyjatek, self.wywolania = tresc, wyjatek, []

    def open(self, zad, timeout=None):
        self.wywolania.append((zad.full_url, timeout))
        if self.wyjatek:
            raise self.wyjatek
        return _Odp(self.tresc)


def _req(url):
    return urllib.request.Request(url)


# ── lista hostów ────────────────────────────────────────────────────────
@pytest.mark.parametrize("url", [
    "http://scanner.tradingview.com/symbol",              # bez TLS
    "https://evil.example/pine-facade",                   # obcy host
    "https://scanner.tradingview.com.evil.example/x",     # podszycie sufiksem
    "https://evil.example/?h=scanner.tradingview.com",
    "https://user:haslo@scanner.tradingview.com/x",       # dane logowania w adresie
    "file:///etc/passwd",
    "https://127.0.0.1/x",
])
def test_adres_spoza_listy_odrzucony_zanim_cokolwiek_wyjdzie(url, monkeypatch):
    op = _Opener()
    monkeypatch.setattr(siec, "_OPENER", op)
    with pytest.raises(siec.BladSieci):
        siec.pobierz(_req(url), timeout=5)
    assert op.wywolania == []


def test_adres_z_listy_przechodzi_i_dostaje_timeout(monkeypatch):
    op = _Opener(b'{"a":1}')
    monkeypatch.setattr(siec, "_OPENER", op)
    assert siec.pobierz(_req("https://scanner.tradingview.com/symbol"), timeout=7) == b'{"a":1}'
    assert op.wywolania[0][1] == 7


# ── przekierowania ──────────────────────────────────────────────────────
def test_przekierowanie_jest_blokowane_zeby_cookie_nie_poszlo_na_obcy_host():
    h = siec._BezPrzekierowan()
    zad = urllib.request.Request("https://pine-facade.tradingview.com/x",
                                 headers={"Cookie": "sessionid=TAJNE"})
    with pytest.raises(urllib.error.HTTPError) as e:
        h.redirect_request(zad, io.BytesIO(b""), 302, "Found", {}, "https://evil.example/zbierz")
    assert e.value.code == 302
    assert "zablokowane" in e.value.msg


def test_opener_uzywa_handlera_bez_przekierowan():
    assert any(isinstance(h, siec._BezPrzekierowan) for h in siec._OPENER.handlers)


# ── rozmiar odpowiedzi ──────────────────────────────────────────────────
def test_zbyt_duza_odpowiedz_odrzucona(monkeypatch):
    monkeypatch.setattr(siec, "_OPENER", _Opener(b"x" * 101))
    with pytest.raises(siec.BladSieci):
        siec.pobierz(_req("https://scanner.tradingview.com/x"), timeout=5, max_bajtow=100)


def test_odpowiedz_w_limicie_przechodzi(monkeypatch):
    monkeypatch.setattr(siec, "_OPENER", _Opener(b"x" * 100))
    assert len(siec.pobierz(_req("https://scanner.tradingview.com/x"), timeout=5, max_bajtow=100)) == 100


# ── dane: limity czasu, ponawianie, 403/429 ─────────────────────────────
def test_dane_timeout_konczy_sie_bladem_po_ograniczonej_liczbie_prob(monkeypatch):
    op = _Opener(wyjatek=socket.timeout("timed out"))
    monkeypatch.setattr(siec, "_OPENER", op)
    with pytest.raises(dane.BladTV) as e:
        dane.odczyt("FX:EURUSD", ["close"])
    assert "timeout" in str(e.value).lower() or "timed out" in str(e.value)
    assert len(op.wywolania) == 2                      # prob=2, bez pętli w nieskończoność
    assert all(t == 25 for _, t in op.wywolania)       # każda próba z limitem czasu


@pytest.mark.parametrize("kod", [403, 429])
def test_dane_403_i_429_zatrzymuja_bez_ponawiania(kod, monkeypatch):
    err = urllib.error.HTTPError("https://scanner.tradingview.com/x", kod, "x", {}, io.BytesIO(b""))
    op = _Opener(wyjatek=err)
    monkeypatch.setattr(siec, "_OPENER", op)
    with pytest.raises(dane.BladTV):
        dane.odczyt("FX:EURUSD", ["close"])
    assert len(op.wywolania) == 1


def test_dane_nie_json_to_bladtv_nie_surowy_wyjatek(monkeypatch):
    monkeypatch.setattr(siec, "_OPENER", _Opener(b"<html>nie json</html>"))
    with pytest.raises(dane.BladTV):
        dane.odczyt("FX:EURUSD", ["close"])


def test_dane_za_duza_odpowiedz_to_bladtv(monkeypatch):
    monkeypatch.setattr(siec, "MAX_ODPOWIEDZI", 10)
    monkeypatch.setattr(siec, "_OPENER", _Opener(b"{" + b" " * 50 + b"}"))
    with pytest.raises(dane.BladTV):
        dane.odczyt("FX:EURUSD", ["close"])


def test_dane_zly_rynek_nie_dociera_do_sieci(monkeypatch):
    op = _Opener()
    monkeypatch.setattr(siec, "_OPENER", op)
    for rynek in ("../../pine-facade/list", "forex/../x", "x?y=1"):
        with pytest.raises(Exception) as e:
            dane.przeglad(rynek)
        assert "rynek" in str(e.value)
    assert op.wywolania == []


def test_dane_przeglad_limit_ile_i_warunkow(monkeypatch):
    op = _Opener()
    monkeypatch.setattr(siec, "_OPENER", op)
    with pytest.raises(Exception):
        dane.przeglad("forex", ile=10**9)
    with pytest.raises(Exception):
        dane.przeglad("forex", [{"left": "RSI", "operation": "x", "right": 1}])
    assert op.wywolania == []


def test_dane_zly_symbol_i_zbyt_wiele_symboli_odrzucone_lokalnie(monkeypatch):
    op = _Opener()
    monkeypatch.setattr(siec, "_OPENER", op)
    with pytest.raises(Exception):
        dane.odczyt("FX:EURUSD&fields=close")
    with pytest.raises(Exception):
        dane.wiele(["FX:EURUSD"] * 1000)
    with pytest.raises(Exception):
        dane.wiele("FX:EURUSD")          # napis zamiast listy
    assert op.wywolania == []


# ── pine ────────────────────────────────────────────────────────────────
def test_pine_timeout_to_bladpine(monkeypatch):
    op = _Opener(wyjatek=socket.timeout("timed out"))
    monkeypatch.setattr(siec, "_OPENER", op)
    with pytest.raises(pine.BladPine):
        pine.sprawdz("//@version=5\nindicator('x')")
    assert op.wywolania[0][1] == 30


def test_pine_odpowiedz_nie_slownik_to_bladpine(monkeypatch):
    monkeypatch.setattr(siec, "_OPENER", _Opener(b"[1,2,3]"))
    with pytest.raises(pine.BladPine):
        pine.sprawdz("//@version=5\nindicator('x')")


def test_pine_ogromny_kod_nie_jest_wysylany(monkeypatch):
    op = _Opener()
    monkeypatch.setattr(siec, "_OPENER", op)
    with pytest.raises(pine.BladPine):
        pine.sprawdz("x" * 10_000_000)
    assert op.wywolania == []


def test_pine_dobra_odpowiedz(monkeypatch):
    monkeypatch.setattr(siec, "_OPENER",
                        _Opener(json.dumps({"success": True, "result": {"errors": []}}).encode()))
    assert pine.sprawdz("//@version=5\nindicator('x')")["poprawny"] is True


# ── sesja ───────────────────────────────────────────────────────────────
def test_sesja_obcy_host_nie_czyta_ciasteczek(monkeypatch):
    def nie_wolno():
        raise AssertionError("ciasteczka odczytane przed sprawdzeniem adresu")

    monkeypatch.setattr(sesja, "_naglowki", nie_wolno)
    for url in ("https://evil.example/x", "http://pine-facade.tradingview.com/x"):
        with pytest.raises(sesja.BladSesji):
            sesja._pobierz(url)


def _sesja_z_ciasteczkiem(monkeypatch, opener):
    monkeypatch.setattr(sesja, "_naglowki", lambda: {"Cookie": "sessionid=x"})
    monkeypatch.setattr(sesja, "_odczekaj", lambda: None)
    monkeypatch.setattr(siec, "_OPENER", opener)


def test_sesja_timeout_to_bladsesji(monkeypatch):
    _sesja_z_ciasteczkiem(monkeypatch, _Opener(wyjatek=socket.timeout("timed out")))
    with pytest.raises(sesja.BladSesji):
        sesja._pobierz("https://pricealerts.tradingview.com/list_alerts")


def test_sesja_blad_dns_i_url_error_to_bladsesji(monkeypatch):
    _sesja_z_ciasteczkiem(monkeypatch, _Opener(wyjatek=urllib.error.URLError("brak DNS")))
    with pytest.raises(sesja.BladSesji):
        sesja._pobierz("https://pricealerts.tradingview.com/list_alerts")


def test_sesja_nie_json_to_bladsesji(monkeypatch):
    _sesja_z_ciasteczkiem(monkeypatch, _Opener(b"<html>"))
    with pytest.raises(sesja.BladSesji):
        sesja._pobierz("https://pricealerts.tradingview.com/list_alerts")


def test_sesja_przekierowanie_to_bladsesji_bez_podazania(monkeypatch):
    err = urllib.error.HTTPError("https://pine-facade.tradingview.com/x", 302,
                                 "przekierowanie", {}, io.BytesIO(b""))
    op = _Opener(wyjatek=err)
    _sesja_z_ciasteczkiem(monkeypatch, op)
    with pytest.raises(sesja.BladSesji):
        sesja._pobierz("https://pine-facade.tradingview.com/pine-facade/list/?filter=saved")
    assert len(op.wywolania) == 1


def test_sesja_id_skryptu_nie_wychodzi_poza_sciezke(monkeypatch):
    monkeypatch.setattr(sesja, "_pobierz", lambda u: pytest.fail("nie powinno dojść do sieci"))
    for zle in ("../../list", "a/b", "a?b=1", "", "x" * 500):
        with pytest.raises(Exception):
            sesja.zrodlo_pine(zle)


def test_sesja_zapis_i_usuniecie_waliduja_wejscie(monkeypatch):
    monkeypatch.setattr(sesja, "_pine_api", lambda *a, **k: pytest.fail("nie powinno dojść do przeglądarki"))
    with pytest.raises(Exception):
        sesja.zapisz_pine("x" * 10_000_000, "nazwa")
    with pytest.raises(Exception):
        sesja.zapisz_pine("//@version=5", 'a"; deleteAll(); "')
    with pytest.raises(Exception):
        sesja.usun_pine("x; deleteAll()")
