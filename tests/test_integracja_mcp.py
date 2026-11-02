"""Testy integracyjne: każde narzędzie wywołane przez serwer MCP.

Klient MCP łączy się z serwerem w pamięci, tak jak zrobiłby to Claude czy inny
klient, a wszystko, co serwer wysyła na zewnątrz, trafia do zaślepek
(`tests/zaslepki.py`). Dzięki temu sprawdzamy całą drogę: spis narzędzi,
schemat argumentów, rozdział wywołań, moduły i ich obsługę błędów.

Uruchomienie: python3 -m pytest tests
"""
from __future__ import annotations

import threading
import time

import anyio
import pytest

from conftest import polacz

pytestmark = pytest.mark.anyio

PINE_OK = '//@version=5\nindicator("t")\nplot(ta.sma(close,20))'
PINE_ZLY = '//@version=5\nindicator("t")\nplot(ta.sma(clse,20))'


def _jest_lista(x):
    return isinstance(x, list)


def _bez_bledu(x):
    return not (isinstance(x, dict) and "blad" in x)


# Poprawne argumenty i sprawdzenie wyniku dla KAŻDEGO narzędzia ze spisu.
# Test `test_kazde_narzedzie_ma_przypadek` pilnuje, żeby nowe narzędzie
# nie weszło do serwera bez wpisu tutaj.
PRZYPADKI = {
    # dane publiczne
    "vgm_odczyt": ({"symbol": "FX:EURUSD", "pola": ["close", "RSI"]},
                   lambda w: w == {"close": 1.1, "RSI": 52.0}),
    "vgm_obraz": ({"symbol": "FX:EURUSD"},
                  lambda w: w["symbol"] == "FX:EURUSD" and w["cena"]["close"] == 1.1),
    "vgm_obraz_pelny": ({"symbol": "FX:EURUSD"},
                        lambda w: w["polozenie"]["cena"] == 1.1 and w["wykres"]["symbol"] == "FX:EURUSD"),
    "vgm_rynki": ({}, lambda w: "forex" in w),
    "vgm_pola": ({}, lambda w: "interwaly_zmierzone" in w and "cena" in w),
    "vgm_polozenie": ({"symbol": "FX:EURUSD", "interwal": "60"},
                      lambda w: w["w_kanale_bollingera_proc"] == 50.0 and w["interwal"] == "60"),
    "vgm_srednie": ({"symbol": "FX:EURUSD"},
                    lambda w: w["par_razem"] == 5 and w["uporzadkowane_w_pelni"]),
    "vgm_mtf": ({"symbol": "FX:EURUSD", "wskazniki": ["RSI"], "interwaly": ["5", "60"]},
                lambda w: w == {"RSI": {"5": 60.0, "60": 40.0}}),
    "vgm_zgodnosc": ({"symbol": "FX:EURUSD"},
                     lambda w: w["za_kupnem"] == ["15", "5"] and w["za_sprzedaza"] == ["60"]
                     and w["bez_danych"] == ["240"] and not w["wszystkie_zgodne"]),
    "vgm_zgodnosc_pelna": ({"symbol": "FX:EURUSD", "wskazniki": ["RSI"], "interwaly": ["5", "240"]},
                           lambda w: w["brakujace"] == ["RSI|240"]),
    "vgm_wiele": ({"symbole": ["FX:EURUSD", "FX:GBPUSD"]},
                  lambda w: [x["symbol"] for x in w] == ["FX:EURUSD", "FX:GBPUSD"]),
    "vgm_porownaj": ({"symbole": ["FX:EURUSD", "FX:GBPUSD"]}, lambda w: len(w) == 2),
    "vgm_skan_wyprzedane": ({"ile": 3}, lambda w: len(w) == 3 and "RSI" in w[0]),
    "vgm_skan_wykupione": ({"rynek": "crypto", "ile": 2}, lambda w: len(w) == 2),
    "vgm_skan_trend": ({"ile": 2}, lambda w: "ADX+DI" in w[0]),
    "vgm_skan_wolumen": ({"ile": 2}, lambda w: "relative_volume_10d_calc" in w[0]),
    "vgm_skan": ({"rynek": "america", "warunki": [{"left": "RSI", "operation": "less", "right": 30}],
                  "ile": 4}, lambda w: len(w) == 4),
    # wykres
    "vgm_wykres_karta": ({}, lambda w: w["bylo_gotowe"] is True),
    "vgm_wykres_zdrowie": ({}, lambda w: w["gotowy"] and w["symbol"] == "FX:EURUSD"),
    "vgm_wykres_stan": ({}, lambda w: w["symbol"] == "FX:EURUSD" and w["interwal"] == "60"),
    "vgm_wykres_wartosci": ({}, _jest_lista),
    "vgm_wykres_przelacz": ({"symbol": "FX:GBPUSD", "interwal": "15"},
                            lambda w: w["potwierdzone"] and w["sposob"] == "zmiana na miejscu"),
    "vgm_przeglad_instrumentow": ({"instrumenty": [["FX:GBPUSD", "60"]], "po_ilu": 5},
                                  lambda w: w["instrumentow"] == 1
                                  and "sprawdzono" in w["wyniki"]["FX:GBPUSD 60"]),
    "vgm_wykres_symbol": ({"symbol": "NASDAQ:NVDA"}, lambda w: w == {"ok": True, "symbol": "NASDAQ:NVDA"}),
    "vgm_wykres_interwal": ({"interwal": "240"}, lambda w: w["interwal"] == "240"),
    "vgm_wykres_typ": ({"typ": 3}, lambda w: w["typ"] == 3),
    "vgm_wskaznik_dodaj": ({"nazwa": "Relative Strength Index"}, lambda w: w["liczy"] is True),
    "vgm_wskaznik_usun": ({"id": "st1"}, lambda w: w["usuniete"] == "st1"),
    "vgm_wykres_swiece": ({"ile": 5}, lambda w: w["zwrocono"] == 5 and "zamkniecie" in w["swiece"][0]),
    "vgm_swiece_statystyka": ({"ile": 100}, lambda w: w["swiec"] == 100),
    "vgm_zmierz_prog": ({"prog": 40}, lambda w: "wniosek" in w),
    "vgm_walk_forward": ({"wskaznik": "RSI"}, lambda w: "wniosek" in w and w["swiec"] == 600),
    "vgm_zmierz": ({"wskaznik": "Bollinger", "prog": 20}, lambda w: "wniosek" in w),
    "vgm_sygnal_czy_trend": ({}, lambda w: "ocena" in w),
    "vgm_koszt_a_przewaga": ({"koszty": [0.02, 0.1]}, _bez_bledu),
    "vgm_jak_dlugo_trzymac": ({"dlugosci": [3, 10]}, lambda w: len(w["dlugosci"]) == 2),
    "vgm_odniesienie_trzymanie": ({"po_ilu": 5}, _bez_bledu),
    "vgm_przeglad_wskaznikow": ({}, lambda w: w["sprawdzono"] == 7),
    "vgm_porownaj_progi": ({"progi": [30, 40]}, _bez_bledu),
    "vgm_swiece_przedzialy": ({"przedzialy": ["15", "60"], "ile": 50},
                              lambda w: set(w["wyniki"]) == {"15", "60"}
                              and w["przedzial_wyjsciowy"] == "60"),
    "vgm_swiece_zmiennosc": ({"ile": 100, "okno": 20}, lambda w: w["okno"] == 20),
    "vgm_wykres_zrzut": ({}, lambda w: w["bajtow"] > 0 and w["plik"].endswith(".png")),
    # sesja
    "vgm_sesja": ({}, lambda w: w["zalogowany"] is True and w["plan"] == "pro_premium"),
    "vgm_alerty": ({}, lambda w: w["ile"] == 2 and w["alerty"][0]["symbol"] == "ICMARKETS:USDCHF"),
    "vgm_lista_obserwowanych": ({}, lambda w: w["ile"] == 2),
    "vgm_skrypty_pine": ({}, lambda w: w["skrypty"][0]["id"] == "USER;abc"),
    "vgm_zrodlo_pine": ({"id": "USER;abc"}, lambda w: w["kod"].startswith("//@version=5")),
    "vgm_zapisz_pine": ({"kod": PINE_OK, "nazwa": "Test"}, lambda w: w["zapisany"] is True),
    "vgm_usun_pine": ({"id": "USER;old"}, lambda w: w["usuniety"] is True),
    "vgm_strategie_wbudowane": ({}, lambda w: w["strategii"] == 2 and w["wbudowanych"] == 3),
    "vgm_tester_raport": ({}, lambda w: w["otwarty"] and w["ma_transakcje"] is False),
    # układ
    "vgm_uklad_stan": ({}, lambda w: w["uklad"] == "s" and w["wykresow"] == 1),
    "vgm_uklad_ustaw": ({"kod": "2h"}, lambda w: w["zgodny"] and w["wykresow"] == 2),
    "vgm_uklad_wybierz": ({"indeks": 0}, lambda w: w["zgodny"]),
    "vgm_uklad_symbol": ({"indeks": 0, "symbol": "FX:GBPUSD"}, lambda w: w["zgodny"]),
    # odtwarzanie
    "vgm_replay_stan": ({}, lambda w: w["dostepne"] and not w["trwa"]),
    "vgm_replay_start": ({"data": "2026-09-11"}, lambda w: w["trwa"] and w["wybrana_data"] == "2026-09-11 00:00"),
    "vgm_replay_krok": ({"ile": 3}, None),        # wymaga trwającego odtwarzania — osobny test
    "vgm_replay_autoplay": ({"wlacz": True}, None),
    "vgm_replay_stop": ({}, lambda w: w["trwa"] is False),
    # Pine
    "vgm_pine_sprawdz": ({"kod": PINE_OK}, lambda w: w == {"poprawny": True, "bledy": []}),
    "vgm_pine_sprawdz_plik": (None, None),         # potrzebuje pliku — osobny test
    "vgm_pine_szkielet": ({"nazwa": "X"}, lambda w: 'indicator("X"' in w["kod"]),
}

