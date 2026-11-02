"""Serwer na prawdziwym pakiecie `mcp` — bez atrapy z conftest.py.

Pozostałe testy podmieniają `mcp` atrapą, więc nie zauważą, że zainstalowana
wersja nie ma API, którego używa src/serwer.py (dekoratory `list_tools` i
`call_tool` z mcp 1.x; w mcp 2.x ich nie ma). Ten test importuje serwer
w osobnym procesie, gdzie atrapy nie ma, i woła oba dekorowane wejścia.
Nic nie łączy się z siecią: lista narzędzi i `vgm_rynki` działają lokalnie.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
BRAK_MCP = 77   # kod wyjścia podprocesu: pakietu `mcp` nie ma w środowisku

SKRYPT = r"""
import asyncio, importlib.util, json, sys
if importlib.util.find_spec("mcp") is None:
    sys.exit(%d)
from importlib.metadata import version
sys.path.insert(0, sys.argv[1])
import serwer
narzedzia = asyncio.run(serwer.lista_narzedzi())
wynik = asyncio.run(serwer.wywolaj("vgm_rynki", {}))
print(json.dumps({"mcp": version("mcp"), "narzedzi": len(narzedzia),
                  "typ": type(narzedzia[0]).__module__,
                  "rynki": json.loads(wynik[0].text)}))
""" % BRAK_MCP


def test_serwer_importuje_sie_z_prawdziwym_mcp(tmp_path):
    p = subprocess.run([sys.executable, "-c", SKRYPT, str(SRC)],
                       cwd=tmp_path, capture_output=True, text=True, timeout=120)
    if p.returncode == BRAK_MCP:
        pytest.skip("pakiet mcp nie jest zainstalowany")
    assert p.returncode == 0, (
        "src/serwer.py nie działa z zainstalowanym pakietem mcp "
        "(requirements.txt przypina mcp>=1.0.0,<2):\n" + p.stderr[-2000:])
    w = json.loads(p.stdout.strip().splitlines()[-1])
    assert w["mcp"].startswith("1."), w["mcp"]
    assert w["typ"].startswith("mcp."), "lista narzędzi nie pochodzi z prawdziwego mcp"
    assert w["narzedzi"] == 63
    assert isinstance(w["rynki"], dict) and w["rynki"]
