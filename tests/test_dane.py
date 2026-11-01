"""Testy warstwy danych na nagranych odpowiedziach — bez sieci."""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

import dane


class Odpowiedz:
    """Udaje odpowiedź urlopen (menedżer kontekstu z .read())."""

    def __init__(self, tresc):
        self._b = json.dumps(tresc).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self._b if n < 0 else self._b[:n]


def blad_http(kod):
    return urllib.error.HTTPError("http://x", kod, "x", {}, io.BytesIO(b""))


@pytest.fixture
def urlopen(monkeypatch):
    """Podmienia otwieracz z `siec` (jedyne wyjście HTTP) kolejką odpowiedzi;
    zapisuje wysłane zapytania."""
    def ustaw(*kolejka):
        kolejka = list(kolejka)
        wyslane = []

        def falszywy(req, timeout=None):
            wyslane.append(req)
            x = kolejka.pop(0)
            if isinstance(x, Exception):
                raise x
            return Odpowiedz(x)

        monkeypatch.setattr(dane.siec._OPENER, "open", falszywy)
        return wyslane

    return ustaw


# ── _pobierz ────────────────────────────────────────────────────────────
def test_pobierz_get_bez_ciala_i_z_naglowkiem_curl(urlopen):
    wyslane = urlopen({"ok": 1})
    assert dane._pobierz("/symbol?x=1") == {"ok": 1}
    req = wyslane[0]
    assert req.full_url == "https://scanner.tradingview.com/symbol?x=1"
    assert req.data is None
    assert req.get_header("User-agent") == "curl/8.5.0"


def test_pobierz_post_wysyla_json(urlopen):
    wyslane = urlopen({"data": []})
    dane._pobierz("/forex/scan", {"a": 1})
    assert json.loads(wyslane[0].data) == {"a": 1}
    assert wyslane[0].get_header("Content-type") == "application/json"


@pytest.mark.parametrize("kod", [403, 429])
def test_pobierz_przy_403_i_429_nie_ponawia(urlopen, kod):
    wyslane = urlopen(blad_http(kod), {"nie": "powinno dojść"})
    with pytest.raises(dane.BladTV, match=str(kod)):
        dane._pobierz("/symbol")
    assert len(wyslane) == 1


def test_pobierz_ponawia_przy_500_i_zwraca_wynik(urlopen):
    wyslane = urlopen(blad_http(500), {"ok": True})
    assert dane._pobierz("/symbol") == {"ok": True}
    assert len(wyslane) == 2


def test_pobierz_po_wyczerpaniu_prob_rzuca_bladtv(urlopen):
    urlopen(blad_http(500), blad_http(502))
    with pytest.raises(dane.BladTV, match="HTTP 502"):
        dane._pobierz("/symbol")


def test_pobierz_blad_sieci_zamieniany_na_bladtv(urlopen):
    urlopen(TimeoutError("czas"), TimeoutError("czas"))
    with pytest.raises(dane.BladTV, match="TimeoutError"):
        dane._pobierz("/symbol")


# ── odczyt ──────────────────────────────────────────────────────────────
def test_odczyt_buduje_adres_z_polami(monkeypatch):
    wyslane = []
    monkeypatch.setattr(dane, "_pobierz",
                        lambda s, d=None, p=2: wyslane.append(s) or {"close": 1.1})
    assert dane.odczyt("FX:EURUSD", ["close", "RSI|60"]) == {"close": 1.1}
    assert wyslane == ["/symbol?symbol=FX%3AEURUSD&fields=close%2CRSI%7C60"]


def test_odczyt_domyslne_pola(monkeypatch):
    wyslane = []
    monkeypatch.setattr(dane, "_pobierz",
                        lambda s, d=None, p=2: wyslane.append(s) or {"close": 1})
    dane.odczyt("FX:EURUSD")
    assert "RSI" in wyslane[0] and "Recommend.All" in wyslane[0]


@pytest.mark.parametrize("odp", [{}, [], None, "tekst"])
def test_odczyt_pusta_lub_dziwna_odpowiedz_to_bladtv(monkeypatch, odp):
    monkeypatch.setattr(dane, "_pobierz", lambda s, d=None, p=2: odp)
    with pytest.raises(dane.BladTV, match="brak danych dla ZLY"):
        dane.odczyt("ZLY")


# ── wiele / przeglad ────────────────────────────────────────────────────
def test_wiele_skleja_symbol_z_kolumnami(monkeypatch):
    zapytania = []

    def pobierz(s, d=None, p=2):
        zapytania.append((s, d))
        return {"data": [{"s": "FX:EURUSD", "d": [1.1, 0.5]},
                         {"s": "FX:GBPUSD", "d": [1.3, None]}]}

    monkeypatch.setattr(dane, "_pobierz", pobierz)
    w = dane.wiele(["FX:EURUSD", "FX:GBPUSD"], ["close", "RSI"])
    assert w == [{"symbol": "FX:EURUSD", "close": 1.1, "RSI": 0.5},
                 {"symbol": "FX:GBPUSD", "close": 1.3, "RSI": None}]
    assert zapytania[0][1]["symbols"] == {"tickers": ["FX:EURUSD", "FX:GBPUSD"]}


def test_wiele_bez_danych_zwraca_pusta_liste(monkeypatch):
    monkeypatch.setattr(dane, "_pobierz", lambda s, d=None, p=2: {})
    assert dane.wiele(["X"]) == []


