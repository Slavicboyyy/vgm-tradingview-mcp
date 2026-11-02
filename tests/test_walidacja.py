"""Walidacja wejścia od klienta: symbole, przedziały, liczby, listy, filtry, ścieżki."""
import os

import pytest

import pola
import walidacja as wal


@pytest.mark.parametrize("s", ["FX:EURUSD", "NASDAQ:NVDA", "COMEX:GC1!", "BINANCE:BTCUSDT.P",
                               "NYSE:BRK.B", "EURUSD"])
def test_symbol_poprawny(s):
    assert wal.symbol(s) == s


@pytest.mark.parametrize("s", [
    "", "A" * 200, "FX:EURUSD&fields=x", "FX:EURUSD\nHost: x", "../../etc",
    "FX:EUR USD", 'FX:"; alert(1);//', "FX:EURUSD#", "FX:EURUSD?x=1", "a:b:c", None, 5, ["FX:EURUSD"],
])
def test_symbol_zly(s):
    with pytest.raises(wal.BladWejscia):
        wal.symbol(s)


@pytest.mark.parametrize("i", ["1", "5", "240", "D", "W", "M", "1W", "1D", 60])
def test_interwal_poprawny(i):
    wal.interwal(i)


@pytest.mark.parametrize("i", ["", "abc", "1);alert(1", "60 ", "-1", "1e9", "99999", None, True])
def test_interwal_zly(i):
    with pytest.raises(wal.BladWejscia):
        wal.interwal(i)


@pytest.mark.parametrize("x", [float("nan"), float("inf"), -float("inf"), True, "30", None, 1e30])
def test_liczba_odrzuca_smieci(x):
    with pytest.raises(wal.BladWejscia):
        wal.liczba(x, "prog", -1e9, 1e9)


def test_calkowita_granice_i_typy():
    assert wal.calkowita(10.0, "n", 1, 20) == 10
    for zle in (0, 21, 1.5, "5", True, None, float("nan")):
        with pytest.raises(wal.BladWejscia):
            wal.calkowita(zle, "n", 1, 20)


def test_lista_limit_elementow_i_typ():
    with pytest.raises(wal.BladWejscia):
        wal.lista(["RSI"] * (wal.MAX_ELEMENTOW + 1), "pola", wal.pole)
    with pytest.raises(wal.BladWejscia):
        wal.lista("RSI", "pola", wal.pole)      # string zamiast listy: nie iterujemy po znakach
    assert wal.lista(["RSI", "ADX+DI", "RSI|60"], "pola", wal.pole)


def test_rynek_tylko_z_listy_bez_wstrzykniecia_sciezki():
    assert wal.rynek("forex", pola.RYNKI) == "forex"
    for zly in ("../../etc/passwd", "forex/../crypto", "forex?x=1", "", None):
        with pytest.raises(wal.BladWejscia):
            wal.rynek(zly, pola.RYNKI)


def test_warunki_poprawny_i_zle():
    ok = [{"left": "RSI", "operation": "less", "right": 30}]
    assert wal.warunki(ok) == ok
    zle = [
        [{"left": "RSI", "operation": "less"}],                              # brak right
        [{"left": "RSI", "operation": "drop_table", "right": 1}],            # obca operacja
        [{"left": "RSI", "operation": "less", "right": 1, "extra": 1}],      # obce pole
        [{"left": "RSI;x", "operation": "less", "right": 1}],
        [{"left": "RSI", "operation": "less", "right": float("nan")}],
        [{"left": "RSI", "operation": "less", "right": {"a": 1}}],
        ["nie obiekt"],
        [ok[0]] * (wal.MAX_WARUNKOW + 1),
    ]
    for w in zle:
        with pytest.raises(wal.BladWejscia):
            wal.warunki(w)


