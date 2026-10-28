"""Wspólne ustawienia testów bezpieczeństwa — żadnych połączeń sieciowych.

Każde wyjście poza proces (HTTP, CDP) jest podmieniane w samym teście.
Tu tylko zabezpieczenie: gdyby któraś poprawka przestała walidować wejście
i kod sięgnął po sieć, test ma się wywrócić, a nie połączyć.
"""
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture(autouse=True)
def bez_sieci(monkeypatch):
    def zabronione(*a, **k):
        raise AssertionError("test próbował otworzyć połączenie sieciowe")

    monkeypatch.setattr(socket, "create_connection", zabronione)
    monkeypatch.setattr(socket.socket, "connect", zabronione)


@pytest.fixture(autouse=True)
def bez_pauz(monkeypatch):
    """Odstępy między zapytaniami i ponowienia nie mają spowalniać testów."""
    import time

    monkeypatch.setattr(time, "sleep", lambda s: None)
