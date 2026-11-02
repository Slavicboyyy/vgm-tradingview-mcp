"""Warstwa wykresu (CDP): wybór karty, ścieżka zrzutu, port, wstrzykiwanie do JS."""
import json

import pytest

import replay
import uklad
import walidacja as wal
import wykres


# ── która karta jest „TradingView" ──────────────────────────────────────
@pytest.mark.parametrize("url,oczekiwane", [
    ("https://www.tradingview.com/chart/abc/", True),
    ("https://tradingview.com/", True),
    ("https://pl.tradingview.com/chart/", True),
    ("https://evil.example/?x=tradingview.com", False),
    ("https://tradingview.com.evil.example/chart", False),
    ("https://eviltradingview.com/", False),
    ("http://www.tradingview.com/chart/", False),
    ("file:///tmp/tradingview.com.html", False),
    ("", False),
])
def test_host_karty(url, oczekiwane):
    assert wykres._to_tradingview(url) is oczekiwane


class _Odp:
    def __init__(self, tresc):
        self.tresc = tresc

    def read(self):
        return self.tresc


def test_karta_nie_wybiera_obcej_strony_z_nazwa_w_adresie(monkeypatch):
    karty = [
        {"type": "page", "url": "https://evil.example/?tradingview.com", "webSocketDebuggerUrl": "ws://zla"},
        {"type": "service_worker", "url": "https://www.tradingview.com/sw.js", "webSocketDebuggerUrl": "ws://sw"},
        {"type": "page", "url": "https://www.tradingview.com/chart/", "webSocketDebuggerUrl": "ws://dobra"},
    ]
    monkeypatch.setattr(wykres, "websocket", object())
    monkeypatch.setattr(wykres.urllib.request, "urlopen",
                        lambda *a, **k: _Odp(json.dumps(karty).encode()))
    assert wykres._karta()["webSocketDebuggerUrl"] == "ws://dobra"


def test_karta_brak_prawdziwej_karty_to_blad(monkeypatch):
    karty = [{"type": "page", "url": "https://evil.example/?tradingview.com"}]
    monkeypatch.setattr(wykres, "websocket", object())
    monkeypatch.setattr(wykres.urllib.request, "urlopen",
                        lambda *a, **k: _Odp(json.dumps(karty).encode()))
    with pytest.raises(wykres.BladWykresu):
        wykres._karta()


def test_karta_przegladarka_nie_odpowiada_to_blad_z_limitem_czasu(monkeypatch):
    zapisane = {}

    def urlopen(url, timeout=None):
        zapisane["timeout"] = timeout
        raise OSError("connection refused")

    monkeypatch.setattr(wykres, "websocket", object())
    monkeypatch.setattr(wykres.urllib.request, "urlopen", urlopen)
    with pytest.raises(wykres.BladWykresu):
        wykres._karta()
    assert zapisane["timeout"] == 10


# ── port ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("v", ["abc", "0", "70000", "-1", "9222; rm -rf /", "1.5"])
def test_zly_port_z_env_odrzucony(v, monkeypatch):
    monkeypatch.setenv("VGM_CDP_PORT", v)
    with pytest.raises(RuntimeError):
        wykres._wykryj_port()


def test_dobry_port_z_env(monkeypatch):
    monkeypatch.setenv("VGM_CDP_PORT", "9333")
    assert wykres._wykryj_port() == 9333


# ── zrzut: zapis tylko w katalogu zrzutów ───────────────────────────────
@pytest.mark.parametrize("sciezka", ["../../root/.bashrc", "/etc/cron.d/x.png", "~/.ssh/authorized_keys",
                                     "x.sh", "../x.png"])
def test_zrzut_zla_sciezka_odrzucona_przed_dotknieciem_przegladarki(sciezka, monkeypatch, tmp_path):
    monkeypatch.setenv("VGM_KATALOG_ZRZUTOW", str(tmp_path))
    monkeypatch.setattr(wykres, "_wykonaj", lambda *a, **k: pytest.fail("ruszył przeglądarkę"))
    monkeypatch.setattr(wykres, "_karta", lambda: pytest.fail("ruszył przeglądarkę"))
    with pytest.raises(wykres.BladWykresu):
        wykres.zrzut(sciezka, zamknij_okna=False)


