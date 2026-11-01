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


def test_karta_nie_wybiera_obcej_strony_z_nazwa_w_adresie(port_cdp, monkeypatch):
    karty = [
        {"type": "page", "url": "https://evil.example/?tradingview.com", "webSocketDebuggerUrl": "ws://zla"},
        {"type": "service_worker", "url": "https://www.tradingview.com/sw.js", "webSocketDebuggerUrl": "ws://sw"},
        {"type": "page", "url": "https://www.tradingview.com/chart/", "webSocketDebuggerUrl": "ws://dobra"},
    ]
    monkeypatch.setattr(wykres, "websocket", object())
    monkeypatch.setattr(wykres.urllib.request, "urlopen",
                        lambda *a, **k: _Odp(json.dumps(karty).encode()))
    assert wykres._karta()["webSocketDebuggerUrl"] == "ws://dobra"


def test_karta_brak_prawdziwej_karty_to_blad(port_cdp, monkeypatch):
    karty = [{"type": "page", "url": "https://evil.example/?tradingview.com"}]
    monkeypatch.setattr(wykres, "websocket", object())
    monkeypatch.setattr(wykres.urllib.request, "urlopen",
                        lambda *a, **k: _Odp(json.dumps(karty).encode()))
    with pytest.raises(wykres.BladWykresu):
        wykres._karta()


def test_karta_przegladarka_nie_odpowiada_to_blad_z_limitem_czasu(port_cdp, monkeypatch):
    zapisane = {}

    def urlopen(url, timeout=None):
        zapisane["timeout"] = timeout
        raise OSError("connection refused")

    monkeypatch.setattr(wykres, "websocket", object())
    monkeypatch.setattr(wykres.urllib.request, "urlopen", urlopen)
    with pytest.raises(wykres.BladWykresu):
        wykres._karta()
    assert zapisane["timeout"] == 10


# ── port: tylko z VGM_CDP_PORT, bez domyślnych i zgadywanych ────────────
@pytest.fixture
def port_cdp(monkeypatch):
    """Dowolny port ustawiony jawnie — wartość nie ma znaczenia, sieć jest atrapą."""
    monkeypatch.setenv("VGM_CDP_PORT", "41234")
    return 41234


@pytest.mark.parametrize("v", ["abc", "0", "70000", "-1", "41234; rm -rf /", "1.5", "１２３"])
def test_zly_port_z_env_odrzucony(v, monkeypatch):
    monkeypatch.setenv("VGM_CDP_PORT", v)
    with pytest.raises(wykres.BladWykresu, match="VGM_CDP_PORT"):
        wykres._port_cdp()


def test_dobry_port_z_env(port_cdp):
    assert wykres._port_cdp() == port_cdp


@pytest.mark.parametrize("v", [None, "", "  "])
def test_brak_portu_to_czytelny_blad_bez_zgadywania(v, monkeypatch):
    if v is None:
        monkeypatch.delenv("VGM_CDP_PORT", raising=False)
    else:
        monkeypatch.setenv("VGM_CDP_PORT", v)
    monkeypatch.setattr(wykres, "websocket", object())
    monkeypatch.setattr(wykres.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("bez VGM_CDP_PORT nie wolno pytać żadnego portu"))
    with pytest.raises(wykres.BladWykresu, match="brak zmiennej VGM_CDP_PORT"):
        wykres._port_cdp()
    with pytest.raises(wykres.BladWykresu, match="brak zmiennej VGM_CDP_PORT"):
        wykres._karta()
    with pytest.raises(wykres.BladWykresu, match="brak zmiennej VGM_CDP_PORT"):
        wykres.otworz_karte("FX:EURUSD")


def test_zdrowie_bez_portu_mowi_czego_brakuje(monkeypatch):
    monkeypatch.delenv("VGM_CDP_PORT", raising=False)
    monkeypatch.setattr(wykres.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("bez VGM_CDP_PORT nie wolno pytać żadnego portu"))
    z = wykres.zdrowie()
    assert z["port"] is None and z["gotowy"] is False and z["przegladarka"] is False
    assert "VGM_CDP_PORT" in z["powod"]


def test_karta_pyta_tylko_port_z_env(port_cdp, monkeypatch):
    adresy = []

    def urlopen(url, timeout=None):
        adresy.append(url)
        return _Odp(json.dumps([{"type": "page", "url": "https://www.tradingview.com/chart/"}]).encode())

    monkeypatch.setattr(wykres, "websocket", object())
    monkeypatch.setattr(wykres.urllib.request, "urlopen", urlopen)
    wykres._karta()
    assert adresy == [f"http://localhost:{port_cdp}/json"]


def test_import_wykresu_nie_pyta_o_port_ani_sieci(tmp_path):
    """Import nie może łączyć się z siecią ani wymagać VGM_CDP_PORT."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    src = Path(wykres.__file__).resolve().parent
    kod = ("import socket, sys\n"
           "def nie(*a, **k): raise SystemExit('import próbował łączyć się z siecią')\n"
           "socket.create_connection = nie\n"
           "socket.socket.connect = nie\n"
           f"sys.path.insert(0, {str(src)!r})\n"
           "import wykres\n"
           "assert not hasattr(wykres, 'PORT')\n")
    env = {k: v for k, v in os.environ.items() if k != "VGM_CDP_PORT"}
    p = subprocess.run([sys.executable, "-c", kod], cwd=tmp_path, env=env,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-1000:]


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