def test_pary_instrumentow_limit_czasu_pracy_wykresu():
    assert wal.pary_instrument_przedzial([["FX:EURUSD", "60"]]) == [("FX:EURUSD", "60")]
    with pytest.raises(wal.BladWejscia):
        wal.pary_instrument_przedzial([["FX:EURUSD", "60"]] * (wal.MAX_INSTRUMENTOW + 1))
    for zle in ([["FX:EURUSD"]], [["FX:EURUSD", "x;y"]], ["FX:EURUSD"], "FX:EURUSD"):
        with pytest.raises(wal.BladWejscia):
            wal.pary_instrument_przedzial(zle)


def test_nazwa_skryptu_bez_cudzyslowu_i_znakow_sterujacych():
    assert wal.nazwa_skryptu("Mój wskaźnik")
    for zla in ('a"b', "a\\b", "a\nb", "", "x" * 101):
        with pytest.raises(wal.BladWejscia):
            wal.nazwa_skryptu(zla)


def test_kod_pine_limit_dlugosci():
    wal.kod_pine("//@version=5\nindicator('x')\n")
    with pytest.raises(wal.BladWejscia):
        wal.kod_pine("x" * (wal.MAX_KOD_PINE + 1))
    with pytest.raises(wal.BladWejscia):
        wal.kod_pine("   ")


# ── ścieżki ─────────────────────────────────────────────────────────────
@pytest.fixture
def katalog_pine(monkeypatch, tmp_path):
    """Katalog ustawiony jawnie w VGM_KATALOG_PINE — jedyne miejsce odczytu."""
    baza = tmp_path / "pine"
    baza.mkdir()
    monkeypatch.setenv("VGM_KATALOG_PINE", str(baza))
    return baza


def test_odczyt_pliku_tylko_z_katalogu_bazowego(katalog_pine, tmp_path):
    (katalog_pine / "ok.pine").write_text("//@version=5")
    (katalog_pine / "ok.txt").write_text("//@version=5")
    assert wal.sciezka_do_odczytu("ok.pine") == (katalog_pine / "ok.pine").resolve()
    assert wal.sciezka_do_odczytu("ok.txt") == (katalog_pine / "ok.txt").resolve()
    assert wal.sciezka_do_odczytu(str(katalog_pine / "ok.pine")) == (katalog_pine / "ok.pine").resolve()

    poza = tmp_path / "tajne.txt"
    poza.write_text("klucz")
    for zla in (str(poza), "../tajne.txt", "/etc/passwd", "sub/../../tajne.txt"):
        with pytest.raises(wal.BladWejscia):
            wal.sciezka_do_odczytu(zla)


@pytest.mark.parametrize("wartosc", [None, "", "   "])
def test_odczyt_bez_vgm_katalog_pine_odrzucony(monkeypatch, tmp_path, wartosc):
    # bez jawnie ustawionej zmiennej nie zgadujemy katalogu — nawet roboczego
    (tmp_path / "ok.pine").write_text("//@version=5")
    monkeypatch.chdir(tmp_path)
    if wartosc is None:
        monkeypatch.delenv("VGM_KATALOG_PINE", raising=False)
    else:
        monkeypatch.setenv("VGM_KATALOG_PINE", wartosc)
    with pytest.raises(wal.BladWejscia, match="VGM_KATALOG_PINE"):
        wal.sciezka_do_odczytu("ok.pine")
    with pytest.raises(wal.BladWejscia, match="VGM_KATALOG_PINE"):
        wal.sciezka_do_odczytu(str(tmp_path / "ok.pine"))


def test_odczyt_vgm_katalog_pine_wzgledny_albo_nie_katalog(monkeypatch, tmp_path):
    (tmp_path / "ok.pine").write_text("//@version=5")
    monkeypatch.chdir(tmp_path)
    for zla in (".", "pine", str(tmp_path / "ok.pine"), str(tmp_path / "nie_ma")):
        monkeypatch.setenv("VGM_KATALOG_PINE", zla)
        with pytest.raises(wal.BladWejscia, match="VGM_KATALOG_PINE"):
            wal.sciezka_do_odczytu("ok.pine")


