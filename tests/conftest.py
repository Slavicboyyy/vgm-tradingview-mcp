"""Wspólne przygotowanie testów integracyjnych.

Każdy test dostaje świeże zaślepki: sieć, przeglądarkę z CDP i zegar umowny.
Moduły z `src` są importowane raz; zaślepki podmieniają w nich tylko to,
co wychodzi na zewnątrz (`urllib.request.urlopen`, moduł `websocket`, `time`).
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

GLOWNY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GLOWNY / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Port ustalany przy imporcie `wykres` — bez tej zmiennej moduł sam szukałby
# przeglądarki na 9333, 9556 i 9222, czyli dotykałby prawdziwej maszyny.
PORT = 9333
os.environ["VGM_CDP_PORT"] = str(PORT)

import zaslepki  # noqa: E402


@pytest.fixture
def srodowisko():
    with zaslepki.podmienione(PORT) as sr:
        yield sr


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── klient MCP działający w pamięci, zgodny z mcp 1.x i 2.x ─────────────
class Klient:
    def __init__(self, sesja):
        self.s = sesja

    async def narzedzia(self):
        return (await self.s.list_tools()).tools

    async def wywolaj_surowo(self, nazwa, argumenty=None):
        return await self.s.call_tool(nazwa, argumenty or {})

    async def wywolaj(self, nazwa, argumenty=None):
        """Zwraca (treść JSON, czy_blad)."""
        r = await self.wywolaj_surowo(nazwa, argumenty)
        blad = getattr(r, "is_error", None)
        if blad is None:
            blad = getattr(r, "isError", False)
        tekst = r.content[0].text
        try:
            return json.loads(tekst), bool(blad)
        except ValueError:
            return tekst, bool(blad)


@asynccontextmanager
async def polacz():
    import serwer

    try:
        from mcp.client.client import Client  # mcp 2.x
    except ImportError:
        Client = None
    if Client is not None:
        async with Client(serwer.serwer) as c:
            yield Klient(c)
    else:
        from mcp.shared.memory import create_connected_server_and_client_session
        async with create_connected_server_and_client_session(serwer.serwer) as s:
            yield Klient(s)
