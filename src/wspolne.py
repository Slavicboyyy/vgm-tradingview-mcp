"""VGM MCP — kod wspólny dla warstw: odstęp między zapytaniami i nagłówki."""
from __future__ import annotations

import time

# Nagłówki, bez których pine-facade i punkty konta odrzucają zapytanie (403).
# Samo User-Agent nie wystarcza — nginx wymaga też Origin i Referer.
UA_PRZEGLADARKI = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
ORIGIN_TV = "https://www.tradingview.com"
REFERER_TV = "https://www.tradingview.com/"


def odczekaj(ostatnie: list[float], odstep_s: float) -> None:
    """Czeka tyle, żeby od poprzedniego zapytania minęło `odstep_s`.

    `ostatnie` to jednoelementowa lista z czasem poprzedniego zapytania —
    każda warstwa trzyma własną, więc odstępy nie zlewają się ze sobą.
    """
    minelo = time.time() - ostatnie[0]
    if minelo < odstep_s:
        time.sleep(odstep_s - minelo)
    ostatnie[0] = time.time()
