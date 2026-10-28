#!/usr/bin/env python3
"""VGM MCP — serwer Model Context Protocol do TradingView.

Zasada: **w serwerze są wyłącznie narzędzia uruchomione na żywym rynku.**
Nic „na zapas", nic „powinno działać". Czego nie sprawdziłem, tego tu nie ma —
lista brakujących rzeczy stoi otwarcie w README.

Trzy warstwy o różnych wymaganiach:
- dane, analiza, pomiar, sprawdzanie Pine — bez logowania i bez przeglądarki,
- wykres — otwarta karta TradingView w przeglądarce z CDP,
- sesja (alerty, listy obserwowanych, zapis Pine, tester) — zalogowane konto.
"""
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analiza  # noqa: E402
import dane  # noqa: E402
import pola  # noqa: E402

from mcp.server import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402
from mcp.types import TextContent, Tool  # noqa: E402

serwer = Server("vgm-mcp")

UWAGA = ("Dane z publicznego punktu TradingView, liczone po ich stronie. "
         "To nie są kwotowania brokera — do handlu użyj ceny od swojego brokera.")

S: dict[str, Any] = {"type": "string"}
L: dict[str, Any] = {"type": "array", "items": {"type": "string"}}


def _n(nazwa: str, opis: str, wlasciwosci: dict[str, Any] | None = None,
       wymagane: list[str] | None = None) -> Tool:
    return Tool(
        name=nazwa,
        description=opis + " " + UWAGA,
        inputSchema={
            "type": "object",
            "properties": wlasciwosci or {},
            "required": wymagane or [],
        },
    )