CHART = {n for n in PRZYPADKI if n.startswith(("vgm_wykres", "vgm_wskaznik", "vgm_swiece",
                                               "vgm_zmierz", "vgm_porownaj_progi",
                                               "vgm_przeglad_", "vgm_sygnal", "vgm_odniesienie",
                                               "vgm_jak_dlugo", "vgm_koszt", "vgm_walk",
                                               "vgm_replay", "vgm_uklad"))}
SESJA = {"vgm_sesja", "vgm_alerty", "vgm_lista_obserwowanych", "vgm_skrypty_pine",
         "vgm_zrodlo_pine", "vgm_zapisz_pine", "vgm_usun_pine", "vgm_strategie_wbudowane",
         "vgm_tester_raport"}
PRZEGLADARKA = (CHART | SESJA) - {"vgm_strategie_wbudowane", "vgm_skrypty_pine",
                                   "vgm_zrodlo_pine", "vgm_alerty"}


# ── spis i rozdział wywołań ─────────────────────────────────────────────
async def test_spis_narzedzi(srodowisko):
    async with polacz() as k:
        nazwy = [n.name for n in await k.narzedzia()]
    assert len(nazwy) == len(set(nazwy)), "powtórzona nazwa narzędzia"
    assert len(nazwy) == 63


async def test_kazde_narzedzie_ma_przypadek(srodowisko):
    async with polacz() as k:
        nazwy = {n.name for n in await k.narzedzia()}
    assert nazwy == set(PRZYPADKI), (
        f"bez przypadku: {sorted(nazwy - set(PRZYPADKI))}; "
        f"przypadek bez narzędzia: {sorted(set(PRZYPADKI) - nazwy)}")


