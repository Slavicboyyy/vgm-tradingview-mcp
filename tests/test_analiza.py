"""Testy warstwy analizy: dane z atrapy TradingView, świece z atrapy wykresu."""
from __future__ import annotations

import sys
import types

import pytest

import analiza
import dane
import pola


def swieca(o, h, l, c, czas=0):
    return {"czas": czas, "otwarcie": o, "szczyt": h, "dolek": l, "zamkniecie": c}


# ── obraz ───────────────────────────────────────────────────────────────
def test_obraz_grupuje_pola_i_pomija_puste(atrapa_tv):
    atrapa_tv({"close": 1.1, "RSI": 55.0, "ADX": None, "SMA50": 1.0})
    o = analiza.obraz("FX:EURUSD")
    assert o["symbol"] == "FX:EURUSD" and o["interwal"] == "biezacy"
    assert o["cena"] == {"close": 1.1}
    assert o["ped"] == {"RSI": 55.0}
    assert o["srednie"] == {"SMA50": 1.0}
    assert "ADX" not in o["trend"]
    assert set(pola.GRUPY) <= set(o)


def test_obraz_z_interwalem_pyta_o_sufiksy_i_zdejmuje_je(atrapa_tv):
    a = atrapa_tv({"RSI|60": 42.0})
    o = analiza.obraz("FX:EURUSD", "60")
    assert o["interwal"] == "60"
    assert o["ped"] == {"RSI": 42.0}
    assert all(p.endswith("|60") for p in a.wywolania[0][1])
    assert len(a.wywolania[0][1]) == len(pola.WSZYSTKIE)


# ── polozenie ───────────────────────────────────────────────────────────
TABELA_POL = {
    "close": 110.0, "BB.upper": 120.0, "BB.lower": 100.0,
    "EMA20": 100.0, "EMA50": 125.0, "EMA200": 110.0,
    "price_52_week_high": 130.0, "price_52_week_low": 90.0, "ATR": 2.2,
}


def test_polozenie_liczy_procenty(atrapa_tv):
    atrapa_tv(TABELA_POL)
    p = analiza.polozenie("X")
    assert p["cena"] == 110.0
    assert p["w_kanale_bollingera_proc"] == 50.0
    assert p["w_zakresie_rocznym_proc"] == 50.0
    assert p["nad_ema20_proc"] == 10.0
    assert p["nad_ema50_proc"] == -12.0
    assert p["nad_ema200_proc"] == 0.0
    assert p["szerokosc_bollingera_proc"] == pytest.approx(18.18)
    assert p["atr_proc_ceny"] == 2.0


def test_polozenie_z_interwalem(atrapa_tv):
    atrapa_tv({f"{k}|60": v for k, v in TABELA_POL.items()})
    p = analiza.polozenie("X", "60")
    assert p["interwal"] == "60"
    assert p["w_kanale_bollingera_proc"] == 50.0


def test_polozenie_bez_ceny_rzuca_bladtv(atrapa_tv):
    atrapa_tv({"close": None})
    with pytest.raises(dane.BladTV, match="brak ceny"):
        analiza.polozenie("X")


def test_polozenie_brakujace_odniesienia_daja_none(atrapa_tv):
    atrapa_tv({"close": 10.0})
    p = analiza.polozenie("X")
    assert p["w_kanale_bollingera_proc"] is None
    assert p["nad_ema50_proc"] is None
    assert p["atr_proc_ceny"] is None
    assert p["szerokosc_bollingera_proc"] is None


def test_polozenie_zerowy_zakres_nie_dzieli_przez_zero(atrapa_tv):
    atrapa_tv({"close": 5.0, "BB.upper": 5.0, "BB.lower": 5.0, "EMA20": 0})
    p = analiza.polozenie("X")
    assert p["w_kanale_bollingera_proc"] is None
    assert p["nad_ema20_proc"] is None


# ── uklad_srednich ──────────────────────────────────────────────────────
def test_uklad_srednich_w_pelni_uporzadkowany(atrapa_tv):
    atrapa_tv({"EMA5": 6, "EMA10": 5, "EMA20": 4, "EMA50": 3, "EMA100": 2,
               "EMA200": 1, "close": 7})
    u = analiza.uklad_srednich("X")
    assert u["par_razem"] == 5
    assert u["par_w_kolejnosci_rosnacej"] == 5
    assert u["par_w_kolejnosci_malejacej"] == 0
    assert u["uporzadkowane_w_pelni"] is True
    assert u["cena"] == 7


