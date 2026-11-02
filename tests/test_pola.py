"""Testy mapy pól — czysta struktura danych, bez żadnych zapytań."""
from __future__ import annotations

from collections import Counter

import pola


def test_wszystkie_to_suma_grup():
    assert len(pola.WSZYSTKIE) == sum(len(g) for g in pola.GRUPY.values())


def test_pola_nie_powtarzaja_sie():
    powt = [k for k, v in Counter(pola.WSZYSTKIE).items() if v > 1]
    assert powt == []


def test_liczba_pol_zgadza_sie_z_opisem_narzedzi():
    # opisy narzędzi serwera obiecują 91 pól
    assert len(pola.WSZYSTKIE) == 91


def test_grupy_nie_sa_puste_i_zawieraja_teksty():
    for nazwa, grupa in pola.GRUPY.items():
        assert grupa, nazwa
        assert all(isinstance(p, str) and p for p in grupa), nazwa


def test_pola_nie_maja_sufiksu_interwalu():
    # sufiks `|interwał` dokleja się przy zapytaniu, nie w mapie
    assert not [p for p in pola.WSZYSTKIE if "|" in p]


def test_zestawy_uzywaja_tylko_znanych_pol():
    znane = set(pola.WSZYSTKIE)
    for nazwa, zestaw in pola.ZESTAW.items():
        assert set(zestaw) <= znane, nazwa


def test_zestaw_pelny_to_wszystkie_pola():
    assert pola.ZESTAW["pelny"] == pola.WSZYSTKIE


def test_zestaw_ped_zaczyna_sie_od_ceny_ohlc():
    assert pola.ZESTAW["ped"][:4] == ["close", "open", "high", "low"]


def test_interwaly_pewne_sa_podzbiorem_interwalow():
    assert set(pola.INTERWALY_PEWNE) <= set(pola.INTERWALY)


def test_rynki_maja_opisy():
    assert {"forex", "crypto", "america", "poland"} <= set(pola.RYNKI)
    assert all(isinstance(v, str) and v for v in pola.RYNKI.values())