async def test_schematy_wymagane_pola_istnieja(srodowisko):
    async with polacz() as k:
        for n in await k.narzedzia():
            schemat = getattr(n, "input_schema", None) or n.inputSchema
            assert schemat["type"] == "object"
            for pole in schemat.get("required", []):
                assert pole in schemat["properties"], f"{n.name}: wymagane {pole} bez opisu"


@pytest.mark.parametrize("nazwa", sorted(n for n, (a, s) in PRZYPADKI.items() if s))
async def test_narzedzie_dziala(srodowisko, nazwa):
    argumenty, sprawdz = PRZYPADKI[nazwa]
    async with polacz() as k:
        if nazwa == "vgm_replay_stop":
            await k.wywolaj("vgm_replay_start", {})
        wynik, blad = await k.wywolaj(nazwa, argumenty)
    assert not blad, wynik
    assert _bez_bledu(wynik), wynik
    assert sprawdz(wynik), wynik


async def test_odtwarzanie_pelny_cykl(srodowisko):
    async with polacz() as k:
        s, _ = await k.wywolaj("vgm_replay_start", {"data": "2026-09-11 13:30"})
        assert s["trwa"] and s["wybrana_data"] == "2026-09-11 13:30"
        kr, _ = await k.wywolaj("vgm_replay_krok", {"ile": 3})
        assert kr["krokow"] == 3 and kr["ruszyl"] is True
        a, _ = await k.wywolaj("vgm_replay_autoplay", {"wlacz": True, "opoznienie_ms": 300})
        assert a["autoodtwarzanie"] is True and a["opoznienie"] == 300
        st, _ = await k.wywolaj("vgm_replay_stop", {})
        assert st["trwa"] is False and st["autoodtwarzanie"] is False
        assert st["pasek_widoczny"] is False