def test_uklad_srednich_odwrotny(atrapa_tv):
    atrapa_tv({"EMA5": 1, "EMA10": 2, "EMA20": 3, "EMA50": 4, "EMA100": 5, "EMA200": 6})
    u = analiza.uklad_srednich("X")
    assert (u["par_w_kolejnosci_rosnacej"], u["par_w_kolejnosci_malejacej"]) == (0, 5)
    assert u["uporzadkowane_w_pelni"] is True


def test_uklad_srednich_poszarpany(atrapa_tv):
    atrapa_tv({"EMA5": 1, "EMA10": 3, "EMA20": 2, "EMA50": 4, "EMA100": 3, "EMA200": 5})
    u = analiza.uklad_srednich("X")
    assert u["uporzadkowane_w_pelni"] is False
    assert u["par_w_kolejnosci_rosnacej"] + u["par_w_kolejnosci_malejacej"] == 5


def test_uklad_srednich_pomija_puste_i_liczy_pary_z_reszty(atrapa_tv):
    atrapa_tv({"EMA5": 3, "EMA10": None, "EMA20": 2, "EMA50": 1})
    u = analiza.uklad_srednich("X")
    assert list(u["srednie"]) == ["EMA5", "EMA20", "EMA50"]
    assert u["par_razem"] == 2 and u["uporzadkowane_w_pelni"] is True


def test_uklad_srednich_za_malo_srednich(atrapa_tv):
    atrapa_tv({"EMA5": 3})
    with pytest.raises(dane.BladTV, match="za mało średnich"):
        analiza.uklad_srednich("X")


def test_uklad_srednich_rowne_wartosci_nie_sa_porzadkiem(atrapa_tv):
    atrapa_tv({"EMA5": 1, "EMA10": 1, "EMA20": 1})
    u = analiza.uklad_srednich("X")
    assert u["uporzadkowane_w_pelni"] is False


# ── zgodnosc_pelna ──────────────────────────────────────────────────────
def test_zgodnosc_pelna_tabela_i_braki(atrapa_tv):
    atrapa_tv({"RSI|1": 50.0, "RSI|5": None, "ADX|1": 20.0})
    z = analiza.zgodnosc_pelna("X", ["RSI", "ADX"], ["1", "5"])
    assert z["wartosci"] == {"RSI": {"1": 50.0, "5": None},
                             "ADX": {"1": 20.0, "5": None}}
    assert z["brakujace"] == ["RSI|5", "ADX|5"]


def test_zgodnosc_pelna_domyslne_zestawy(atrapa_tv):
    a = atrapa_tv({})
    z = analiza.zgodnosc_pelna("X")
    assert z["interwaly"] == pola.INTERWALY_PEWNE[:4]
    assert list(z["wartosci"]) == ["RSI", "ADX", "MACD.hist", "Recommend.All"]
    assert len(a.wywolania[0][1]) == 16
    assert len(z["brakujace"]) == 16


def test_zgodnosc_pelna_pole_pominiete_przez_tv_jest_brakujace(monkeypatch):
    monkeypatch.setattr(dane, "odczyt", lambda s, p=None: {"RSI|1": 40.0})
    z = analiza.zgodnosc_pelna("X", ["RSI"], ["1", "5"])
    assert z["brakujace"] == ["RSI|5"]


# ── porownaj / skany ────────────────────────────────────────────────────
def test_porownaj_sortuje_po_sile_ruchu_i_toleruje_none(monkeypatch):
    monkeypatch.setattr(dane, "wiele", lambda s, p=None: [
        {"symbol": "A", "change": 0.1}, {"symbol": "B", "change": -2.0},
        {"symbol": "C", "change": None}, {"symbol": "D", "change": 1.5}])
    assert [x["symbol"] for x in analiza.porownaj(["A", "B", "C", "D"])] == \
        ["B", "D", "A", "C"]


