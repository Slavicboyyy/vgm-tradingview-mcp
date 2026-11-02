"""Testy błędów znalezionych przy wdrażaniu CI — każdy zawodził przed poprawką."""
from __future__ import annotations

import io
import sys
import tokenize
from pathlib import Path

import pytest

import analiza
import dane
import pine
import pomiar
import replay

SRC = Path(__file__).resolve().parent.parent / "src"


# ── składnia zgodna z Pythonem 3.11 ─────────────────────────────────────
def _zagniezdzone_f(sciezka):
    """Linie, w których f-string zawiera ten sam cudzysłów w polu {…}.

    Od Pythona 3.12 to działa, ale w 3.11 jest SyntaxError, a CI biegnie na 3.11.
    """
    zle, stos = [], []
    with open(sciezka, "rb") as f:
        for t in tokenize.tokenize(f.readline):
            if t.type == tokenize.FSTRING_START:
                if stos and t.string[-1] == stos[-1]:
                    zle.append(t.start[0])
                stos.append(t.string[-1])
            elif t.type == tokenize.FSTRING_END:
                stos.pop()
            elif t.type == tokenize.STRING and stos and t.string[-1] == stos[-1]:
                zle.append(t.start[0])
    return sorted(set(zle))


@pytest.mark.parametrize("plik", sorted(SRC.glob("*.py")), ids=lambda p: p.name)
def test_zrodla_kompiluja_sie_na_python_311(plik):
    if sys.version_info < (3, 12):
        compile(plik.read_text(encoding="utf-8"), str(plik), "exec")
    else:
        assert _zagniezdzone_f(plik) == [], \
            f"{plik.name}: f-string z tym samym cudzysłowem w środku (SyntaxError w 3.11)"


# ── pine._podglad ───────────────────────────────────────────────────────
def test_podglad_blad_bez_numeru_linii_nie_wywala():
    out = pine._podglad("plot(x)", [{"linia": None, "kolumna": None, "komunikat": "boom"}])
    assert "boom" in out and "?" in out


def test_podglad_wskazuje_linie_i_kolumne():
    out = pine._podglad("a\nplot(clse)", [{"linia": 2, "kolumna": 6, "komunikat": "nieznana"}])
    assert "   2 | plot(clse)" in out and "^-- nieznana" in out


# ── analiza.zmiennosc_swiec ─────────────────────────────────────────────
def _swiece(n):
    return [{"czas": i, "otwarcie": 10.0, "szczyt": 11.0, "dolek": 9.0, "zamkniecie": 10.0}
            for i in range(n)]


@pytest.mark.parametrize("okno", [0, -3])
def test_zmiennosc_swiec_odrzuca_okno_nie_dodatnie(monkeypatch, okno):
    monkeypatch.setattr(analiza, "_swiece_z_wykresu", lambda ile=0: _swiece(50))
    with pytest.raises(dane.BladTV):
        analiza.zmiennosc_swiec(50, okno)


# ── replay._na_milisekundy ──────────────────────────────────────────────
def test_data_replay_sekundy_jako_tekst():
    # przez MCP argument "data" jest zawsze tekstem
    assert replay._na_milisekundy("1700000000") == 1700000000 * 1000
    assert replay._na_milisekundy(1700000000) == 1700000000 * 1000


def test_data_replay_nadal_przyjmuje_daty():
    assert replay._na_milisekundy("2026-09-11") == 1789084800 * 1000
    assert replay._na_milisekundy("2026-09-11 13:30") == (1789084800 + 13 * 3600 + 1800) * 1000


# ── pomiar.czy_sygnal_czy_trend ─────────────────────────────────────────
@pytest.mark.parametrize("wskaznik, kier, prog, oczekiwany", [
    ("RSI", "ponizej", 30, 70),
    ("Bollinger", "powyzej", 90, 10),
    ("ADX", "powyzej", 30, 30),
])
def test_prog_odwrotny_lustro_dla_wskaznikow_0_100(monkeypatch, wskaznik, kier, prog, oczekiwany):
    wywolania = []

    def falszywe_zmierz(w, p, k, *a, **kw):
        wywolania.append((w, p, k))
        return {"caly_okres": {"sredni_zwrot_proc": 1.0, "wejsc": 30}}

    monkeypatch.setattr(pomiar, "zmierz", falszywe_zmierz)
    monkeypatch.setattr(pomiar, "odniesienie_trzymanie", lambda *a, **k: {"sredni_zwrot_proc": 0.5})
    r = pomiar.czy_sygnal_czy_trend(wskaznik, prog, kier, 10)
    assert wywolania[1][1] == oczekiwany
    assert r["warunek_odwrotny"].endswith(str(oczekiwany))


# ── pomiar.zmierz / zmierz_prog: zły kierunek ───────────────────────────
def _seria(n=120):
    out, c = [], 100.0
    for i in range(n):
        c += 1.0 if (i // 10) % 2 == 0 else -1.0
        out.append({"czas": i, "otwarcie": c, "szczyt": c + 0.5, "dolek": c - 0.5,
                    "zamkniecie": c})
    return out


def test_zmierz_odrzuca_nieznany_kierunek(monkeypatch):
    monkeypatch.setattr(analiza, "_swiece_z_wykresu", lambda ile=0: _seria())
    with pytest.raises(pomiar.BladPomiaru):
        pomiar.zmierz("RSI", 30, "w_dol")
    with pytest.raises(pomiar.BladPomiaru):
        pomiar.zmierz_prog("RSI", 30, "w_dol")


# ── pomiar._losuj_probe: pusta pula ─────────────────────────────────────
def test_losuj_probe_pusta_pula_nie_wywala():
    import random
    prob, blokowo = pomiar._losuj_probe(_seria(60), [16, 17], 0, 19, random.Random(1))
    assert prob == [] and blokowo is False