async def test_odtwarzanie_data_w_sekundach_jako_tekst(srodowisko):
    # Schemat mówi "string", opis: "YYYY-MM-DD, YYYY-MM-DD HH:MM albo sekundy".
    async with polacz() as k:
        s, blad = await k.wywolaj("vgm_replay_start", {"data": "1757548800"})
    assert not blad and _bez_bledu(s), s
    assert s["wybrana_data"] == "2025-09-11 00:00"


async def test_odtwarzanie_krok_bez_startu(srodowisko):
    async with polacz() as k:
        w, _ = await k.wywolaj("vgm_replay_krok", {"ile": 1})
    assert "nie trwa" in w["blad"]


async def test_pine_sprawdz_plik(srodowisko, tmp_path):
    p = tmp_path / "zly.pine"
    p.write_text(PINE_ZLY, encoding="utf-8")
    async with polacz() as k:
        w, _ = await k.wywolaj("vgm_pine_sprawdz_plik", {"sciezka": str(p)})
    assert w["poprawny"] is False and w["bledy"][0]["linia"] == 3
    assert "clse" in w["podglad"] and w["plik"] == str(p)


async def test_pine_literowka_z_podgladem(srodowisko):
    async with polacz() as k:
        w, _ = await k.wywolaj("vgm_pine_sprawdz", {"kod": PINE_ZLY})
    assert w["bledy"] == [{"linia": 3, "kolumna": 13,
                           "komunikat": "Undeclared identifier 'clse'"}]
    assert "^-- Undeclared" in w["podglad"]


async def test_nieznane_narzedzie(srodowisko):
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_nie_ma_takiego", {})
    assert "nieznane narzędzie" in w["blad"]
    assert blad


# ── przypadki błędów: sieć ──────────────────────────────────────────────
@pytest.mark.parametrize("kod", [403, 429])
async def test_scanner_odmawia_bez_ponawiania(srodowisko, kod):
    srodowisko.siec.awaria["scanner.tradingview.com"] = kod
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_odczyt", {"symbol": "FX:EURUSD"})
    assert blad and str(kod) in w["blad"] and w["narzedzie"] == "vgm_odczyt"
    assert len([z for z in srodowisko.siec.zapytania if "scanner" in z[1]]) == 1


async def test_scanner_zla_nazwa_instrumentu(srodowisko):
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_odczyt", {"symbol": "NIE-ISTNIEJE-XYZ"})
    assert blad and "400" in w["blad"]


async def test_scanner_odpowiada_smieciami(srodowisko):
    srodowisko.siec.awaria["scanner.tradingview.com"] = "smieci"
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_polozenie", {"symbol": "FX:EURUSD"})
    assert blad and "JSONDecodeError" in w["blad"]


async def test_scanner_nieznany_rynek(srodowisko):
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_skan_trend", {"rynek": "marsjanski"})
    assert blad and "404" in w["blad"]


async def test_brak_wymaganego_pola(srodowisko):
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_odczyt", {})
    assert blad
    tekst = w["blad"] if isinstance(w, dict) else w
    assert "symbol" in tekst


