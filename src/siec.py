#!/usr/bin/env python3
"""VGM MCP — jedyne miejsce, przez które idą zapytania HTTP do TradingView.

Trzy zabezpieczenia, których sam `urllib.request.urlopen` nie daje:
- tylko HTTPS i tylko hosty TradingView (ciasteczka sesji nie wyjdą gdzie indziej),
- żadnych przekierowań (urllib przenosi nagłówki, także Cookie, na nowy host),
- twardy limit rozmiaru odpowiedzi (nie czytamy w nieskończoność do pamięci).
"""
from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from typing import Any

MAX_ODPOWIEDZI = 5_000_000   # bajtów; największe zmierzone odpowiedzi to setki kB
HOSTY = ("scanner.tradingview.com", "pine-facade.tradingview.com",
         "pricealerts.tradingview.com")


class BladSieci(Exception):
    """Zapytanie odrzucone przed wysłaniem albo odpowiedź niedozwolona."""


class _BezPrzekierowan(urllib.request.HTTPRedirectHandler):
    """Obsługa przekierowań, która każde przekierowanie zamienia w HTTPError."""
    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> urllib.request.Request | None:
        """Zamiast przekierować, rzuca HTTPError z adresem docelowym."""
        raise urllib.error.HTTPError(req.full_url, code,
                                     f"przekierowanie do {newurl[:80]} zablokowane",
                                     headers, fp)


_OPENER = urllib.request.build_opener(_BezPrzekierowan)


def sprawdz_adres(url: str) -> str:
    """Przepuszcza tylko HTTPS do hostów z HOSTY, bez danych logowania w adresie."""
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.hostname not in HOSTY or u.username or u.password:
        raise BladSieci(f"adres niedozwolony: {u.scheme}://{u.hostname}")
    return url


def pobierz(zad: urllib.request.Request, timeout: float, max_bajtow: int = MAX_ODPOWIEDZI) -> bytes:
    """Wysyła zapytanie i zwraca treść. Rzuca BladSieci, gdy host jest spoza listy
    albo odpowiedź przekracza limit; HTTPError i URLError przechodzą bez zmian."""
    sprawdz_adres(zad.full_url)
    with _OPENER.open(zad, timeout=timeout) as o:
        dane: bytes = o.read(max_bajtow + 1)
    if len(dane) > max_bajtow:
        raise BladSieci(f"odpowiedź większa niż {max_bajtow} bajtów")
    return dane