@serwer.list_tools()
async def lista_narzedzi() -> list[Tool]:
    sym = {"symbol": dict(S, description="Nazwa z giełdą: FX:EURUSD, NASDAQ:NVDA, COINBASE:BTCUSD")}
    interw = {"interwal": dict(S, description="1, 5, 15, 60, 240, 1W. Pominięty = bieżący")}
    rynek = {"rynek": dict(S, description="forex, crypto, coin, america, poland, germany, uk, japan, futures, cfd", default="forex")}
    ile = {"ile": {"type": "integer", "default": 20}}

    return [
        # ── odczyt ──────────────────────────────────────────────────────
        _n("vgm_odczyt",
           "Wartości wybranych pól dla instrumentu. 91 dostępnych pól: cena, wolumen, "
           "oscylatory pędu, wskaźniki trendu, średnie, zmienność, poziomy, wyniki, ocena.",
           {**sym, "pola": dict(L, description="Nazwy pól. Pominięte = zestaw domyślny")},
           ["symbol"]),

        _n("vgm_obraz",
           "Pełny obraz instrumentu: wszystkie 91 pól pogrupowanych w dziewięć kategorii, "
           "jednym zapytaniem. Używaj, gdy chcesz zobaczyć całość naraz.",
           {**sym, **interw}, ["symbol"]),

        _n("vgm_obraz_pelny",
           "Wszystko o instrumencie w jednym wywołaniu: 91 pól, położenie ceny, "
           "układ średnich, zgodność przedziałów, a gdy przeglądarka jest dostępna "
           "— także stan wykresu i wartości wskaźników z niego. "
           "Bez przeglądarki zwraca samą część publiczną i mówi o tym wprost.",
           {"symbol": dict(S, description="np. FX:EURUSD")}, ["symbol"]),

        _n("vgm_rynki",
           "Spis rynków przyjmowanych przez przegląd, wszystkie sprawdzone: "
           "forex, kryptowaluty, akcje amerykańskie, GPW, niemieckie, brytyjskie, "
           "japońskie, kontrakty terminowe i na różnicę."),

        _n("vgm_pola",
           "Spis dostępnych pól z podziałem na grupy — sprawdź tu, zanim zgadniesz nazwę."),

        # ── położenie i układ ───────────────────────────────────────────
        _n("vgm_polozenie",
           "Gdzie stoi cena względem swoich odniesień, w procentach: miejsce w kanale "
           "Bollingera, miejsce w zakresie rocznym, odchylenie od średnich 20/50/200, "
           "szerokość kanału, zmienność ATR jako procent ceny.",
           {**sym, **interw}, ["symbol"]),

        _n("vgm_srednie",
           "Układ sześciu średnich wykładniczych (5 do 200): ile par stoi w kolejności "
           "rosnącej, ile w malejącej. Zwraca surowy fakt, nie nazywa go trendem.",
           {**sym, **interw}, ["symbol"]),

        # ── wiele interwałów ────────────────────────────────────────────
        _n("vgm_mtf",
           "Ten sam wskaźnik na kilku interwałach naraz, jednym zapytaniem. "
           "Zmierzone interwały: 1, 5, 15, 60, 240, 1W.",
           {**sym,
            "wskazniki": dict(L, description="np. RSI, ADX, Recommend.All"),
            "interwaly": L}, ["symbol"]),

        _n("vgm_zgodnosc",
           "Ile interwałów wskazuje w tę samą stronę. Zwraca zliczenie: które powyżej "
           "progu kupna, które poniżej progu sprzedaży. Celowo nie podejmuje decyzji "
           "handlowej — próg należy do strategii i wymaga własnego pomiaru.",
           {**sym, "interwaly": L,
            "prog_kupno": {"type": "number", "default": 55},
            "prog_sprzedaz": {"type": "number", "default": 45}}, ["symbol"]),

        _n("vgm_zgodnosc_pelna",
           "Tabela wielu wskaźników na wielu interwałach naraz — rozszerzenie vgm_zgodnosc "
           "na dowolny zestaw. Zwraca wartości i listę brakujących.",
           {**sym, "wskazniki": L, "interwaly": L}, ["symbol"]),

        # ── porównania ──────────────────────────────────────────────────
        _n("vgm_wiele",
           "Kilka instrumentów w jednym zapytaniu zamiast kilku osobnych.",
           {"symbole": L, "pola": L}, ["symbole"]),

        _n("vgm_porownaj",
           "Instrumenty obok siebie, posortowane po sile ruchu.",
           {"symbole": L, "pola": L}, ["symbole"]),

        # ── skany rynku ─────────────────────────────────────────────────
        _n("vgm_skan_wyprzedane",
           "Instrumenty z RSI poniżej progu.",
           {**rynek, "prog": {"type": "number", "default": 30}, **ile}),

        _n("vgm_skan_wykupione",
           "Instrumenty z RSI powyżej progu.",
           {**rynek, "prog": {"type": "number", "default": 70}, **ile}),

        _n("vgm_skan_trend",
           "Instrumenty z ADX powyżej progu — silny ruch kierunkowy. "
           "Zwraca też ADX+DI i ADX-DI, żeby było widać stronę.",
           {**rynek, "prog_adx": {"type": "number", "default": 30}, **ile}),

        _n("vgm_skan_wolumen",
           "Instrumenty z wolumenem powyżej wielokrotności średniej z dziesięciu dni.",
           {**rynek, "krotnosc": {"type": "number", "default": 2.0}, **ile}),

        _n("vgm_skan",
           "Dowolny filtr TradingView — pełna swoboda. Warunki w formacie "
           '[{"left":"RSI","operation":"less","right":30}]. '
           "Operacje: less, greater, equal, in_range, above_pct, below_pct.",
           {**rynek,
            "warunki": {"type": "array", "items": {"type": "object"}},
            "pola": L, **ile}, ["rynek", "warunki"]),

        # ── wykres: wymaga otwartej przeglądarki ────────────────────────
        Tool(name="vgm_wykres_karta",
             description=("Otwiera kartę z wykresem, gdy żadna nie jest otwarta. "
                          "Karta potrafi zniknąć: ktoś ją zamknie, przeglądarka ubije "
                          "ją przy przeciążeniu. Bez niej wszystkie narzędzia wykresu "
                          "przestają działać, choć nic nie jest zepsute. "
                          "Nic nie robi, gdy karta już jest."),
             inputSchema={"type": "object",
                          "properties": {"symbol": dict(S, default="FX:EURUSD")}}),

        Tool(name="vgm_wykres_zdrowie",
             description=("Czy da się sterować wykresem: czy przeglądarka odpowiada, "
                          "czy jest karta z TradingView, czy strona udostępnia API. "
                          "Sprawdź to przed każdym innym narzędziem wykresu. "
                          "Port bierze ze zmiennej VGM_CDP_PORT."),
             inputSchema={"type": "object", "properties": {}}),

        Tool(name="vgm_wykres_stan",
             description=("Co jest teraz na wykresie: instrument, przedział czasu, typ, "
                          "lista wskaźników i rysunków. Wymaga otwartej przeglądarki."),
             inputSchema={"type": "object", "properties": {}}),

        Tool(name="vgm_wykres_wartosci",
             description=("Bieżące wartości wszystkich wskaźników z wykresu — także "
                          "własnych, napisanych w Pine, których publiczne API nie zna. "
                          "To główny powód, dla którego warstwa przeglądarki istnieje."),
             inputSchema={"type": "object", "properties": {}}),

        Tool(name="vgm_wykres_przelacz",
             description=("Zmienia instrument i czeka, aż świece naprawdę do niego należą. "
                          "Używaj tego zamiast vgm_wykres_symbol, gdy zaraz potem czytasz "
                          "świece albo liczysz statystykę. Zmierzone: sama zmiana symbolu "
                          "potrafi zostawić świece poprzedniego instrumentu, a nic tego nie "
                          "sygnalizuje. To narzędzie sprawdza je krzyżowo z ceną z publicznego "
                          "punktu i w razie potrzeby przeładowuje stronę."),
             inputSchema={"type": "object",
                          "properties": {"symbol": S, "interwal": S},
                          "required": ["symbol"]}),

        Tool(name="vgm_przeglad_instrumentow",
             description=("Ten sam przegląd wskaźników na kilku instrumentach i przedziałach. "
                          "Wynik z jednego wykresu to jeden pomiar — dopiero powtórzenie "
                          "pokazuje, czy wniosek się utrzymuje. Przełącza z weryfikacją "
                          "danych i przywraca stan wyjściowy."),
             inputSchema={"type": "object",
                          "properties": {
                              "instrumenty": {"type": "array",
                                              "items": {"type": "array",
                                                        "items": {"type": "string"}}},
                              "po_ilu": {"type": "integer", "default": 10}}}),

        Tool(name="vgm_wykres_symbol",
             description="Zmienia instrument na wykresie, np. FX:EURUSD, NASDAQ:NVDA.",
             inputSchema={"type": "object",
                          "properties": {"symbol": S}, "required": ["symbol"]}),

        Tool(name="vgm_wykres_interwal",
             description="Zmienia przedział czasu wykresu: 1, 5, 15, 60, 240, D, W, M.",
             inputSchema={"type": "object",
                          "properties": {"interwal": S}, "required": ["interwal"]}),

        Tool(name="vgm_wykres_typ",
             description="Typ wykresu: 0 słupki, 1 świece, 3 linia, 9 Heikin Ashi.",
             inputSchema={"type": "object",
                          "properties": {"typ": {"type": "integer"}}, "required": ["typ"]}),

        Tool(name="vgm_wskaznik_dodaj",
             description=("Dodaje wskaźnik na wykres po pełnej nazwie, dokładnie takiej "
                          'jak w oknie wyboru TradingView: "Relative Strength Index", '
                          '"Moving Average Exponential", "Volume". '
                          "Uwaga, zmierzone: bez zalogowania TradingView liczy tylko jeden "
                          "wskaźnik naraz. Kolejne pojawiają się na liście, ale ich wartości "
                          "zostają puste. Usuń poprzedni przez vgm_wskaznik_usun albo zaloguj "
                          "się. Narzędzie czeka na dane i w odpowiedzi mówi, czy wskaźnik "
                          "faktycznie liczy."),
             inputSchema={"type": "object",
                          "properties": {"nazwa": S}, "required": ["nazwa"]}),

        Tool(name="vgm_wskaznik_usun",
             description="Usuwa wskaźnik z wykresu po identyfikatorze z vgm_wykres_stan.",
             inputSchema={"type": "object",
                          "properties": {"id": S}, "required": ["id"]}),

        Tool(name="vgm_wykres_swiece",
             description=("Świece historyczne z wykresu: czas, otwarcie, szczyt, dołek, "
                          "zamknięcie, wolumen. Bierze je z serii, którą wykres ma "
                          "wczytaną, więc nie potrzeba osobnego źródła ani konta. "
                          "Zwykle dostępnych jest kilkaset świec."),
             inputSchema={"type": "object",
                          "properties": {"ile": {"type": "integer", "default": 100}}}),

        Tool(name="vgm_swiece_statystyka",
             description=("Liczby policzone na świecach z wykresu: rozpiętość, miejsce "
                          "ceny w zakresie, średni zasięg świecy, udział świec wzrostowych, "
                          "największa luka, zmiana od początku okresu. "
                          "Bez zewnętrznego źródła danych."),
             inputSchema={"type": "object",
                          "properties": {"ile": {"type": "integer", "default": 200}}}),

        Tool(name="vgm_zmierz_prog",
             description=("Sprawdza, czy przekroczenie progu przez wskaźnik cokolwiek "
                          "zapowiada. Liczy zwrot po N świecach od wejścia, porównuje "
                          "z sygnałem losowym o tej samej częstości, dzieli okres na dwie "
                          "połowy i odejmuje spread. Odrzuca wynik przy mniej niż "
                          "dwudziestu wejściach. Zwraca zdanie mówiące wprost, czy sygnał "
                          "jest cokolwiek wart — także gdy nie jest."),
             inputSchema={"type": "object",
                          "properties": {
                              "prog": {"type": "number", "default": 30},
                              "kierunek": dict(S, description="ponizej albo powyzej",
                                               default="ponizej"),
                              "po_ilu": {"type": "integer", "default": 10},
                              "ile_swiec": {"type": "integer", "default": 0, "description": "0 = cała wczytana historia"},
                              "spread_proc": {"type": "number", "default": 0.02}}}),

        Tool(name="vgm_walk_forward",
             description=("Jedyny pomiar poza próbą. Próg wybierany na pierwszych 70% "
                          "świec (najwyższy z-score wobec placebo), sprawdzany na "
                          "ostatnich 30%, których wybór nie widział. Wszystko inne tu "
                          "mierzy w próbie, więc najlepszy próg zawsze wygląda dobrze. "
                          "Zwraca wynik każdego progu na uczeniu, wybrany próg i jego "
                          "przewagę, z-score i liczbę wejść poza próbą. Wymaga co najmniej "
                          "200 świec; sensownie od tysiąca. Świeże przełączenie symbolu "
                          "daje około 400 — pełna historia pojawia się tylko przy strategii "
                          "z głębokim testem na wykresie."),
             inputSchema={"type": "object",
                          "properties": {"wskaznik": dict(S, description="RSI, Bollinger, ADX, ATR_proc"),
                                         "kierunek": dict(S, description="ponizej albo powyzej"),
                                         "progi": {"type": "array", "items": {"type": "number"},
                                                   "description": "Pominięte = zestaw domyślny dla wskaźnika"},
                                         "po_ilu": {"type": "integer", "default": 10},
                                         "czesc_ucz": {"type": "number", "default": 0.7},
                                         "spread_proc": {"type": "number", "default": 0.0}},
                          "required": ["wskaznik"]}),

        Tool(name="vgm_zmierz",
             description=("To samo co vgm_zmierz_prog, ale dla dowolnego z czterech "
                          "wskaźników liczonych na świecach: RSI, Bollinger (położenie "
                          "w kanale, 0 to dolna wstęga, 100 to górna), ADX (siła ruchu "
                          "kierunkowego), ATR_proc (zasięg świecy jako procent ceny)."),
             inputSchema={"type": "object",
                          "properties": {
                              "wskaznik": dict(S, description="RSI, Bollinger, ADX, ATR_proc",
                                               default="RSI"),
                              "prog": {"type": "number", "default": 30},
                              "kierunek": dict(S, default="ponizej"),
                              "po_ilu": {"type": "integer", "default": 10},
                              "spread_proc": {"type": "number", "default": 0.02}}}),

        Tool(name="vgm_sygnal_czy_trend",
             description=("Rozstrzyga, czy warunek naprawdę coś wnosi, czy tylko łapie "
                          "trend. Porównuje cztery liczby: warunek, warunek odwrotny, "
                          "samo trzymanie przez N świec i losowe wejście. Prawdziwy sygnał "
                          "bije trzymanie, a jego odwrotność wypada gorzej. Sam trend daje "
                          "podobny wynik niezależnie od warunku. To ostrzejsze kryterium "
                          "niż samo placebo: sygnał może bić losowe wejście, a mimo to "
                          "przegrywać z nicnierobieniem."),
             inputSchema={"type": "object",
                          "properties": {
                              "wskaznik": dict(S, default="Bollinger"),
                              "prog": {"type": "number", "default": 90},
                              "kierunek": dict(S, default="powyzej"),
                              "po_ilu": {"type": "integer", "default": 10}}}),

        Tool(name="vgm_koszt_a_przewaga",
             description=("Przy jakim koszcie transakcji sygnał przestaje mieć sens. "
                          "Liczy transakcje BEZ nakładania (jedna pozycja naraz) i obciąża "
                          "każde podejście jego prawdziwą liczbą transakcji: sygnał płaci "
                          "koszt przy każdym wejściu, kupno z trzymaniem raz. "
                          "To zwykle zmienia wnioski — przy dłuższym trzymaniu sąsiednie "
                          "wejścia to niemal ta sama pozycja, a sumowanie ich jak "
                          "niezależnych zawyża wynik kilkukrotnie."),
             inputSchema={"type": "object",
                          "properties": {
                              "wskaznik": dict(S, default="Bollinger"),
                              "prog": {"type": "number", "default": 90},
                              "kierunek": dict(S, default="powyzej"),
                              "po_ilu": {"type": "integer", "default": 40},
                              "koszty": {"type": "array", "items": {"type": "number"}}}}),

        Tool(name="vgm_jak_dlugo_trzymac",
             description=("Po ilu świecach sygnał daje najwięcej ponad samo trzymanie. "
                          "Zmierzone: ten sam warunek potrafi działać odwrotnie na krótkim "
                          "terminie i dobrze na długim. Porównuje różnicę wobec trzymania "
                          "i rozstęp wobec warunku odwrotnego, bo sam zwrot rośnie przy "
                          "dłuższym trzymaniu niezależnie od sygnału."),
             inputSchema={"type": "object",
                          "properties": {
                              "wskaznik": dict(S, default="Bollinger"),
                              "prog": {"type": "number", "default": 90},
                              "kierunek": dict(S, default="powyzej"),
                              "dlugosci": {"type": "array", "items": {"type": "integer"}}}}),

        Tool(name="vgm_odniesienie_trzymanie",
             description=("Ile daje samo trzymanie przez N świec, bez żadnego sygnału. "
                          "Uczciwszy punkt odniesienia niż losowe wejście."),
             inputSchema={"type": "object",
                          "properties": {"po_ilu": {"type": "integer", "default": 10}}}),

        Tool(name="vgm_przeglad_wskaznikow",
             description=("Siedem warunków na czterech wskaźnikach, jeden przebieg. "
                          "Odpowiada na pytanie, czy którykolwiek cokolwiek zapowiada "
                          "na tym instrumencie i przedziale. Zwraca też te, które nie "
                          "przeszły, wraz z powodem."),
             inputSchema={"type": "object",
                          "properties": {
                              "po_ilu": {"type": "integer", "default": 10},
                              "spread_proc": {"type": "number", "default": 0.02}}}),

        Tool(name="vgm_porownaj_progi",
             description=("Ten sam pomiar na kilku progach naraz. Pokazuje, gdzie leży "
                          "granica między liczbą wejść a siłą sygnału, zamiast zgadywać. "
                          "Próg przechodzi tylko wtedy, gdy ma dodatni zwrot po spreadzie, "
                          "bije sygnał losowy, jest zgodny w obu połowach okresu i ma co "
                          "najmniej dwadzieścia wejść."),
             inputSchema={"type": "object",
                          "properties": {
                              "progi": {"type": "array", "items": {"type": "number"}},
                              "kierunek": dict(S, default="ponizej"),
                              "po_ilu": {"type": "integer", "default": 10},
                              "spread_proc": {"type": "number", "default": 0.02}}}),

        Tool(name="vgm_swiece_przedzialy",
             description=("Statystyka świec z kilku przedziałów czasu naraz. Przełącza "
                          "wykres na każdy, liczy i wraca na wyjściowy. Trwa kilka sekund "
                          "na przedział, bo wykres musi wczytać dane."),
             inputSchema={"type": "object",
                          "properties": {"przedzialy": {"type": "array", "items": {"type": "string"}},
                                         "ile": {"type": "integer", "default": 100}}}),

        Tool(name="vgm_swiece_zmiennosc",
             description=("Zmienność w dwóch oknach: świeższym i wcześniejszym, plus ich "
                          "stosunek. Podział na dwie części to zasada pomiaru — jedna "
                          "liczba nic nie mówi, dopóki nie widać, czy powtarza się w drugim "
                          "okresie."),
             inputSchema={"type": "object",
                          "properties": {"ile": {"type": "integer", "default": 200},
                                         "okno": {"type": "integer", "default": 20}}}),

        Tool(name="vgm_wykres_zrzut",
             description=("Zapisuje obraz wykresu do pliku PNG i zwraca ścieżkę. "
                          "Pozwala obejrzeć wykres, nie tylko odczytać z niego liczby. "
                          "Przed zrzutem zamyka okna zachęt zasłaniające widok."),
             inputSchema={"type": "object",
                          "properties": {
                              "sciezka": dict(S, description="Gdzie zapisać. Pominięta = plik tymczasowy"),
                              "zamknij_okna": {"type": "boolean", "default": True}}}),

        # ── sesja: wymaga zalogowania na TradingView ────────────────────
        Tool(name="vgm_sesja",
             description=("Czy w przeglądarce jest sesja TradingView i jaki plan konta. "
                          "Sprawdza ciasteczko sessionid (HttpOnly, przez CDP) oraz obiekt "
                          "użytkownika na stronie. Zmierzone: sam document.cookie nigdy go "
                          "nie widzi, więc wcześniejsze sprawdzanie zawsze mówiło brak."),
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="vgm_alerty",
             description=("Wszystkie alerty cenowe z konta, przez HTTP z ciasteczkami sesji, "
                          "bez klikania w stronę. Zmierzone: 208 alertów, symbol rozpakowany "
                          "z formatu ={...} TradingView."),
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="vgm_lista_obserwowanych",
             description=("Instrumenty z listy obserwowanych otwartej w panelu wykresu. "
                          "Zmierzone: 29 symboli z listy Forex. Wymaga otwartego panelu prawego."),
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="vgm_skrypty_pine",
             description="Skrypty Pine zapisane na koncie. Zmierzone: 59.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="vgm_zrodlo_pine",
             description="Kod źródłowy zapisanego skryptu po identyfikatorze z vgm_skrypty_pine.",
             inputSchema={"type": "object", "properties": {"id": S}, "required": ["id"]}),
        Tool(name="vgm_zapisz_pine",
             description=("Zapisuje nowy skrypt Pine na koncie przez API strony. Zmierzone: "
                          "lista rośnie o jeden, zwraca identyfikator. Sprawdź kod wcześniej "
                          "przez vgm_pine_sprawdz."),
             inputSchema={"type": "object", "properties": {"kod": S, "nazwa": S},
                          "required": ["kod", "nazwa"]}),
        Tool(name="vgm_usun_pine",
             description="Usuwa zapisany skrypt po identyfikatorze. Nieodwracalne.",
             inputSchema={"type": "object", "properties": {"id": S}, "required": ["id"]}),
        Tool(name="vgm_strategie_wbudowane",
             description="Wbudowane strategie TradingView z identyfikatorami. Zmierzone: 20 ze 145.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="vgm_tester_raport",
             description=("Otwiera Strategy Tester i czyta raport strategii z wykresu. "
                          "Zwraca linie panelu i czy strategia zrobiła transakcje. "
                          "Wymaga własnej strategii na wykresie — wbudowanych nie da się "
                          "dodać przez createStudy (sprawdzone trzema nazwami). Wyniki są "
                          "poglądowe: tester wypełnia na zamknięciu świecy."),
             inputSchema={"type": "object", "properties": {}}),

        # ── układ okna: kilka wykresów naraz ────────────────────────────
        Tool(name="vgm_uklad_stan",
             description=("Jaki jest układ okna, ile jest wykresów, który aktywny i co "
                          "na każdym stoi. Podaje też liczbę paneli w aktywnym wykresie "
                          "(pierwszy to cena, kolejne to wskaźniki w osobnych oknach) "
                          "i czy układ ma niezapisane zmiany."),
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="vgm_uklad_ustaw",
             description=("Dzieli okno na kilka wykresów. Kody: s jeden, 2h dwa w poziomie, "
                          "2v dwa w pionie, 2-1 dwa u góry i jeden pod, 3h, 3v, 4 dwa na dwa, "
                          "6, 8. Zmienia to, co widzi użytkownik — wróć kodem s. Zwraca "
                          "`zgodny`, bo przy nieobsługiwanym kodzie TradingView przyjmuje "
                          "wywołanie i nic nie robi."),
             inputSchema={"type": "object",
                          "properties": {"kod": dict(S, default="s",
                                                     description="s, 2h, 2v, 2-1, 3h, 3v, 4, 6, 8")}}),
        Tool(name="vgm_uklad_wybierz",
             description=("Wybiera aktywny wykres w układzie, licząc od zera. Wszystkie "
                          "pozostałe narzędzia wykresu działają na aktywnym, więc to "
                          "przełącznik dla vgm_wykres_symbol, vgm_wskaznik_dodaj i reszty."),
             inputSchema={"type": "object",
                          "properties": {"indeks": {"type": "integer", "default": 0}}}),
        Tool(name="vgm_uklad_symbol",
             description=("Ustawia instrument na wybranym wykresie układu, nie na aktywnym. "
                          "Po wywołaniu aktywny zostaje ten zmieniony. Sprawdza odczytem, "
                          "czy instrument naprawdę się zmienił."),
             inputSchema={"type": "object",
                          "properties": {"indeks": {"type": "integer"},
                                         "symbol": dict(S, description="np. FX:GBPUSD"),
                                         "interwal": dict(S, description="pominięty = bez zmiany")},
                          "required": ["indeks", "symbol"]}),

        # ── odtwarzanie historii: wymaga otwartej przeglądarki ──────────
        Tool(name="vgm_replay_stan",
             description=("Stan odtwarzania historii: czy dostępne, czy trwa, na której "
                          "świecy stoi, jak głęboko sięga historia instrumentu. "
                          "Sprawdź przed każdym innym narzędziem odtwarzania."),
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="vgm_replay_start",
             description=("Cofa wykres do podanej daty i włącza tryb odtwarzania — świeca "
                          "po świecy, bez podglądania przyszłości. Data jako YYYY-MM-DD, "
                          "YYYY-MM-DD HH:MM albo sekundy; pominięta = początek historii "
                          "(zmierzone na EURUSD: 2001-11-28). Zostawia wykres w trybie "
                          "odtwarzania, więc po skończeniu wywołaj vgm_replay_stop."),
             inputSchema={"type": "object",
                          "properties": {"data": dict(S, description="np. 2026-09-11 albo 2026-09-11 13:30")}}),
        Tool(name="vgm_replay_krok",
             description=("Przesuwa odtwarzanie o podaną liczbę świec. Zwraca, gdzie stoi "
                          "i czy wykres naprawdę ruszył — bo API potwierdza krok, nawet "
                          "gdy nic się nie stało. Zmierzone: cztery kroki na trzyminutowych "
                          "świecach przesunęły wykres o dwanaście minut."),
             inputSchema={"type": "object",
                          "properties": {"ile": {"type": "integer", "default": 1,
                                                 "description": "1 do 500"}}}),
        Tool(name="vgm_replay_autoplay",
             description=("Włącza lub wyłącza samoczynne przesuwanie świec. Opóźnienie "
                          "w milisekundach na świecę: 100 to dziesięć świec na sekundę, "
                          "większa liczba to wolniej. Zmierzone: przy 300 ms sześć sekund "
                          "realnego czasu przejechało 69 minut wykresu."),
             inputSchema={"type": "object",
                          "properties": {"wlacz": {"type": "boolean", "default": True},
                                         "opoznienie_ms": {"type": "integer",
                                                           "description": "np. 100, 300, 1000"}}}),
        Tool(name="vgm_replay_stop",
             description=("Kończy odtwarzanie, wraca do czasu rzeczywistego i chowa pasek. "
                          "Wywołaj zawsze po skończonej pracy — inaczej użytkownik zostaje "
                          "z wykresem cofniętym w przeszłość."),
             inputSchema={"type": "object", "properties": {}}),

        # ── Pine Script: bez przeglądarki ───────────────────────────────
        Tool(name="vgm_pine_sprawdz",
             description=("Kompiluje kod Pine w kompilatorze TradingView i zwraca błędy "
                          "z dokładną linią i kolumną, plus podgląd wskazujący miejsce. "
                          "Bez przeglądarki i bez konta, odpowiedź w około sekundę. "
                          "Wywołuj to zawsze przed wstawieniem skryptu na wykres."),
             inputSchema={"type": "object",
                          "properties": {"kod": dict(S, description="Kod Pine Script")},
                          "required": ["kod"]}),

        Tool(name="vgm_pine_sprawdz_plik",
             description="To samo co vgm_pine_sprawdz, ale czyta kod z pliku na dysku.",
             inputSchema={"type": "object",
                          "properties": {"sciezka": S}, "required": ["sciezka"]}),

        Tool(name="vgm_pine_szkielet",
             description=("Zwraca gotowy szkielet wskaźnika Pine w wersji 5, sprawdzony "
                          "w kompilatorze. Punkt wyjścia do pisania własnego."),
             inputSchema={"type": "object",
                          "properties": {"nazwa": S,
                                         "na_wykresie": {"type": "boolean", "default": True}}}),
    ]