async def test_zly_typ_argumentu_nie_wywraca_serwera(srodowisko):
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_wykres_swiece", {"ile": "dużo"})
        assert blad
        # serwer nadal odpowiada po błędzie
        w2, blad2 = await k.wywolaj("vgm_rynki", {})
    assert not blad2 and "forex" in w2


async def test_pine_kompilator_odmawia(srodowisko):
    srodowisko.siec.awaria["translate_light"] = 429
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_pine_sprawdz", {"kod": PINE_OK})
    assert blad and "429" in w["blad"]


async def test_pine_pusty_kod(srodowisko):
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_pine_sprawdz", {"kod": "   "})
    assert blad and w["blad"] == "pusty kod"


async def test_pine_blad_bez_pozycji(srodowisko):
    # Kompilator potrafi zwrócić błąd bez linii i kolumny.
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_pine_sprawdz", {"kod": PINE_OK + "\n// BEZ_POZYCJI"})
    assert not blad and w["poprawny"] is False, w
    assert "Script could not be translated" in w["podglad"]


async def test_pine_plik_nie_istnieje(srodowisko, tmp_path):
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_pine_sprawdz_plik", {"sciezka": str(tmp_path / "brak.pine")})
    assert blad and "nie ma takiego pliku" in w["blad"]


async def test_pine_plik_to_katalog_albo_nie_tekst(srodowisko, tmp_path):
    binarny = tmp_path / "obraz.pine"
    binarny.write_bytes(b"\xff\xfe\x00\x81")
    async with polacz() as k:
        w1, b1 = await k.wywolaj("vgm_pine_sprawdz_plik", {"sciezka": str(tmp_path)})
        w2, b2 = await k.wywolaj("vgm_pine_sprawdz_plik", {"sciezka": str(binarny)})
    assert b1 and isinstance(w1, dict) and "blad" in w1, w1
    assert b2 and isinstance(w2, dict) and "blad" in w2, w2


# ── przypadki błędów: przeglądarka ──────────────────────────────────────
def _argumenty_dla(nazwa):
    a = PRZYPADKI[nazwa][0]
    return {} if a is None else a


@pytest.mark.parametrize("nazwa", sorted(PRZEGLADARKA))
async def test_przegladarka_zamknieta(srodowisko, nazwa):
    """Bez przeglądarki każde narzędzie mówi to wprost, zamiast się wywrócić."""
    srodowisko.cdp.tryb = "zamknieta"
    async with polacz() as k:
        w, blad = await k.wywolaj(nazwa, _argumenty_dla(nazwa))
    if nazwa == "vgm_wykres_zdrowie":
        assert not blad and w["gotowy"] is False and "9333" in w["powod"]
        return
    if nazwa == "vgm_przeglad_instrumentow":
        assert blad and "9333" in w["blad"], w
        return
    assert blad, w
    assert isinstance(w, dict) and "blad" in w, w
    assert "9333" in w["blad"] or "przeglądarka" in w["blad"], w


@pytest.mark.parametrize("nazwa", ["vgm_wykres_stan", "vgm_wykres_swiece", "vgm_sesja",
                                   "vgm_replay_stan", "vgm_uklad_stan", "vgm_wykres_zrzut"])
async def test_brak_karty_tradingview(srodowisko, nazwa):
    srodowisko.cdp.tryb = "bez_karty"
    async with polacz() as k:
        w, blad = await k.wywolaj(nazwa, {})
    assert blad and "żadna karta" in w["blad"], w


async def test_wykres_karta_otwiera_nowa(srodowisko):
    srodowisko.cdp.tryb = "bez_karty"
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_wykres_karta", {"symbol": "FX:GBPUSD"})
    assert not blad and w["bylo_gotowe"] is False and w["otwarta"] is True, w
    assert "FX:GBPUSD" in srodowisko.cdp.karty[-1]["url"]


async def test_wybiera_karte_strony_nie_service_worker(srodowisko):
    # Pierwszy cel z tradingview.com na liście to service worker — nie ma wykresu.
    async with polacz() as k:
        await k.wywolaj("vgm_wykres_stan", {})
    import wykres
    assert wykres._karta()["id"] == "K1"