# ── wstrzykiwanie do JS ─────────────────────────────────────────────────
def _przechwyc(monkeypatch):
    kod = []
    monkeypatch.setattr(wykres, "_wykonaj", lambda k, **kw: kod.append(k) or {"ok": True})
    return kod


@pytest.mark.parametrize("zly", ['FX:EURUSD"); alert(1);//', "FX:EURUSD'+x+'", "a b", "x" * 200])
def test_symbol_nie_trafia_do_js(zly, monkeypatch):
    kod = _przechwyc(monkeypatch)
    with pytest.raises(wal.BladWejscia):
        wykres.ustaw_symbol(zly)
    assert kod == []


def test_interwal_typ_swiece_wskaznik_walidowane(monkeypatch):
    kod = _przechwyc(monkeypatch)
    with pytest.raises(wal.BladWejscia):
        wykres.ustaw_interwal("1); alert(1")
    with pytest.raises(wal.BladWejscia):
        wykres.ustaw_typ("1); alert(1)")
    with pytest.raises(wal.BladWejscia):
        wykres.ustaw_typ(10**9)
    with pytest.raises(wal.BladWejscia):
        wykres.swiece("100; while(1){}")
    with pytest.raises(wal.BladWejscia):
        wykres.swiece(10**9)             # było obcinane po cichu; teraz jawny błąd
    with pytest.raises(wal.BladWejscia):
        wykres.usun_wskaznik("a'); x('")
    with pytest.raises(wal.BladWejscia):
        wykres.dodaj_wskaznik("x" * 5000)
    assert kod == []


def test_poprawny_symbol_idzie_jako_literal_json(monkeypatch):
    kod = _przechwyc(monkeypatch)
    wykres.ustaw_symbol("NASDAQ:NVDA")
    assert 'ch.setSymbol("NASDAQ:NVDA")' in kod[0]


def test_przelacz_zly_symbol_nie_rusza_wykresu(monkeypatch):
    kod = _przechwyc(monkeypatch)
    with pytest.raises(wal.BladWejscia):
        wykres.przelacz('FX:X"; alert(1)')
    assert kod == []


# ── replay / układ ──────────────────────────────────────────────────────
@pytest.mark.parametrize("zla", [float("inf"), float("nan"), -1, 10**12, True, "ala ma kota", "2026-13-45"])
def test_replay_zla_data(zla):
    with pytest.raises(replay.BladReplay):
        replay._na_milisekundy(zla)


def test_replay_dobra_data():
    assert replay._na_milisekundy("2026-09-11") == 1789084800000
    assert replay._na_milisekundy(1789084800) == 1789084800000


def test_replay_krok_i_opoznienie_poza_zakresem(monkeypatch):
    monkeypatch.setattr(replay, "stan", lambda: {"trwa": True, "autoodtwarzanie": False})
    monkeypatch.setattr(replay, "_r", lambda *a, **k: pytest.fail("nie powinno dojść do przeglądarki"))
    for zle in ("abc", 0, 501, 10**9, float("nan")):
        with pytest.raises(replay.BladReplay):
            replay.krok(zle)
    for zle in ("1); alert(1", 1, 10**9, float("inf")):
        with pytest.raises(replay.BladReplay):
            replay.autoplay(True, zle)


def test_uklad_indeks_i_symbol(monkeypatch):
    monkeypatch.setattr(uklad, "_u", lambda *a, **k: pytest.fail("ruszył przeglądarkę"))
    monkeypatch.setattr(uklad, "stan", lambda: {"wykresow": 2})
    with pytest.raises(uklad.BladUkladu):
        uklad.wybierz("x")
    with pytest.raises(uklad.BladUkladu):
        uklad.wybierz(5)
    # zły symbol odrzucony ZANIM przestawi aktywny wykres użytkownika
    with pytest.raises(uklad.BladUkladu):
        uklad.symbol_w_wykresie(0, 'FX:X"; alert(1)')
    with pytest.raises(uklad.BladUkladu):
        uklad.ustaw("s'); alert(1); ('")