@pytest.mark.parametrize("funkcja, argumenty, pole, operacja, prog", [
    (analiza.skan_wyprzedane, {}, "RSI", "less", 30),
    (analiza.skan_wykupione, {}, "RSI", "greater", 70),
    (analiza.skan_silny_trend, {}, "ADX", "greater", 30),
    (analiza.skan_wolumen, {}, "relative_volume_10d_calc", "greater", 2.0),
    (analiza.skan_wyprzedane, {"prog": 25}, "RSI", "less", 25),
    (analiza.skan_wykupione, {"prog": 80}, "RSI", "greater", 80),
    (analiza.skan_silny_trend, {"prog_adx": 40}, "ADX", "greater", 40),
    (analiza.skan_wolumen, {"krotnosc": 3.5}, "relative_volume_10d_calc", "greater", 3.5),
])
def test_skany_buduja_filtr(monkeypatch, funkcja, argumenty, pole, operacja, prog):
    zap = {}
    monkeypatch.setattr(dane, "przeglad",
                        lambda r, w, p, i: zap.update(r=r, w=w, p=p, i=i) or ["ok"])
    assert funkcja("crypto", ile=5, **argumenty) == ["ok"]
    assert zap["r"] == "crypto" and zap["i"] == 5
    assert zap["w"] == [{"left": pole, "operation": operacja, "right": prog}]


def test_skan_wlasny_domyslne_pola(monkeypatch):
    zap = {}
    monkeypatch.setattr(dane, "przeglad",
                        lambda r, w, p, i: zap.update(w=w, p=p, i=i) or [])
    w = [{"left": "RSI", "operation": "less", "right": 30}]
    analiza.skan_wlasny("poland", w)
    assert zap["w"] == w and zap["i"] == 30
    assert zap["p"] == ["close", "change", "RSI", "ADX", "volume"]


# ── świece z wykresu ────────────────────────────────────────────────────
@pytest.fixture
def atrapa_wykresu(monkeypatch):
    """Podstawia moduł `wykres` — prawdziwy wymaga przeglądarki z CDP."""
    m = types.ModuleType("wykres")
    m.proszone = []
    m.swiece_dane = []
    m.interwal = "15"
    m.ustawione = []
    m.zepsute = set()

    def swiece(ile):
        m.proszone.append(ile)
        return {"swiece": m.swiece_dane}

    def ustaw_interwal(p):
        if p in m.zepsute:
            raise RuntimeError("nie ma takiego przedziału")
        m.ustawione.append(p)

    m.swiece = swiece
    m.stan = lambda: {"interwal": m.interwal}
    m.ustaw_interwal = ustaw_interwal
    m.zdrowie = lambda: {"gotowy": False, "powod": "brak przeglądarki"}
    monkeypatch.setitem(sys.modules, "wykres", m)
    return m


@pytest.mark.parametrize("ile, oczekiwane", [(0, 5000), (-3, 5000), (120, 120)])
def test_swiece_z_wykresu_zero_znaczy_cala_historia(atrapa_wykresu, ile, oczekiwane):
    atrapa_wykresu.swiece_dane = [swieca(1, 2, 0, 1)]
    analiza._swiece_z_wykresu(ile)
    assert atrapa_wykresu.proszone == [oczekiwane]


def test_statystyka_swiec_liczy_miary(atrapa_wykresu):
    atrapa_wykresu.swiece_dane = [
        swieca(10, 12, 9, 11, czas=100),    # wzrostowa, zasięg 3
        swieca(11, 13, 10, 10, czas=200),   # spadkowa, zasięg 3, luka 0
        swieca(12, 14, 11, 14, czas=300),   # wzrostowa, zasięg 3, luka 2
        swieca(14, 15, 13, 13, czas=400),   # spadkowa, zasięg 2, luka 0
    ]
    s = analiza.statystyka_swiec()
    assert s["swiec"] == 4
    assert (s["od"], s["do"]) == (100, 400)
    assert s["najwyzsze_zamkniecie"] == 14 and s["najnizsze_zamkniecie"] == 10
    assert s["ostatnie_zamkniecie"] == 13
    assert s["w_zakresie_proc"] == 75.0
    assert s["sredni_zasieg"] == 2.75
    assert s["najwiekszy_zasieg"] == 3
    assert s["swiec_wzrostowych"] == 2 and s["udzial_wzrostowych_proc"] == 50.0
    assert s["najwieksza_luka"] == 2
    assert s["zmiana_od_poczatku_proc"] == 18.182


def test_statystyka_swiec_plaski_rynek_nie_dzieli_przez_zero(atrapa_wykresu):
    atrapa_wykresu.swiece_dane = [swieca(5, 5, 5, 5), swieca(5, 5, 5, 5)]
    s = analiza.statystyka_swiec()
    assert s["w_zakresie_proc"] is None
    assert s["najwieksza_luka"] == 0
    assert s["zmiana_od_poczatku_proc"] == 0