async def test_karta_bez_adresu_gniazda(srodowisko):
    # Chrome nie podaje webSocketDebuggerUrl, gdy do karty jest już podpięte DevTools.
    for kt in srodowisko.cdp.karty:
        kt.pop("webSocketDebuggerUrl")
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_wykres_stan", {})
    assert blad and "DevTools" in w["blad"], w


async def test_strona_bez_api(srodowisko):
    srodowisko.cdp.tryb = "bez_api"
    async with polacz() as k:
        z, _ = await k.wywolaj("vgm_wykres_zdrowie", {})
        w, blad = await k.wywolaj("vgm_wykres_stan", {})
    assert z["gotowy"] is False and z["powod"] == "strona nie udostępnia API wykresu"
    assert blad and w["blad"] == "strona nie udostępnia API wykresu"
    assert w["podpowiedz"] == "sprawdź vgm_wykres_zdrowie"


async def test_wyjatek_javascript_ma_opis(srodowisko):
    srodowisko.cdp.wyjatek_js = "Cannot read properties of undefined (reading 'value')"
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_replay_stan", {})
    assert blad and w["blad"].startswith("TypeError: Cannot read properties"), w


async def test_zerwane_polaczenie(srodowisko):
    srodowisko.cdp.tryb = "zerwane"
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_wykres_stan", {})
    assert blad and "WebSocketConnectionClosedException" in w["blad"], w


async def test_sesja_niezalogowana(srodowisko):
    srodowisko.cdp.zalogowany = False
    async with polacz() as k:
        s, _ = await k.wywolaj("vgm_sesja", {})
        a, blad = await k.wywolaj("vgm_alerty", {})
    assert s == {"zalogowany": False, "sessionid": False, "uzytkownik": None, "plan": None}
    assert blad and "zaloguj się" in a["blad"]


async def test_sesja_wygasla(srodowisko):
    srodowisko.siec.awaria["pricealerts"] = 401
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_alerty", {})
    assert blad and "401" in w["blad"] and "wygasła" in w["blad"]


async def test_sesja_siec_nie_odpowiada(srodowisko):
    srodowisko.siec.awaria["pine-facade.tradingview.com/pine-facade/list"] = "timeout"
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_skrypty_pine", {})
    assert blad and isinstance(w, dict) and "blad" in w, w


async def test_sesja_nie_wypisuje_sekretow(srodowisko):
    async with polacz() as k:
        for nazwa in SESJA:
            r = await k.wywolaj_surowo(nazwa, _argumenty_dla(nazwa))
            assert "SEKRET-SESJI" not in r.content[0].text, nazwa
        w, _ = await k.wywolaj("vgm_sesja", {})
    assert w["uzytkownik"] == "tes***"


async def test_lista_obserwowanych_bez_panelu(srodowisko):
    srodowisko.cdp.panel_prawy = False
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_lista_obserwowanych", {})
    assert blad and w["blad"] == "panel prawy nie jest otwarty"


async def test_zrodlo_pine_nieznane_id(srodowisko):
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_zrodlo_pine", {"id": "USER;nie/ma"})
    assert blad and "404" in w["blad"]


async def test_wskaznik_usun_nieznany(srodowisko):
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_wskaznik_usun", {"id": "st999"})
    assert blad and "nie ma wskaźnika" in w["blad"]


async def test_wskaznik_bez_sesji_nie_liczy(srodowisko):
    srodowisko.cdp.zalogowany = False
    async with polacz() as k:
        await k.wywolaj("vgm_wskaznik_dodaj", {"nazwa": "Relative Strength Index"})
        w, _ = await k.wywolaj("vgm_wskaznik_dodaj", {"nazwa": "Moving Average Exponential"})
    assert w["liczy"] is False and "JEDEN" in w["uwaga"]


async def test_zrzut_do_pliku(srodowisko, tmp_path):
    cel = tmp_path / "w.png"
    async with polacz() as k:
        w, _ = await k.wywolaj("vgm_wykres_zrzut", {"sciezka": str(cel), "zamknij_okna": False})
    assert cel.read_bytes().startswith(b"\x89PNG") and w["plik"] == str(cel)