def test_przeglad_uzywa_rynku_w_adresie_i_zakresu(monkeypatch):
    zapytania = []

    def pobierz(s, d=None, p=2):
        zapytania.append((s, d))
        return {"data": [{"s": "FX:A", "d": [1, 2, 3, 4, 5]}]}

    monkeypatch.setattr(dane, "_pobierz", pobierz)
    warunki = [{"left": "RSI", "operation": "less", "right": 30}]
    w = dane.przeglad("crypto", warunki, ile=7)
    assert zapytania[0][0] == "/crypto/scan"
    assert zapytania[0][1]["filter"] == warunki
    assert zapytania[0][1]["range"] == [0, 7]
    assert w == [{"symbol": "FX:A", "close": 1, "change": 2, "RSI": 3,
                  "ADX": 4, "volume": 5}]


# ── mtf / zgodnosc ──────────────────────────────────────────────────────
def test_mtf_grupuje_po_wskazniku_i_interwale(atrapa_tv):
    a = atrapa_tv({"RSI|5": 40.0, "RSI|60": 60.0, "ADX|5": 20.0, "ADX|60": None})
    w = dane.mtf("FX:EURUSD", ["RSI", "ADX"], ["5", "60"])
    assert w == {"RSI": {"5": 40.0, "60": 60.0}, "ADX": {"5": 20.0, "60": None}}
    assert a.wywolania[0][1] == ["RSI|5", "RSI|60", "ADX|5", "ADX|60"]


def test_mtf_domyslne_wskazniki_i_interwaly(atrapa_tv):
    a = atrapa_tv({})
    w = dane.mtf("FX:EURUSD")
    assert list(w) == ["RSI", "ADX", "Recommend.All"]
    assert list(w["RSI"]) == ["5", "15", "60", "240"]
    assert len(a.wywolania[0][1]) == 12


def test_mtf_pusty_interwal_daje_biezacy(atrapa_tv):
    atrapa_tv({"RSI": 50.0})
    assert dane.mtf("FX:EURUSD", ["RSI"], [""]) == {"RSI": {"biezacy": 50.0}}


def test_zgodnosc_wszystkie_za_kupnem(atrapa_tv):
    atrapa_tv({"RSI|5": 60, "RSI|15": 55, "RSI|60": 70, "RSI|240": 80})
    z = dane.zgodnosc("FX:EURUSD")
    assert z["za_kupnem"] == ["15", "240", "5", "60"]
    assert z["za_sprzedaza"] == []
    assert z["wszystkie_zgodne"] is True


def test_zgodnosc_wszystkie_za_sprzedaza_na_progu(atrapa_tv):
    atrapa_tv({"RSI|5": 45, "RSI|15": 30, "RSI|60": 10, "RSI|240": 44.9})
    z = dane.zgodnosc("FX:EURUSD")
    assert len(z["za_sprzedaza"]) == 4
    assert z["wszystkie_zgodne"] is True


def test_zgodnosc_mieszana_i_braki(atrapa_tv):
    atrapa_tv({"RSI|5": 60, "RSI|15": 30, "RSI|60": 50, "RSI|240": None})
    z = dane.zgodnosc("FX:EURUSD")
    assert z["za_kupnem"] == ["5"]
    assert z["za_sprzedaza"] == ["15"]
    assert z["bez_danych"] == ["240"]
    assert z["wszystkie_zgodne"] is False


def test_zgodnosc_wlasne_progi(atrapa_tv):
    atrapa_tv({"RSI|5": 52, "RSI|15": 53})
    z = dane.zgodnosc("X", ["5", "15"], prog_kupno=50, prog_sprzedaz=40)
    assert z["wszystkie_zgodne"] is True


def test_zgodnosc_brak_interwalu_w_odpowiedzi_nie_daje_zgodnosci(atrapa_tv, monkeypatch):
    # TradingView potrafi pominąć pole — wtedy interwał nie może liczyć się jako zgodny
    monkeypatch.setattr(dane, "odczyt", lambda s, p=None: {"RSI|5": 60.0})
    z = dane.zgodnosc("X", ["5", "15"])
    assert z["wszystkie_zgodne"] is False
    assert z["bez_danych"] == ["15"]


def test_zgodnosc_pusty_interwal_to_biezacy_a_nie_brak(atrapa_tv):
    # interwaly=[""] to bieżący przedział; wartość wraca pod kluczem "biezacy",
    # więc nie wolno jej zgłosić jako brakującej
    a = atrapa_tv({"RSI": 60.0})
    z = dane.zgodnosc("FX:EURUSD", [""])
    assert a.wywolania[0][1] == ["RSI"]
    assert z["rsi"] == {"biezacy": 60.0}
    assert z["bez_danych"] == []
    assert z["za_kupnem"] == ["biezacy"]
    assert z["wszystkie_zgodne"] is True


def test_zgodnosc_pusty_interwal_bez_wartosci_to_brak_biezacego(atrapa_tv):
    atrapa_tv({"RSI": None, "RSI|60": 70.0})
    z = dane.zgodnosc("FX:EURUSD", ["", "60"])
    assert z["bez_danych"] == ["biezacy"]
    assert z["za_kupnem"] == ["60"]
    assert z["wszystkie_zgodne"] is False