def test_odczyt_pliku_dowiazanie_na_zewnatrz_odrzucone(katalog_pine, tmp_path):
    cel = tmp_path / "poza_bazy.pine"
    cel.write_text("sekret")
    (katalog_pine / "link.pine").symlink_to(cel)
    with pytest.raises(wal.BladWejscia):
        wal.sciezka_do_odczytu("link.pine")


def test_odczyt_pliku_dowiazanie_rozwiazywane_do_celu(katalog_pine):
    # dowiązanie wewnątrz katalogu: liczy się cel, z jego rozszerzeniem
    (katalog_pine / "skrypt.pine").write_text("//@version=5")
    (katalog_pine / "klucz.pem").write_text("x")
    (katalog_pine / "alias.pine").symlink_to(katalog_pine / "skrypt.pine")
    (katalog_pine / "przebrany.pine").symlink_to(katalog_pine / "klucz.pem")
    assert wal.sciezka_do_odczytu("alias.pine") == (katalog_pine / "skrypt.pine").resolve()
    with pytest.raises(wal.BladWejscia, match=".pine i .txt"):
        wal.sciezka_do_odczytu("przebrany.pine")


def test_katalog_bazowy_przez_dowiazanie_jest_rozwiazywany(monkeypatch, tmp_path):
    prawdziwy = tmp_path / "prawdziwy"
    prawdziwy.mkdir()
    (prawdziwy / "a.pine").write_text("//@version=5")
    (tmp_path / "skrot").symlink_to(prawdziwy, target_is_directory=True)
    monkeypatch.setenv("VGM_KATALOG_PINE", str(tmp_path / "skrot"))
    assert wal.sciezka_do_odczytu("a.pine") == (prawdziwy / "a.pine").resolve()


def test_odczyt_pliku_rozszerzenie_rozmiar_katalog(katalog_pine):
    (katalog_pine / "klucz.pem").write_text("x")
    (katalog_pine / "bez_rozszerzenia").write_text("x")
    (katalog_pine / "duzy.pine").write_bytes(b"x" * (wal.MAX_PLIK_PINE + 1))
    (katalog_pine / "graniczny.pine").write_bytes(b"x" * wal.MAX_PLIK_PINE)
    (katalog_pine / "katalog.pine").mkdir()
    for zla in ("klucz.pem", "bez_rozszerzenia", "duzy.pine", "katalog.pine", "nie_ma.pine"):
        with pytest.raises(wal.BladWejscia):
            wal.sciezka_do_odczytu(zla)
    assert wal.sciezka_do_odczytu("graniczny.pine").name == "graniczny.pine"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="brak os.mkfifo")
def test_odczyt_tylko_zwykly_plik_nie_fifo(katalog_pine):
    os.mkfifo(katalog_pine / "potok.pine")
    with pytest.raises(wal.BladWejscia, match="zwykły plik"):
        wal.sciezka_do_odczytu("potok.pine")


def test_zapis_zrzutu_tylko_png_w_katalogu_bazowym(tmp_path):
    p = wal.sciezka_do_zapisu("wykres.png", tmp_path)
    assert p == (tmp_path / "wykres.png").resolve()
    for zla in ("../wykres.png", "/etc/cron.d/x.png", "~/.bashrc", ".bashrc", "wykres.sh",
                "../../authorized_keys", "bez_rozszerzenia"):
        with pytest.raises(wal.BladWejscia):
            wal.sciezka_do_zapisu(zla, tmp_path)


def test_zapis_zrzutu_nie_idzie_za_dowiazaniem(tmp_path):
    cel = tmp_path.parent / "wazny_plik"
    cel.write_text("nie nadpisuj")
    baza = tmp_path / "zrzuty"
    baza.mkdir()
    (baza / "x.png").symlink_to(cel)
    with pytest.raises(wal.BladWejscia):
        wal.sciezka_do_zapisu("x.png", baza)
    assert cel.read_text() == "nie nadpisuj"


def test_limit_rozmiaru_wyniku():
    wal.wynik_nie_za_duzy("x" * 10)
    with pytest.raises(wal.BladWejscia):
        wal.wynik_nie_za_duzy("x" * (wal.MAX_WYNIK_ZNAKOW + 1))