async def test_zrzut_do_nieistniejacego_katalogu(srodowisko, tmp_path):
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_wykres_zrzut", {"sciezka": str(tmp_path / "nie" / "ma.png")})
    assert blad and isinstance(w, dict) and "blad" in w, w


async def test_pomiar_za_malo_swiec(srodowisko):
    srodowisko.cdp.ile_swiec = 30
    async with polacz() as k:
        for nazwa in ("vgm_zmierz_prog", "vgm_zmierz", "vgm_walk_forward", "vgm_koszt_a_przewaga"):
            w, blad = await k.wywolaj(nazwa, _argumenty_dla(nazwa))
            assert blad and "za mało świec" in w["blad"], (nazwa, w)


async def test_pomiar_nieznany_wskaznik(srodowisko):
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_zmierz", {"wskaznik": "MACD"})
    assert blad and "nieznany wskaźnik" in w["blad"], w


async def test_uklad_nieznany_kod_i_indeks(srodowisko):
    async with polacz() as k:
        w1, b1 = await k.wywolaj("vgm_uklad_ustaw", {"kod": "5x"})
        w2, b2 = await k.wywolaj("vgm_uklad_wybierz", {"indeks": 3})
    assert b1 and "nieznany układ" in w1["blad"]
    assert b2 and "poza zakresem" in w2["blad"]


async def test_uklad_symbol_na_drugim_wykresie(srodowisko):
    async with polacz() as k:
        await k.wywolaj("vgm_uklad_ustaw", {"kod": "2h"})
        w, _ = await k.wywolaj("vgm_uklad_symbol", {"indeks": 1, "symbol": "COINBASE:BTCUSD",
                                                     "interwal": "60"})
    assert w["zgodny"] and w["indeks"] == 1
    assert [x["symbol"] for x in w["uklad"]["wykresy"]] == ["FX:EURUSD", "COINBASE:BTCUSD"]


async def test_przelacz_przy_spoznionych_swiecach_przeladowuje(srodowisko):
    srodowisko.cdp.swiece_spoznione = 1000          # świece nie nadążają za symbolem
    async with polacz() as k:
        w, _ = await k.wywolaj("vgm_wykres_przelacz", {"symbol": "COINBASE:BTCUSD"})
    assert w["sposob"] == "przeładowanie strony" and w["potwierdzone"] is True, w
    assert "symbol=COINBASE%3ABTCUSD" in srodowisko.cdp.nawigacje[-1]


@pytest.mark.parametrize("przedzial,luka", [("D", 2 * 86400), ("60", 2 * 86400)])
async def test_przelacz_po_weekendzie(srodowisko, przedzial, luka):
    # Poniedziałek: między ostatnią świecą a przedostatnią jest weekend.
    # Odstęp z jednej pary świec wygląda wtedy jak zły przedział.
    srodowisko.cdp.luka_przed_ostatnia = luka
    async with polacz() as k:
        w, _ = await k.wywolaj("vgm_wykres_przelacz", {"symbol": "FX:EURUSD", "interwal": przedzial})
    assert w["potwierdzone"] is True and w["sposob"] == "zmiana na miejscu", w
    assert srodowisko.cdp.nawigacje == []


async def test_przeglad_instrumentow_przywraca_stan(srodowisko):
    async with polacz() as k:
        w, _ = await k.wywolaj("vgm_przeglad_instrumentow",
                               {"instrumenty": [["FX:GBPUSD", "15"], ["COINBASE:BTCUSD", "D"]]})
        s, _ = await k.wywolaj("vgm_wykres_stan", {})
    assert w["stan_przywrocony"] == "FX:EURUSD 60"
    assert (s["symbol"], s["interwal"]) == ("FX:EURUSD", "60")


# ── limity czasu ────────────────────────────────────────────────────────
async def test_cdp_milczy_limit_czasu(srodowisko):
    srodowisko.cdp.tryb = "cisza"
    start = srodowisko.zegar.time()
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_wykres_stan", {})
    trwalo = srodowisko.zegar.time() - start
    assert blad and "2 próbach" in w["blad"], w
    # dwie próby: 25 s i 50 s, plus dwie przerwy po 2 s
    assert 75 <= trwalo <= 80, trwalo