def test_statystyka_swiec_za_malo_swiec(atrapa_wykresu):
    atrapa_wykresu.swiece_dane = [swieca(1, 2, 0, 1)]
    with pytest.raises(dane.BladTV, match="za mało świec"):
        analiza.statystyka_swiec()


def test_zmiennosc_swiec_dwa_okna(atrapa_wykresu):
    wczesniejsze = [swieca(10, 11, 9, 10) for _ in range(3)]   # zasięg 2
    swiezsze = [swieca(10, 12, 8, 10) for _ in range(3)]       # zasięg 4
    atrapa_wykresu.swiece_dane = wczesniejsze + swiezsze
    z = analiza.zmiennosc_swiec(okno=3)
    assert z["wczesniejsze"]["sredni_zasieg"] == 2
    assert z["swiezsze"]["sredni_zasieg"] == 4
    assert z["swiezsze"]["sredni_zasieg_proc_ceny"] == 40.0
    assert z["stosunek_zasiegow"] == 2.0


def test_zmiennosc_swiec_za_malo_swiec(atrapa_wykresu):
    atrapa_wykresu.swiece_dane = [swieca(1, 2, 0, 1)] * 5
    with pytest.raises(dane.BladTV, match="co najmniej 40"):
        analiza.zmiennosc_swiec(okno=20)


def test_zmiennosc_swiec_zerowy_zasieg_wczesniej(atrapa_wykresu):
    atrapa_wykresu.swiece_dane = ([swieca(5, 5, 5, 5)] * 2) + ([swieca(5, 6, 4, 5)] * 2)
    assert analiza.zmiennosc_swiec(okno=2)["stosunek_zasiegow"] is None


def test_swiece_wiele_przedzialow_wraca_na_wyjsciowy_i_zbiera_bledy(
        atrapa_wykresu, monkeypatch):
    monkeypatch.setattr(analiza.time, "sleep", lambda s: None)
    atrapa_wykresu.swiece_dane = [swieca(1, 2, 0, 1), swieca(1, 3, 0, 2)]
    atrapa_wykresu.zepsute = {"60"}
    w = analiza.swiece_wiele_przedzialow(["15", "60", "240"], ile=10)
    assert w["przedzial_wyjsciowy"] == "15"
    assert w["wyniki"]["15"]["swiec"] == 2
    assert "nie ma takiego" in w["wyniki"]["60"]["blad"]
    assert w["wyniki"]["240"]["swiec"] == 2
    assert atrapa_wykresu.ustawione == ["15", "240", "15"]


# ── obraz_pelny ─────────────────────────────────────────────────────────
def test_obraz_pelny_bez_przegladarki_mowi_o_tym(atrapa_tv, atrapa_wykresu):
    atrapa_tv({"close": 1.0, "EMA5": 2, "EMA10": 1})
    o = analiza.obraz_pelny("FX:EURUSD")
    assert set(o) >= {"symbol", "pola", "polozenie", "srednie", "zgodnosc", "wykres"}
    assert o["wykres"] == {"niedostepny": "brak przeglądarki"}
    assert "wskazniki_z_wykresu" not in o


def test_obraz_pelny_z_przegladarka_dolacza_wykres(atrapa_tv, atrapa_wykresu):
    atrapa_tv({"close": 1.0, "EMA5": 2, "EMA10": 1})
    atrapa_wykresu.zdrowie = lambda: {"gotowy": True}
    atrapa_wykresu.wartosci = lambda: {"RSI": 50}
    o = analiza.obraz_pelny("FX:EURUSD")
    assert o["wykres"] == {"interwal": "15"}
    assert o["wskazniki_z_wykresu"] == {"RSI": 50}


def test_obraz_pelny_blad_wykresu_nie_psuje_czesci_publicznej(atrapa_tv, atrapa_wykresu):
    atrapa_tv({"close": 1.0, "EMA5": 2, "EMA10": 1})

    def zdrowie():
        raise ConnectionError("CDP nie odpowiada")

    atrapa_wykresu.zdrowie = zdrowie
    o = analiza.obraz_pelny("FX:EURUSD")
    assert "CDP nie odpowiada" in o["wykres"]["niedostepny"]
    assert o["polozenie"]["cena"] == 1.0