@serwer.call_tool()
async def wywolaj(nazwa: str, a: dict[str, Any]) -> list[TextContent]:
    def ok(x: Any) -> list[TextContent]:
        return [TextContent(type="text", text=json.dumps(x, ensure_ascii=False, indent=1))]

    def przez_tabele(tabela: dict[str, Callable[[dict[str, Any]], Any]],
                     wyjatek: type[Exception],
                     dodatek: dict[str, str] | None = None) -> list[TextContent]:
        """Woła narzędzie z tabeli; wyjątek warstwy staje się odpowiedzią z `blad`."""
        try:
            return ok(tabela[nazwa](a))
        except wyjatek as e:
            return ok({"blad": str(e), "narzedzie": nazwa, **(dodatek or {})})

    try:
        if nazwa == "vgm_odczyt":
            return ok(dane.odczyt(a["symbol"], a.get("pola")))
        if nazwa == "vgm_obraz":
            return ok(analiza.obraz(a["symbol"], a.get("interwal")))
        if nazwa == "vgm_rynki":
            return ok(pola.RYNKI)
        if nazwa == "vgm_obraz_pelny":
            return ok(analiza.obraz_pelny(a["symbol"]))
        if nazwa == "vgm_pola":
            return ok({g: lista for g, lista in pola.GRUPY.items()}
                      | {"interwaly_zmierzone": pola.INTERWALY_PEWNE})
        if nazwa == "vgm_polozenie":
            return ok(analiza.polozenie(a["symbol"], a.get("interwal")))
        if nazwa == "vgm_srednie":
            return ok(analiza.uklad_srednich(a["symbol"], a.get("interwal")))
        if nazwa == "vgm_mtf":
            return ok(dane.mtf(a["symbol"], a.get("wskazniki"), a.get("interwaly")))
        if nazwa == "vgm_zgodnosc":
            return ok(dane.zgodnosc(a["symbol"], a.get("interwaly"),
                                    a.get("prog_kupno", 55), a.get("prog_sprzedaz", 45)))
        if nazwa == "vgm_zgodnosc_pelna":
            return ok(analiza.zgodnosc_pelna(a["symbol"], a.get("wskazniki"),
                                             a.get("interwaly")))
        if nazwa == "vgm_wiele":
            return ok(dane.wiele(a["symbole"], a.get("pola")))
        if nazwa == "vgm_porownaj":
            return ok(analiza.porownaj(a["symbole"], a.get("pola")))
        if nazwa == "vgm_skan_wyprzedane":
            return ok(analiza.skan_wyprzedane(a.get("rynek", "forex"),
                                              a.get("prog", 30), a.get("ile", 20)))
        if nazwa == "vgm_skan_wykupione":
            return ok(analiza.skan_wykupione(a.get("rynek", "forex"),
                                             a.get("prog", 70), a.get("ile", 20)))
        if nazwa == "vgm_skan_trend":
            return ok(analiza.skan_silny_trend(a.get("rynek", "forex"),
                                               a.get("prog_adx", 30), a.get("ile", 20)))
        if nazwa == "vgm_skan_wolumen":
            return ok(analiza.skan_wolumen(a.get("rynek", "forex"),
                                           a.get("krotnosc", 2.0), a.get("ile", 20)))
        if nazwa == "vgm_skan":
            return ok(analiza.skan_wlasny(a["rynek"], a["warunki"],
                                          a.get("pola"), a.get("ile", 30)))
        # ── sesja ───────────────────────────────────────────────────────
        SESJA: dict[str, Callable[[dict[str, Any]], Any]] = {
                 "vgm_sesja": lambda a: sesja.czy_zalogowany(),
                 "vgm_alerty": lambda a: sesja.alerty(),
                 "vgm_lista_obserwowanych": lambda a: sesja.lista_obserwowanych(),
                 "vgm_skrypty_pine": lambda a: sesja.skrypty_pine(),
                 "vgm_zrodlo_pine": lambda a: sesja.zrodlo_pine(a["id"]),
                 "vgm_zapisz_pine": lambda a: sesja.zapisz_pine(a["kod"], a["nazwa"]),
                 "vgm_usun_pine": lambda a: sesja.usun_pine(a["id"]),
                 "vgm_strategie_wbudowane": lambda a: sesja.strategie_wbudowane(),
                 "vgm_tester_raport": lambda a: sesja.tester_raport()}
        if nazwa in SESJA:
            import sesja
            return przez_tabele(
                SESJA, sesja.BladSesji,
                {"podpowiedz": "zaloguj się na TradingView w przeglądarce z CDP"})

        # ── Pine ────────────────────────────────────────────────────────
        if nazwa.startswith("vgm_pine"):
            import pine

            try:
                if nazwa == "vgm_pine_sprawdz":
                    return ok(pine.sprawdz(a["kod"]))
                if nazwa == "vgm_pine_sprawdz_plik":
                    return ok(pine.sprawdz_plik(a["sciezka"]))
                if nazwa == "vgm_pine_szkielet":
                    return ok({"kod": pine.szkielet(a.get("nazwa", "Nowy wskaźnik"),
                                                    a.get("na_wykresie", True))})
            except pine.BladPine as e:
                return ok({"blad": str(e), "narzedzie": nazwa})

        # ── wykres ──────────────────────────────────────────────────────
        # Lista musi obejmować KAŻDE narzędzie tej grupy — narzędzie spoza niej
        # jest zadeklarowane, ale nieobsługiwane, i zwraca "nieznane narzędzie".
        # Pilnuje tego .narzedzia/sprawdz_wszystkie.py, który woła wszystkie po kolei.
        if nazwa.startswith(("vgm_wykres", "vgm_wskaznik", "vgm_swiece",
                             "vgm_zmierz", "vgm_porownaj_progi",
                             "vgm_przeglad_",          # wskaznikow ORAZ instrumentow
                             "vgm_sygnal_czy_trend",
                             "vgm_odniesienie_trzymanie", "vgm_jak_dlugo_trzymac",
                             "vgm_koszt_a_przewaga", "vgm_walk_forward",
                             "vgm_replay_", "vgm_uklad_")):
            import pomiar
            import wykres  # dopiero tutaj — reszta działa bez websocket-client

            try:
                if nazwa == "vgm_wykres_karta":
                    return ok(wykres.zapewnij_karte(a.get("symbol", "FX:EURUSD")))
                if nazwa == "vgm_wykres_zdrowie":
                    return ok(wykres.zdrowie())
                if nazwa == "vgm_wykres_stan":
                    return ok(wykres.stan())
                if nazwa == "vgm_wykres_wartosci":
                    return ok(wykres.wartosci())
                if nazwa == "vgm_wykres_przelacz":
                    return ok(wykres.przelacz(a["symbol"], a.get("interwal")))
                if nazwa == "vgm_przeglad_instrumentow":
                    inst = a.get("instrumenty")
                    if inst:
                        inst = [tuple(x) for x in inst]
                    return ok(pomiar.przeglad_instrumentow(inst, a.get("po_ilu", 10)))
                if nazwa == "vgm_wykres_symbol":
                    return ok(wykres.ustaw_symbol(a["symbol"]))
                if nazwa == "vgm_wykres_interwal":
                    return ok(wykres.ustaw_interwal(a["interwal"]))
                if nazwa == "vgm_wykres_typ":
                    return ok(wykres.ustaw_typ(a["typ"]))
                if nazwa == "vgm_wskaznik_dodaj":
                    return ok(wykres.dodaj_wskaznik(a["nazwa"]))
                if nazwa == "vgm_wskaznik_usun":
                    return ok(wykres.usun_wskaznik(a["id"]))
                if nazwa == "vgm_wykres_swiece":
                    return ok(wykres.swiece(a.get("ile", 100)))
                if nazwa == "vgm_swiece_statystyka":
                    return ok(analiza.statystyka_swiec(a.get("ile", 200)))
                if nazwa == "vgm_zmierz_prog":
                    return ok(pomiar.zmierz_prog(
                        "RSI", a.get("prog", 30), a.get("kierunek", "ponizej"),
                        a.get("po_ilu", 10), a.get("ile_swiec", 0),
                        a.get("spread_proc", 0.02)))
                if nazwa.startswith("vgm_uklad_"):
                    import uklad
                    UKLAD: dict[str, Callable[[dict[str, Any]], Any]] = {
                             "vgm_uklad_stan": lambda a: uklad.stan(),
                             "vgm_uklad_ustaw": lambda a: uklad.ustaw(a.get("kod", "s")),
                             "vgm_uklad_wybierz": lambda a: uklad.wybierz(a.get("indeks", 0)),
                             "vgm_uklad_symbol": lambda a: uklad.symbol_w_wykresie(
                                 a["indeks"], a["symbol"], a.get("interwal"))}
                    return przez_tabele(UKLAD, uklad.BladUkladu)
                if nazwa.startswith("vgm_replay_"):
                    import replay
                    REPLAY: dict[str, Callable[[dict[str, Any]], Any]] = {
                              "vgm_replay_stan": lambda a: replay.stan(),
                              "vgm_replay_start": lambda a: replay.start(a.get("data")),
                              "vgm_replay_krok": lambda a: replay.krok(a.get("ile", 1)),
                              "vgm_replay_autoplay": lambda a: replay.autoplay(
                                  a.get("wlacz", True), a.get("opoznienie_ms")),
                              "vgm_replay_stop": lambda a: replay.stop()}
                    return przez_tabele(REPLAY, replay.BladReplay)
                if nazwa == "vgm_walk_forward":
                    return ok(pomiar.walk_forward(
                        a.get("wskaznik", "RSI"), a.get("kierunek", "ponizej"), a.get("progi"),
                        a.get("po_ilu", 10), a.get("ile_swiec", 0), a.get("czesc_ucz", 0.7),
                        a.get("spread_proc", 0.0)))
                if nazwa == "vgm_zmierz":
                    return ok(pomiar.zmierz(
                        a.get("wskaznik", "RSI"), a.get("prog", 30),
                        a.get("kierunek", "ponizej"), a.get("po_ilu", 10), 0, a.get("spread_proc", 0.02)))
                if nazwa == "vgm_sygnal_czy_trend":
                    return ok(pomiar.czy_sygnal_czy_trend(
                        a.get("wskaznik", "Bollinger"), a.get("prog", 90),
                        a.get("kierunek", "powyzej"), a.get("po_ilu", 10)))
                if nazwa == "vgm_koszt_a_przewaga":
                    return ok(pomiar.koszt_a_przewaga(
                        a.get("wskaznik", "Bollinger"), a.get("prog", 90),
                        a.get("kierunek", "powyzej"), a.get("po_ilu", 40),
                        0, a.get("koszty")))
                if nazwa == "vgm_jak_dlugo_trzymac":
                    return ok(pomiar.jak_dlugo_trzymac(
                        a.get("wskaznik", "Bollinger"), a.get("prog", 90),
                        a.get("kierunek", "powyzej"), a.get("dlugosci")))
                if nazwa == "vgm_odniesienie_trzymanie":
                    return ok(pomiar.odniesienie_trzymanie(a.get("po_ilu", 10)))
                if nazwa == "vgm_przeglad_wskaznikow":
                    return ok(pomiar.przeglad_wskaznikow(
                        a.get("po_ilu", 10), 0, a.get("spread_proc", 0.02)))
                if nazwa == "vgm_porownaj_progi":
                    return ok(pomiar.porownaj_progi(
                        a.get("progi"), a.get("kierunek", "ponizej"),
                        a.get("po_ilu", 10), 0, a.get("spread_proc", 0.02)))
                if nazwa == "vgm_swiece_przedzialy":
                    return ok(analiza.swiece_wiele_przedzialow(
                        a.get("przedzialy"), a.get("ile", 100)))
                if nazwa == "vgm_swiece_zmiennosc":
                    return ok(analiza.zmiennosc_swiec(a.get("ile", 200), a.get("okno", 20)))
                if nazwa == "vgm_wykres_zrzut":
                    return ok(wykres.zrzut(a.get("sciezka"), a.get("zamknij_okna", True)))
            except wykres.BladWykresu as e:
                return ok({"blad": str(e), "narzedzie": nazwa,
                           "podpowiedz": "sprawdź vgm_wykres_zdrowie"})

        return ok({"blad": f"nieznane narzędzie: {nazwa}"})

    except dane.BladTV as e:
        return ok({"blad": str(e), "narzedzie": nazwa})
    except KeyError as e:
        return ok({"blad": f"brakuje wymaganego pola: {e}", "narzedzie": nazwa})


async def main() -> None:
    async with stdio_server() as (we, wy):
        await serwer.run(we, wy, serwer.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