async def test_cdp_milczy_raz_ponowienie_wystarcza(srodowisko):
    srodowisko.cdp.cisza_razy = 1
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_wykres_stan", {})
    assert not blad and w["symbol"] == "FX:EURUSD", w


async def test_cdp_zalew_zdarzen_limit_czasu(srodowisko):
    # Gniazdo żyje, ale przysyła tylko zdarzenia bez naszego id.
    srodowisko.cdp.tryb = "zalew"
    start = srodowisko.zegar.time()
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_wykres_stan", {})
    trwalo = srodowisko.zegar.time() - start
    assert blad and "nie odpowiedzia" in w["blad"], w
    assert trwalo <= 80, trwalo


@pytest.mark.parametrize("nazwa", ["vgm_wykres_zrzut", "vgm_sesja", "vgm_wykres_przelacz"])
async def test_cdp_milczy_inne_drogi(srodowisko, nazwa):
    """Zrzut, ciasteczka i przeładowanie mają własne gniazda — też z limitem."""
    srodowisko.cdp.tryb = "cisza"
    start = srodowisko.zegar.time()
    async with polacz() as k:
        w, blad = await k.wywolaj(nazwa, {"symbol": "FX:GBPUSD"} if "przelacz" in nazwa else {})
    assert blad and isinstance(w, dict) and "blad" in w, w
    assert srodowisko.zegar.time() - start <= 200


async def test_scanner_timeout(srodowisko):
    srodowisko.siec.awaria["scanner.tradingview.com"] = "timeout"
    start = srodowisko.zegar.time()
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_odczyt", {"symbol": "FX:EURUSD"})
    assert blad and "timeout" in w["blad"].lower() or "timed out" in w["blad"], w
    # dwie próby po 25 s i przerwa 2 s
    assert srodowisko.zegar.time() - start <= 60
    assert len(srodowisko.siec.zapytania) == 2


async def test_pine_timeout(srodowisko):
    srodowisko.siec.awaria["translate_light"] = "timeout"
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_pine_sprawdz", {"kod": PINE_OK})
    assert blad and "timed out" in w["blad"]


async def test_replay_start_nie_rusza_limit(srodowisko):
    # API przyjmuje wywołanie, ale odtwarzanie nie startuje.
    import zaslepki
    stary = zaslepki.CDP._replay

    def bez_startu(self, kod):
        if "selectDate(" in kod or "selectFirstAvailableDate" in kod:
            return 1
        return stary(self, kod)

    srodowisko.cdp._replay = bez_startu.__get__(srodowisko.cdp)
    start = srodowisko.zegar.time()
    async with polacz() as k:
        w, blad = await k.wywolaj("vgm_replay_start", {})
    assert blad and "nie wystartowało w 20 s" in w["blad"]
    assert srodowisko.zegar.time() - start <= 30


async def test_dlugie_narzedzie_nie_blokuje_serwera(srodowisko):
    """Wywołanie czekające na przeglądarkę nie może zamrozić całego serwera.

    Gdy narzędzie liczy w pętli zdarzeń, klient nie dostaje odpowiedzi na żadne
    inne zapytanie (spis narzędzi, ping, anulowanie) — wygląda to jak zawieszony
    serwer. Sprawdzamy spisem narzędzi, bo ping zniknął z nowszych wersji
    protokołu, a spis jest w każdej.
    """
    zwolnij = threading.Event()
    srodowisko.cdp.blokada = zwolnij
    threading.Timer(3.0, zwolnij.set).start()
    async with polacz() as k:
        async with anyio.create_task_group() as tg:
            # zegar startuje przed wywołaniem: zablokowana pętla zatrzymałaby
            # też samo anyio.sleep, więc pomiar od końca drzemki niczego by nie złapał
            t0 = time.perf_counter()
            tg.start_soon(k.wywolaj, "vgm_wykres_stan", {})
            await anyio.sleep(0.2)
            with anyio.fail_after(10):
                await k.narzedzia()
            czas = time.perf_counter() - t0
            zwolnij.set()
    assert srodowisko.cdp.metody == ["Runtime.evaluate"], "narzędzie nie dotarło do przeglądarki"
    assert czas < 1.5, f"spis narzędzi czekał {czas:.1f} s na koniec innego narzędzia"
