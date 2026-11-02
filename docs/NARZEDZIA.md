# Narzędzia serwera VGM MCP — opis API

Dokument opisuje każde narzędzie zarejestrowane w `src/serwer.py`
(`lista_narzedzi`): wejście, wyjście, przykład wywołania i błędy.
Zgodność listy narzędzi i parametrów z tym plikiem sprawdza
`tests/test_dokumentacja.py` (bez sieci). Dodajesz narzędzie albo parametr —
dopisz sekcję tutaj, inaczej test padnie.

## Jak czytać ten dokument

**Skąd opis wyjścia.** Każdy opis wyjścia wynika z kodu (`src/*.py`), nie
z odpowiedzi zarejestrowanej na żywym rynku. Przy pisaniu tego dokumentu
**żadne narzędzie nie zostało uruchomione na żywym rynku** ani na prawdziwej
przeglądarce — testy idą bez sieci. W każdej sekcji stoi to wprost w linii
„Na żywym rynku". Wartości liczbowe w przykładach to opisy typu
w nawiasach ostrych (`<liczba>`), nie notowania.

Klucze, które kod przepisuje wprost z odpowiedzi TradingView (nazwy pól
skanera, obiekty z API strony), zależą od tego, co TradingView odda — mogą
mieć wartość `null` albo nie pojawić się wcale. Przy takich kluczach
napisano to osobno.

**Tabela wejścia.** Kolumny: parametr, typ JSON ze schematu, czy wymagany,
wartość domyślna ze schematu (`—` gdy schemat jej nie podaje) i uwagi
(zakres sprawdzany przez serwer, domyślna wartość z kodu). Gdy kod używa
innej wartości domyślnej niż schemat, mówi o tym kolumna uwag.

**Wywołanie.** Przykłady pokazują `name` i `arguments` tak, jak klient MCP
wysyła je w `tools/call`.

## Wspólne zasady odpowiedzi i błędów

Każde narzędzie zwraca **jeden blok tekstu** (`TextContent`) z JSON-em
(`ensure_ascii=False`, wcięcie 1). Błąd też jest JSON-em, nie wyjątkiem
protokołu. Kolejność obsługi w `serwer.wywolaj`:

1. **Walidacja argumentów** (`serwer.zwaliduj`). Argumenty muszą być obiektem
   o najwyżej 20 kluczach. Klucze z tabeli `WALIDATORY` (oraz `ile`) są
   sprawdzane; zły argument daje
   `{"blad": "niepoprawny argument — <pole>: <powód>", "narzedzie": "<nazwa>"}`.
   Klucze spoza tabeli (`kod`, `nazwa`, `sciezka`, `data`, `opoznienie_ms`)
   przechodzą bez zmian i sprawdza je dopiero warstwa niżej. Nieznane klucze
   nie są odrzucane — narzędzie je pomija.
2. **Wykonanie w wątku z limitem 240 s.** Po przekroczeniu:
   `{"blad": "przekroczono limit 240 s", "narzedzie": "<nazwa>"}`.
3. **Brak wymaganego parametru:**
   `{"blad": "brakuje wymaganego pola: '<pole>'", "narzedzie": "<nazwa>"}`.
4. **Błąd warstwy** — zależnie od grupy narzędzia:
   - dane publiczne (`dane.BladTV`): `{"blad", "narzedzie"}`; typowe treści:
     „TradingView odmówił (403|429). Zatrzymuję się…", „HTTP <kod> przy <ścieżka>",
     „brak danych dla <symbol> — sprawdź nazwę z giełdą", „adres niedozwolony…";
   - wykres (`wykres.BladWykresu`): `{"blad", "narzedzie", "podpowiedz": "sprawdź vgm_wykres_zdrowie"}`;
     typowe treści: „brak zmiennej VGM_CDP_PORT…", „VGM_CDP_PORT='…' nie jest portem",
     „przeglądarka nie odpowiada na porcie <port>…", „żadna karta nie ma otwartego TradingView…",
     „strona nie udostępnia API wykresu", „wykres jeszcze się nie wczytał",
     „brakuje pakietu websocket-client…";
   - sesja (`sesja.BladSesji`): `{"blad", "narzedzie", "podpowiedz": "zaloguj się na TradingView w przeglądarce z CDP"}`;
   - Pine (`pine.BladPine`), układ (`uklad.BladUkladu`), odtwarzanie
     (`replay.BladReplay`): `{"blad", "narzedzie"}` bez podpowiedzi;
   - walidacja wewnątrz warstwy (`walidacja.BladWejscia` rzucona poza
     `zwaliduj`): `{"blad": "<pole>: <powód>", "narzedzie"}` — bez przedrostka
     „niepoprawny argument";
   - każdy inny wyjątek: `{"blad": "<NazwaTypu>: <do 120 znaków treści>", "narzedzie"}`.
     Tak wracają `pomiar.BladPomiaru` (np. „BladPomiaru: za mało świec: 0,
     potrzeba co najmniej 60") oraz `BladWykresu` rzucony z narzędzi sesji
     (np. „BladWykresu: brak zmiennej VGM_CDP_PORT…") — w obu przypadkach
     bez pola `podpowiedz`.
5. **Za duży wynik:** odpowiedź dłuższa niż 1 000 000 znaków daje
   `{"blad": "wynik za duży (<n> znaków) — zmniejsz `ile`", "narzedzie"}`.
6. **Nieznane narzędzie:** `{"blad": "nieznane narzędzie: <nazwa>"}` (bez klucza `narzedzie`).

Wspólne walidatory (w nawiasie zakres): `symbol` — litery, cyfry i `_.!-`,
opcjonalnie z giełdą (`FX:EURUSD`); `interwal` — `^\d{1,4}[SDWMH]?$` albo `D`,
`W`, `M` (liczba całkowita jest zamieniana na tekst); pole — nazwa pola
TradingView z opcjonalnym `|interwał`; listy — najwyżej 50 elementów, chyba że
napisano inaczej; `id` — do 100 znaków `A-Za-z0-9_;.-`; `ile` — 1–200 dla
narzędzi `vgm_skan*`, 1–500 dla `vgm_replay_krok`, 1–5000 dla pozostałych.

Opis każdego narzędzia z grupy danych publicznych (zbudowanego przez
`serwer._n`) ma dopisane zastrzeżenie `UWAGA`: dane pochodzą z publicznego
punktu TradingView, nie od brokera.

Wymagania warstw:

| grupa | potrzebuje |
|---|---|
| dane publiczne, Pine | sieci do `scanner.tradingview.com` / `pine-facade.tradingview.com`; bez konta i przeglądarki |
| wykres, pomiar, układ, odtwarzanie | przeglądarki z CDP (`VGM_CDP_PORT`) i otwartej karty TradingView; pakietu `websocket-client` |
| sesja | jak wykres, plus zalogowanego konta TradingView w tej przeglądarce |

---

## Dane publiczne: odczyt

### `vgm_odczyt`

Wartości wybranych pól TradingView dla jednego instrumentu
(`dane.odczyt`, jedno zapytanie `GET /symbol`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `symbol` | string | tak | — | z giełdą, np. `FX:EURUSD` |
| `pola` | array of string | nie | — | najwyżej 50 nazw; pominięte albo puste = 22 pola: `close, open, high, low, change, change_abs, volume`, 12 pierwszych wskaźników (`RSI` … `BB.upper`) i `Recommend.All, Recommend.MA, Recommend.Other` |

**Wyjście**

Obiekt `{<nazwa pola>: <wartość>}` przepisany z odpowiedzi TradingView.
Klucze to nazwy pól z zapytania, ale ich obecność i wartości (liczba albo
`null`) zależą wyłącznie od TradingView.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_odczyt", "arguments": {"symbol": "FX:EURUSD", "pola": ["close", "RSI", "ADX"]}}
```
```
{"close": <liczba|null>, "RSI": <liczba|null>, "ADX": <liczba|null>}
```

**Błędy**

- zły `symbol` albo nazwa pola → „niepoprawny argument — …";
- TradingView zwrócił pusty obiekt → „brak danych dla <symbol> — sprawdź nazwę z giełdą, np. FX:EURUSD";
- 403/429, inny HTTP, błąd sieci → komunikat `BladTV` (patrz zasady wspólne).

### `vgm_obraz`

Wszystkie 91 pól z `pola.GRUPY` jednym zapytaniem, pogrupowane w dziewięć kategorii
(`analiza.obraz`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `symbol` | string | tak | — | z giełdą |
| `interwal` | string | nie | — | np. `60`; pominięty = przedział bieżący (pola bez sufiksu) |

**Wyjście**

`{"symbol", "interwal", "cena", "wolumen", "ped", "trend", "srednie", "zmiennosc", "poziomy", "wynik", "ocena"}`.
`interwal` to podany przedział albo `"biezacy"`. Każda grupa to obiekt
`{<pole>: <wartość>}`; pola, dla których TradingView nie oddał wartości
(albo oddał `null`), są pomijane — liczba kluczy w grupie zależy od TradingView.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; zawartość grup zależy od odpowiedzi TradingView.

**Przykład**

```json
{"name": "vgm_obraz", "arguments": {"symbol": "FX:EURUSD", "interwal": "60"}}
```
```
{"symbol": "FX:EURUSD", "interwal": "60",
 "cena": {"close": <liczba>, ...}, "wolumen": {...}, "ped": {...}, "trend": {...},
 "srednie": {...}, "zmiennosc": {...}, "poziomy": {...}, "wynik": {...}, "ocena": {...}}
```

**Błędy**

- zły `symbol` / `interwal` → „niepoprawny argument — …";
- pusta odpowiedź → „brak danych dla <symbol> …"; 403/429/HTTP → `BladTV`.

### `vgm_obraz_pelny`

Wszystko o instrumencie w jednym wywołaniu: `vgm_obraz`, `vgm_polozenie`,
`vgm_srednie`, `vgm_zgodnosc_pelna` (wszystkie na przedziale bieżącym), a gdy
przeglądarka jest gotowa — także stan wykresu i wartości wskaźników
(`analiza.obraz_pelny`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `symbol` | string | tak | — | z giełdą |

**Wyjście**

`{"symbol", "pola", "polozenie", "srednie", "zgodnosc", "wykres"}` oraz
`"wskazniki_z_wykresu"`, gdy wykres jest dostępny.
`pola`, `polozenie`, `srednie`, `zgodnosc` mają kształt wyjść odpowiednio
`vgm_obraz`, `vgm_polozenie`, `vgm_srednie`, `vgm_zgodnosc_pelna`.
`wykres` to wyjście `vgm_wykres_stan`, a gdy przeglądarki nie ma —
`{"niedostepny": "<powód>"}`. `wskazniki_z_wykresu` to wyjście `vgm_wykres_wartosci`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_obraz_pelny", "arguments": {"symbol": "FX:EURUSD"}}
```
```
{"symbol": "FX:EURUSD", "pola": {...}, "polozenie": {...}, "srednie": {...},
 "zgodnosc": {...}, "wykres": {"niedostepny": "brak zmiennej VGM_CDP_PORT — ..."}}
```

**Błędy**

- błąd części publicznej (`BladTV`: brak ceny, za mało średnich, 403/429…) przerywa całe narzędzie;
- błąd przeglądarki **nie** jest błędem narzędzia — trafia do `wykres.niedostepny` (do 80 znaków).

### `vgm_rynki`

Spis rynków przyjmowanych przez skany (`pola.RYNKI`). Działa lokalnie, bez sieci.

**Wejście**

Brak parametrów.

**Wyjście**

Obiekt `{<kod rynku>: <opis po polsku>}` z kluczami `forex, crypto, coin,
america, poland, germany, uk, japan, futures, cfd`.

Na żywym rynku: nie dotyczy (stała z kodu, bez zapytania).

**Przykład**

```json
{"name": "vgm_rynki", "arguments": {}}
```
```
{"forex": "pary walutowe", "crypto": "kryptowaluty", ..., "cfd": "kontrakty na różnicę"}
```

**Błędy**

Brak błędów własnych (poza wspólnymi, np. argumenty niebędące obiektem).

### `vgm_pola`

Spis dostępnych pól w dziewięciu grupach i lista zmierzonych przedziałów.
Działa lokalnie, bez sieci.

**Wejście**

Brak parametrów.

**Wyjście**

`{"cena": [...], "wolumen": [...], "ped": [...], "trend": [...], "srednie": [...],
"zmiennosc": [...], "poziomy": [...], "wynik": [...], "ocena": [...],
"interwaly_zmierzone": ["1", "5", "15", "60", "240", "1W"]}` — listy nazw z `pola.GRUPY`.

Na żywym rynku: nie dotyczy (stała z kodu, bez zapytania).

**Przykład**

```json
{"name": "vgm_pola", "arguments": {}}
```
```
{"cena": ["close", "open", ...], ..., "interwaly_zmierzone": ["1", "5", "15", "60", "240", "1W"]}
```

**Błędy**

Brak błędów własnych.

### `vgm_polozenie`

Gdzie stoi cena względem kanału Bollingera, zakresu rocznego i średnich EMA,
w procentach (`analiza.polozenie`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `symbol` | string | tak | — | z giełdą |
| `interwal` | string | nie | — | pominięty = bieżący |

**Wyjście**

`{"symbol", "interwal", "cena", "w_kanale_bollingera_proc", "w_zakresie_rocznym_proc",
"nad_ema20_proc", "nad_ema50_proc", "nad_ema200_proc", "szerokosc_bollingera_proc",
"atr_proc_ceny"}`. Wszystkie wartości poza `symbol`/`interwal`/`cena` to liczby
zaokrąglone albo `null`, gdy TradingView nie oddał potrzebnego pola (albo
dzielnik wynosi zero). `w_kanale_bollingera_proc`: 0 = dolna wstęga, 100 = górna.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; wartości zależą od pól TradingView.

**Przykład**

```json
{"name": "vgm_polozenie", "arguments": {"symbol": "NASDAQ:NVDA"}}
```
```
{"symbol": "NASDAQ:NVDA", "interwal": "biezacy", "cena": <liczba>,
 "w_kanale_bollingera_proc": <liczba|null>, ..., "atr_proc_ceny": <liczba|null>}
```

**Błędy**

- brak `close` w odpowiedzi → „brak ceny dla <symbol>";
- pusta odpowiedź → „brak danych dla …"; 403/429/HTTP → `BladTV`.

### `vgm_srednie`

Układ sześciu średnich EMA (5, 10, 20, 50, 100, 200): ile sąsiednich par stoi
w kolejności rosnącej, ile w malejącej (`analiza.uklad_srednich`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `symbol` | string | tak | — | z giełdą |
| `interwal` | string | nie | — | pominięty = bieżący |

**Wyjście**

`{"symbol", "interwal", "srednie": {"EMA5": <liczba>, ...}, "cena",
"par_w_kolejnosci_rosnacej", "par_w_kolejnosci_malejacej", "par_razem",
"uporzadkowane_w_pelni"}`. „Rosnąca" znaczy tu: krótsza średnia nad dłuższą.
W `srednie` są tylko średnie z wartością.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_srednie", "arguments": {"symbol": "FX:EURUSD", "interwal": "240"}}
```
```
{"symbol": "FX:EURUSD", "interwal": "240", "srednie": {"EMA5": <liczba>, ...},
 "cena": <liczba>, "par_w_kolejnosci_rosnacej": <int>, "par_w_kolejnosci_malejacej": <int>,
 "par_razem": <int>, "uporzadkowane_w_pelni": <bool>}
```

**Błędy**

- mniej niż dwie średnie z wartością → „za mało średnich dla <symbol>";
- 403/429/HTTP/pusta odpowiedź → `BladTV`.

## Dane publiczne: wiele przedziałów

### `vgm_mtf`

Te same wskaźniki na kilku przedziałach jednym zapytaniem (sufiks `|<przedział>`, `dane.mtf`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `symbol` | string | tak | — | z giełdą |
| `wskazniki` | array of string | nie | — | nazwy pól; z kodu: `RSI, ADX, Recommend.All` |
| `interwaly` | array of string | nie | — | z kodu: `5, 15, 60, 240`; pusty napis odrzuca walidacja serwera |

**Wyjście**

`{<wskaźnik>: {<przedział>: <wartość|null>}}`. Przedziały, których TradingView
nie oddał, nie pojawiają się w obiekcie wskaźnika.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; obecność przedziałów zależy od TradingView.

**Przykład**

```json
{"name": "vgm_mtf", "arguments": {"symbol": "FX:EURUSD", "wskazniki": ["RSI"], "interwaly": ["15", "60"]}}
```
```
{"RSI": {"15": <liczba|null>, "60": <liczba|null>}}
```

**Błędy**

- zły przedział / pole → „niepoprawny argument — interwaly: …" / „… wskazniki: …";
- `BladTV` jak w `vgm_odczyt`.

### `vgm_zgodnosc`

Ile przedziałów ma RSI powyżej progu kupna, a ile poniżej progu sprzedaży.
Nie podejmuje decyzji (`dane.zgodnosc`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `symbol` | string | tak | — | z giełdą |
| `interwaly` | array of string | nie | — | z kodu: `5, 15, 60, 240` |
| `prog_kupno` | number | nie | `55` | 0–100 (sprawdza warstwa danych) |
| `prog_sprzedaz` | number | nie | `45` | 0–100 (sprawdza warstwa danych) |

**Wyjście**

`{"symbol", "rsi": {<przedział>: <liczba|null>}, "za_kupnem": [<przedział>],
"za_sprzedaza": [<przedział>], "bez_danych": [<przedział>], "wszystkie_zgodne": <bool>}`.
Listy są posortowane jak napisy. `wszystkie_zgodne` jest prawdą, gdy wszystkie
podane przedziały są po jednej stronie.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_zgodnosc", "arguments": {"symbol": "FX:EURUSD", "prog_kupno": 60, "prog_sprzedaz": 40}}
```
```
{"symbol": "FX:EURUSD", "rsi": {"5": <liczba>, ...}, "za_kupnem": [...],
 "za_sprzedaza": [...], "bez_danych": [...], "wszystkie_zgodne": <bool>}
```

**Błędy**

- próg spoza 0–100 → `{"blad": "prog_kupno: 150 poza zakresem 0–100"}` (bez przedrostka „niepoprawny argument", bo sprawdza warstwa danych);
- `BladTV` jak w `vgm_odczyt`.

### `vgm_zgodnosc_pelna`

Tabela wielu wskaźników na wielu przedziałach i lista brakujących wartości
(`analiza.zgodnosc_pelna`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `symbol` | string | tak | — | z giełdą |
| `wskazniki` | array of string | nie | — | z kodu: `RSI, ADX, MACD.hist, Recommend.All` |
| `interwaly` | array of string | nie | — | z kodu: `1, 5, 15, 60` |

**Wyjście**

`{"symbol", "interwaly": [...], "wartosci": {<wskaźnik>: {<przedział>: <wartość>}},
"brakujace": ["<wskaźnik>|<przedział>", ...]}`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; obecność wartości zależy od TradingView.

**Przykład**

```json
{"name": "vgm_zgodnosc_pelna", "arguments": {"symbol": "FX:EURUSD", "wskazniki": ["RSI", "ADX"], "interwaly": ["15", "60"]}}
```
```
{"symbol": "FX:EURUSD", "interwaly": ["15", "60"],
 "wartosci": {"RSI": {"15": <liczba>, "60": <liczba>}, "ADX": {...}}, "brakujace": []}
```

**Błędy**

- zły przedział / pole → „niepoprawny argument — …"; `BladTV` jak w `vgm_odczyt`.

## Dane publiczne: porównania i skany

### `vgm_wiele`

Kilka instrumentów jednym zapytaniem (`dane.wiele`, `POST /forex/scan` z listą tickerów).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `symbole` | array of string | tak | — | 1–50 symboli z giełdą |
| `pola` | array of string | nie | — | z kodu: `close, open, high, low, RSI, ADX, Recommend.All` |

**Wyjście**

Lista `[{"symbol": <ticker>, <pole>: <wartość>, ...}]` w kolejności z odpowiedzi
TradingView. Instrument, którego TradingView nie zwróci, nie pojawia się na liście.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu. Kod zawsze pyta
punkt `/forex/scan`, także o akcje i kryptowaluty — czy zwraca je wszystkie,
nie zostało tu sprawdzone.

**Przykład**

```json
{"name": "vgm_wiele", "arguments": {"symbole": ["FX:EURUSD", "FX:GBPUSD"], "pola": ["close", "RSI"]}}
```
```
[{"symbol": "FX:EURUSD", "close": <liczba>, "RSI": <liczba>}, {"symbol": "FX:GBPUSD", ...}]
```

**Błędy**

- pusta lista → `{"blad": "symbole: pusta lista"}`; zły symbol → „niepoprawny argument — …";
- 403/429/HTTP → `BladTV`.

### `vgm_porownaj`

Instrumenty obok siebie, posortowane malejąco po wartości bezwzględnej `change`
(`analiza.porownaj`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `symbole` | array of string | tak | — | 1–50 symboli |
| `pola` | array of string | nie | — | z kodu: `close, change, RSI, ADX, relative_volume_10d_calc, Recommend.All` |

**Wyjście**

Lista jak w `vgm_wiele`, posortowana po `|change|` (brak `change` liczy się jak 0).
Gdy `pola` nie zawierają `change`, kolejność jest taka, jak w odpowiedzi.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; uwaga o `/forex/scan` jak w `vgm_wiele`.

**Przykład**

```json
{"name": "vgm_porownaj", "arguments": {"symbole": ["FX:EURUSD", "FX:USDJPY", "FX:AUDUSD"]}}
```
```
[{"symbol": "FX:USDJPY", "close": <liczba>, "change": <liczba>, ...}, ...]
```

**Błędy**

Jak w `vgm_wiele`.

### `vgm_skan_wyprzedane`

Instrumenty rynku z RSI poniżej progu (`analiza.skan_wyprzedane`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `rynek` | string | nie | `"forex"` | jeden z kluczy `vgm_rynki` |
| `prog` | number | nie | `30` | ±1e9 |
| `ile` | integer | nie | `20` | 1–200 |

**Wyjście**

Lista `[{"symbol", "close", "change", "RSI", "ADX", "volume"}]`, najwyżej `ile`
wierszy, posortowana przez TradingView malejąco po `change`. Wartości pól
pochodzą wprost z odpowiedzi skanera.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_skan_wyprzedane", "arguments": {"rynek": "crypto", "prog": 25, "ile": 5}}
```
```
[{"symbol": "<GIEŁDA:TICKER>", "close": <liczba>, "change": <liczba>, "RSI": <liczba>, "ADX": <liczba>, "volume": <liczba|null>}, ...]
```

**Błędy**

- nieznany rynek → „niepoprawny argument — rynek: nieznany — dozwolone: …";
- `ile` spoza 1–200 → „niepoprawny argument — ile: …"; 403/429/HTTP → `BladTV`.

### `vgm_skan_wykupione`

Instrumenty rynku z RSI powyżej progu (`analiza.skan_wykupione`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `rynek` | string | nie | `"forex"` | klucz z `vgm_rynki` |
| `prog` | number | nie | `70` | ±1e9 |
| `ile` | integer | nie | `20` | 1–200 |

**Wyjście**

Jak w `vgm_skan_wyprzedane`: `[{"symbol", "close", "change", "RSI", "ADX", "volume"}]`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_skan_wykupione", "arguments": {"rynek": "america", "prog": 75}}
```
```
[{"symbol": "NASDAQ:<TICKER>", "close": <liczba>, "RSI": <liczba>, ...}, ...]
```

**Błędy**

Jak w `vgm_skan_wyprzedane`.

### `vgm_skan_trend`

Instrumenty z ADX powyżej progu, z ADX+DI i ADX-DI (`analiza.skan_silny_trend`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `rynek` | string | nie | `"forex"` | klucz z `vgm_rynki` |
| `prog_adx` | number | nie | `30` | ±1e9 |
| `ile` | integer | nie | `20` | 1–200 |

**Wyjście**

`[{"symbol", "close", "change", "ADX", "ADX+DI", "ADX-DI", "RSI"}]`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_skan_trend", "arguments": {"prog_adx": 35, "ile": 10}}
```
```
[{"symbol": "FX:<PARA>", "ADX": <liczba>, "ADX+DI": <liczba>, "ADX-DI": <liczba>, ...}, ...]
```

**Błędy**

Jak w `vgm_skan_wyprzedane`.

### `vgm_skan_wolumen`

Instrumenty z `relative_volume_10d_calc` powyżej podanej krotności (`analiza.skan_wolumen`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `rynek` | string | nie | `"forex"` | klucz z `vgm_rynki` |
| `krotnosc` | number | nie | `2.0` | 0–1e6 |
| `ile` | integer | nie | `20` | 1–200 |

**Wyjście**

`[{"symbol", "close", "change", "volume", "relative_volume_10d_calc", "RSI"}]`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu. Na rynku `forex`
wolumen bywa pusty — czy filtr zwraca tam cokolwiek, nie zostało tu sprawdzone.

**Przykład**

```json
{"name": "vgm_skan_wolumen", "arguments": {"rynek": "poland", "krotnosc": 3}}
```
```
[{"symbol": "GPW:<TICKER>", "volume": <liczba>, "relative_volume_10d_calc": <liczba>, ...}, ...]
```

**Błędy**

Jak w `vgm_skan_wyprzedane`; `krotnosc` spoza 0–1e6 → „niepoprawny argument — krotnosc: …".

### `vgm_skan`

Dowolny filtr skanera TradingView (`analiza.skan_wlasny`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `rynek` | string | tak | `"forex"` | klucz z `vgm_rynki`; schemat ma domyślną, ale parametr jest wymagany |
| `warunki` | array of object | tak | — | 1–10 obiektów `{"left": <pole>, "operation": <op>, "right": <liczba \| pole \| lista do 20 liczb>}`; dozwolone operacje: `less, greater, equal, nequal, eless, egreater, in_range, not_in_range, above_pct, below_pct, crosses, crosses_above, crosses_below, has, has_none_of` |
| `pola` | array of string | nie | — | z kodu: `close, change, RSI, ADX, volume` |
| `ile` | integer | nie | `20` | 1–200; **kod używa 30, gdy `ile` pominięte** (schemat mówi 20) |

**Wyjście**

`[{"symbol", <pole>: <wartość>, ...}]` — kolumny z `pola`, najwyżej `ile`
wierszy, sortowanie malejąco po `change`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; które operacje
TradingView przyjmuje dla danego pola, nie zostało tu sprawdzone.

**Przykład**

```json
{"name": "vgm_skan", "arguments": {"rynek": "forex", "warunki": [{"left": "RSI", "operation": "less", "right": 30}, {"left": "ADX", "operation": "greater", "right": 25}], "pola": ["close", "RSI", "ADX"], "ile": 10}}
```
```
[{"symbol": "FX:<PARA>", "close": <liczba>, "RSI": <liczba>, "ADX": <liczba>}, ...]
```

**Błędy**

- „niepoprawny argument — warunki: oczekiwano {left, operation, right}", „… brakuje left, operation albo right", „… nieznana operacja '<op>'";
- brak `rynek` albo `warunki` → „brakuje wymaganego pola: …"; 403/429/HTTP → `BladTV`.

## Wykres (przeglądarka z CDP)

Wszystkie narzędzia tej grupy działają na **aktywnym** wykresie karty
TradingView w przeglądarce wskazanej przez `VGM_CDP_PORT`. Błędy `BladWykresu`
mają pole `podpowiedz: "sprawdź vgm_wykres_zdrowie"`.

### `vgm_wykres_zdrowie`

Czy da się sterować wykresem: port, przeglądarka, karta TradingView, API strony (`wykres.zdrowie`).

**Wejście**

Brak parametrów.

**Wyjście**

`{"port": <int|null>, "przegladarka": <bool>, "karta_tv": <bool>, "api_wykresu": <bool>,
"gotowy": <bool>}` plus, zależnie od wyniku: `"powod"` (gdy coś nie działa),
`"tytul"` (tytuł karty, do 70 znaków), `"symbol"` (gdy `gotowy`).

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu na prawdziwej
przeglądarce; ścieżka bez `VGM_CDP_PORT` sprawdzona lokalnie (bez sieci).

**Przykład**

```json
{"name": "vgm_wykres_zdrowie", "arguments": {}}
```
```
{"port": null, "przegladarka": false, "karta_tv": false, "api_wykresu": false,
 "gotowy": false, "powod": "brak zmiennej VGM_CDP_PORT — ustaw ją na port, ..."}
```

**Błędy**

Narzędzie nie zgłasza błędów warstwy — każdy problem trafia do `powod` przy `gotowy: false`.

### `vgm_wykres_karta`

Otwiera nową kartę z wykresem, gdy żadna nie jest gotowa; nic nie robi, gdy jest
(`wykres.zapewnij_karte`). Czeka do 20 s na wczytanie.

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `symbol` | string | nie | `"FX:EURUSD"` | instrument nowej karty |

**Wyjście**

- karta była: `{"bylo_gotowe": true, "symbol": <symbol>}`;
- karta otwarta: `{"bylo_gotowe": false, "otwarta": true, "id": <12 znaków>, "symbol", "sekund": 20}`;
- karta powstała, ale wykres się nie wczytał: `{"bylo_gotowe": false, "otwarta": false, "id", "powod"}`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_wykres_karta", "arguments": {"symbol": "FX:GBPUSD"}}
```
```
{"bylo_gotowe": false, "otwarta": true, "id": "<id karty>", "symbol": "FX:GBPUSD", "sekund": 20}
```

**Błędy**

- brak/zły `VGM_CDP_PORT` → `BladWykresu` z podpowiedzią;
- przeglądarka nie przyjęła `/json/new` → „nie udało się otworzyć karty (<typ>). Sprawdź, czy przeglądarka słucha na porcie <port>.".

### `vgm_wykres_stan`

Co jest na aktywnym wykresie (`wykres.stan`).

**Wejście**

Brak parametrów.

**Wyjście**

`{"symbol", "interwal", "typ_wykresu", "wskazniki": [{"id", "nazwa"}], "rysunki": [{"id", "nazwa"}]}`.
Wartości pochodzą z wewnętrznego API strony (`ch.symbol()`, `ch.resolution()`,
`ch.chartType()`, `getAllStudies()`, `getAllShapes()`); listy są puste, gdy
API rzuci wyjątek.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; klucze z API strony TradingView.

**Przykład**

```json
{"name": "vgm_wykres_stan", "arguments": {}}
```
```
{"symbol": "FX:EURUSD", "interwal": "60", "typ_wykresu": 1,
 "wskazniki": [{"id": "<id>", "nazwa": "Volume"}], "rysunki": []}
```

**Błędy**

`BladWykresu` (brak portu, brak karty, „strona nie udostępnia API wykresu", „wykres jeszcze się nie wczytał").

### `vgm_wykres_wartosci`

Bieżące wartości wszystkich wskaźników z wykresu, także własnych w Pine (`wykres.wartosci`).

**Wejście**

Brak parametrów.

**Wyjście**

Lista `[{"nazwa": <opis wskaźnika>, "wartosci": [<liczba>, ...]}]` — dla każdego
źródła z `metaInfo`, które ma ostatni słupek z wartościami. Wskaźniki bez
wartości są pomijane. Kolejność i liczba wartości zależą od wskaźnika
i od wewnętrznego modelu strony.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; klucze z modelu strony TradingView.

**Przykład**

```json
{"name": "vgm_wykres_wartosci", "arguments": {}}
```
```
[{"nazwa": "Relative Strength Index", "wartosci": [<liczba>, ...]}]
```

**Błędy**

`BladWykresu`; „brak dostępu do modelu wykresu".

### `vgm_wykres_symbol`

Zmienia instrument na wykresie bez czekania na dane (`wykres.ustaw_symbol`).
Gdy zaraz potem czytasz świece, użyj `vgm_wykres_przelacz`.

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `symbol` | string | tak | — | z giełdą |

**Wyjście**

`{"ok": true, "symbol": <symbol>}` — potwierdza wywołanie `setSymbol`, nie to, że świece już się zmieniły.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_wykres_symbol", "arguments": {"symbol": "NASDAQ:NVDA"}}
```
```
{"ok": true, "symbol": "NASDAQ:NVDA"}
```

**Błędy**

Zły symbol → „niepoprawny argument — …"; `BladWykresu`.

### `vgm_wykres_interwal`

Zmienia przedział czasu wykresu (`wykres.ustaw_interwal`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `interwal` | string | tak | — | np. `1, 5, 15, 60, 240, D, W, M` |

**Wyjście**

`{"ok": true, "interwal": <przedział>}` — potwierdza wywołanie `setResolution`, nie wczytanie świec.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_wykres_interwal", "arguments": {"interwal": "D"}}
```
```
{"ok": true, "interwal": "D"}
```

**Błędy**

Zły przedział → „niepoprawny argument — interwal: oczekiwano np. 5, 60, 240, D, W, M"; `BladWykresu`.

### `vgm_wykres_typ`

Zmienia typ wykresu (`wykres.ustaw_typ`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `typ` | integer | tak | — | 0–30; opisane: 0 słupki, 1 świece, 3 linia, 9 Heikin Ashi |

**Wyjście**

`{"ok": true, "typ": <int>}`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; które numery poza
opisanymi TradingView przyjmuje, nie zostało tu sprawdzone.

**Przykład**

```json
{"name": "vgm_wykres_typ", "arguments": {"typ": 9}}
```
```
{"ok": true, "typ": 9}
```

**Błędy**

`typ` spoza 0–30 albo niecałkowity → „niepoprawny argument — typ: …"; `BladWykresu`.

### `vgm_wykres_przelacz`

Zmienia instrument (i opcjonalnie przedział) i czeka, aż świece należą do nowego
instrumentu: porównuje ostatnie zamknięcie z ceną z publicznego punktu, a gdy
się nie zgadza — przeładowuje stronę (`wykres.przelacz`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `symbol` | string | tak | — | z giełdą |
| `interwal` | string | nie | — | pominięty = bez zmiany przedziału |

**Wyjście**

`{"symbol", "interwal", "sposob": "zmiana na miejscu" | "przeładowanie strony",
"potwierdzone": <bool>, "cena_wykresu", "cena_odniesienia", "przedzial_sprawdzony": <bool|null>,
"odstep_swiec_s": <int|null>}` oraz `"powod"`, gdy dane nie zostały potwierdzone.
`potwierdzone` wymaga zgodności ceny (tolerancja 5%) i — gdy podano `interwal` —
odstępu między świecami (tolerancja 20%). Przy przeładowaniu narzędzie trwa
do ~45 s.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_wykres_przelacz", "arguments": {"symbol": "COINBASE:BTCUSD", "interwal": "60"}}
```
```
{"symbol": "COINBASE:BTCUSD", "interwal": "60", "sposob": "zmiana na miejscu",
 "potwierdzone": true, "cena_wykresu": <liczba>, "cena_odniesienia": <liczba>,
 "przedzial_sprawdzony": true, "odstep_swiec_s": 3600}
```

**Błędy**

- zły symbol / przedział → „niepoprawny argument — …"; `BladWykresu`;
- brak ceny odniesienia nie jest błędem: `potwierdzone: false` i `powod: "brak ceny odniesienia: …"`.

### `vgm_wskaznik_dodaj`

Dodaje wskaźnik po pełnej nazwie z okna wyboru TradingView i czeka do ~14 s,
aż zacznie zwracać wartości (`wykres.dodaj_wskaznik`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `nazwa` | string | tak | — | niepusta, do 120 znaków, bez znaków sterujących (sprawdza warstwa wykresu) |

**Wyjście**

- liczy: `{"ok": true, "dodano": <nazwa>, "liczy": true}`;
- nie liczy: `{"ok": true, "dodano", "liczy": false, "wskaznikow_liczacych": <int>, "uwaga": "<wyjaśnienie>"}` — bez zalogowania TradingView liczy jeden wskaźnik naraz.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_wskaznik_dodaj", "arguments": {"nazwa": "Relative Strength Index"}}
```
```
{"ok": true, "dodano": "Relative Strength Index", "liczy": true}
```

**Błędy**

- pusta nazwa → `{"blad": "nazwa: pusty"}` (bez przedrostka „niepoprawny argument");
- „ta wersja strony nie pozwala dodać wskaźnika"; inne `BladWykresu`.

### `vgm_wskaznik_usun`

Usuwa wskaźnik po identyfikatorze z `vgm_wykres_stan` (`wykres.usun_wskaznik`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `id` | string | tak | — | do 100 znaków `A-Za-z0-9_;.-` |

**Wyjście**

`{"ok": true, "usuniete": <id>}`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_wskaznik_usun", "arguments": {"id": "Ab12Cd"}}
```
```
{"ok": true, "usuniete": "Ab12Cd"}
```

**Błędy**

- „nie ma wskaźnika o takim identyfikatorze" (`BladWykresu` z podpowiedzią);
- zły `id` → „niepoprawny argument — id: niedozwolone znaki albo zła długość".

### `vgm_wykres_swiece`

Ostatnie świece z serii wczytanej na wykresie (`wykres.swiece`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `ile` | integer | nie | `100` | 1–5000 |

**Wyjście**

`{"dostepnych": <int>, "zwrocono": <int>, "swiece": [{"czas", "otwarcie", "szczyt",
"dolek", "zamkniecie", "wolumen"}]}`. `czas` to znacznik czasu z serii wykresu
(kod odtwarzania traktuje go jako sekundy UTC); `wolumen` bywa `null`.
Świece od najstarszej do najnowszej.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_wykres_swiece", "arguments": {"ile": 3}}
```
```
{"dostepnych": <int>, "zwrocono": 3, "swiece": [{"czas": <int>, "otwarcie": <liczba>,
 "szczyt": <liczba>, "dolek": <liczba>, "zamkniecie": <liczba>, "wolumen": <liczba|null>}, ...]}
```

**Błędy**

„brak dostępu do modelu wykresu", „nie znalazłem serii świec", inne `BladWykresu`;
bardzo duże `ile` może dać „wynik za duży".

### `vgm_wykres_zrzut`

Zapisuje zrzut karty do pliku PNG (`wykres.zrzut`). Domyślnie najpierw klika
przyciski zamykania okien i wysyła Escape.

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `sciezka` | string | nie | — | względna wobec `VGM_KATALOG_ZRZUTOW` (domyślnie `<tmp>/vgm-mcp`), tylko `*.png`, bez dowiązań; pominięta = plik tymczasowy `vgm-wykres-*.png` w katalogu tymczasowym systemu |
| `zamknij_okna` | boolean | nie | `true` | — |

**Wyjście**

`{"plik": <ścieżka bezwzględna>, "bajtow": <int>, "tytul": <tytuł karty, do 70 znaków>}`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_wykres_zrzut", "arguments": {"sciezka": "eurusd.png"}}
```
```
{"plik": "<tmp>/vgm-mcp/eurusd.png", "bajtow": <int>, "tytul": "<tytuł karty>"}
```

**Błędy**

- ścieżka poza katalogiem, inne rozszerzenie, dowiązanie → `BladWykresu` z treścią walidacji (np. „sciezka: dozwolone tylko pliki .png");
- „przeglądarka nie odpowiedziała w 45s", „przeglądarka nie zwróciła obrazu".

### `vgm_swiece_statystyka`

Proste miary na świecach z wykresu (`analiza.statystyka_swiec`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `ile` | integer | nie | `200` | 1–5000 |

**Wyjście**

`{"swiec", "od", "do", "najwyzsze_zamkniecie", "najnizsze_zamkniecie",
"ostatnie_zamkniecie", "w_zakresie_proc", "sredni_zasieg", "najwiekszy_zasieg",
"swiec_wzrostowych", "udzial_wzrostowych_proc", "najwieksza_luka",
"zmiana_od_poczatku_proc"}`. `od`/`do` to `czas` pierwszej i ostatniej świecy;
`w_zakresie_proc` jest `null`, gdy wszystkie zamknięcia są równe.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_swiece_statystyka", "arguments": {"ile": 300}}
```
```
{"swiec": 300, "od": <int>, "do": <int>, "najwyzsze_zamkniecie": <liczba>, ..., "zmiana_od_poczatku_proc": <liczba>}
```

**Błędy**

- mniej niż 2 świece → `{"blad": "za mało świec do policzenia czegokolwiek"}` (bez podpowiedzi);
- `BladWykresu`.

### `vgm_swiece_zmiennosc`

Średni zasięg świecy w dwóch sąsiednich oknach i ich stosunek (`analiza.zmiennosc_swiec`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `ile` | integer | nie | `200` | 1–5000; ile świec pobrać |
| `okno` | integer | nie | `20` | 2–500; wymaga co najmniej `2 × okno` świec |

**Wyjście**

`{"okno", "swiezsze": {"sredni_zasieg", "sredni_zasieg_proc_ceny", "zakres"},
"wczesniejsze": {...}, "stosunek_zasiegow": <liczba|null>}` — `swiezsze` to ostatnie
`okno` świec, `wczesniejsze` poprzednie `okno`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_swiece_zmiennosc", "arguments": {"ile": 100, "okno": 30}}
```
```
{"okno": 30, "swiezsze": {"sredni_zasieg": <liczba>, "sredni_zasieg_proc_ceny": <liczba>, "zakres": <liczba>},
 "wczesniejsze": {...}, "stosunek_zasiegow": <liczba>}
```

**Błędy**

„potrzeba co najmniej <2×okno> świec, jest <n>"; `BladWykresu`.

### `vgm_swiece_przedzialy`

`vgm_swiece_statystyka` po kolei na kilku przedziałach; przełącza wykres i wraca
na przedział wyjściowy (`analiza.swiece_wiele_przedzialow`). Około 3,5 s na przedział.

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `przedzialy` | array of string | nie | — | do 8 przedziałów; z kodu: `15, 60, 240` |
| `ile` | integer | nie | `100` | 1–5000 |

**Wyjście**

`{"przedzial_wyjsciowy": <przedział>, "wyniki": {<przedział>: <wyjście vgm_swiece_statystyka> | {"blad": "<do 90 znaków>"}}}`.
Błąd jednego przedziału nie przerywa pozostałych.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu. Kod nie sprawdza
odstępu świec po przełączeniu (w przeciwieństwie do `vgm_wykres_przelacz`).

**Przykład**

```json
{"name": "vgm_swiece_przedzialy", "arguments": {"przedzialy": ["60", "D"], "ile": 50}}
```
```
{"przedzial_wyjsciowy": "15", "wyniki": {"60": {"swiec": 50, ...}, "D": {"swiec": 50, ...}}}
```

**Błędy**

Ponad 8 przedziałów → „niepoprawny argument — przedzialy: za dużo elementów"; `BladWykresu` przy odczycie stanu początkowego.

## Pomiar sygnałów (świece z wykresu)

Liczy na świecach **aktywnego wykresu**; instrument ustawia się wcześniej przez
`vgm_wykres_przelacz`. Wskaźniki liczone lokalnie: `RSI` (14), `Bollinger`
(położenie w kanale 20/2, 0 = dolna wstęga, 100 = górna), `ADX` (14),
`ATR_proc` (ATR 14 jako procent zamknięcia). Placebo: 50 losowań, ziarno 42,
losowane z tych samych kwintyli zmienności co wejścia sygnału (`placebo_blokowe`).

Wspólny blok statystyki (`caly_okres` itp.):
`{"wejsc", "sredni_zwrot_proc", "mediana_proc", "trafien_proc", "najlepsze", "najgorsze", "odchylenie"}`
albo `{"wejsc": 0}`. Bloki połów mają dodatkowo `"placebo", "przewaga", "z", "placebo_blokowe"`.

`BladPomiaru` (za mało świec, nieznany wskaźnik) nie jest przechwytywany
osobno — wraca jako `{"blad": "BladPomiaru: <treść>", "narzedzie"}` bez podpowiedzi.

### `vgm_zmierz_prog`

Czy przekroczenie progu przez RSI (14) cokolwiek zapowiada (`pomiar.zmierz_prog`).
Wejście na otwarciu świecy po sygnale, wynik po `po_ilu` świecach, minus spread.

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `prog` | number | nie | `30` | ±1e9 |
| `kierunek` | string | nie | `"ponizej"` | `ponizej` albo `powyzej` |
| `po_ilu` | integer | nie | `10` | 1–500 |
| `ile_swiec` | integer | nie | `0` | 0–5000; 0 = cała wczytana historia |
| `spread_proc` | number | nie | `0.02` | 0–100 |

**Wyjście**

`{"warunek": "RSI <kierunek> <prog>", "swiec", "sprawdzane_po": "<n> świecach",
"spread_odjety_proc", "caly_okres", "pierwsza_polowa", "druga_polowa",
"placebo_sredni_zwrot", "placebo_odchylenie", "placebo_blokowe",
"przewaga_nad_placebo", "z_score", "percentyl_wobec_placebo", "losowan", "wniosek"}`.
Gdy warunek nie wystąpił: `{"wejsc": 0, "uwaga": "warunek RSI … nie wystąpił ani razu"}`.
Każda świeca spełniająca warunek liczy się jako wejście (bez usuwania nakładania).

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_zmierz_prog", "arguments": {"prog": 30, "kierunek": "ponizej", "po_ilu": 10}}
```
```
{"warunek": "RSI ponizej 30", "swiec": <int>, "sprawdzane_po": "10 świecach", "spread_odjety_proc": 0.02,
 "caly_okres": {...}, "pierwsza_polowa": {...}, "druga_polowa": {...}, ..., "wniosek": "<zdanie>"}
```

**Błędy**

- mniej niż 60 świec → „BladPomiaru: za mało świec: <n>, potrzeba co najmniej 60";
- zły `kierunek` → „niepoprawny argument — kierunek: dozwolone: ponizej, powyzej"; `BladWykresu`.

### `vgm_zmierz`

To samo co `vgm_zmierz_prog` dla jednego z czterech wskaźników, z wejściami
bez nakładania (`pomiar.zmierz`). Zawsze cała wczytana historia.

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `wskaznik` | string | nie | `"RSI"` | `RSI`, `Bollinger`, `ADX`, `ATR_proc` |
| `prog` | number | nie | `30` | ±1e9 |
| `kierunek` | string | nie | `"ponizej"` | `ponizej` / `powyzej` |
| `po_ilu` | integer | nie | `10` | 1–500 |
| `spread_proc` | number | nie | `0.02` | 0–100 |

**Wyjście**

`{"warunek", "opis_wskaznika", "sygnalow_lacznie", "epizodow_bez_nakladania",
"swiec", "sprawdzane_po", "spread_odjety_proc"}` + te same klucze porównania
z placebo co w `vgm_zmierz_prog` (od `caly_okres` do `wniosek`).
Brak wejść: `{"wejsc": 0, "uwaga": "…"}`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_zmierz", "arguments": {"wskaznik": "Bollinger", "prog": 90, "kierunek": "powyzej"}}
```
```
{"warunek": "Bollinger powyzej 90", "opis_wskaznika": "położenie w kanale, ...",
 "sygnalow_lacznie": <int>, "epizodow_bez_nakladania": <int>, ..., "wniosek": "<zdanie>"}
```

**Błędy**

Jak w `vgm_zmierz_prog`; zły `wskaznik` → „niepoprawny argument — wskaznik: dozwolone: RSI, Bollinger, ADX, ATR_proc".

### `vgm_porownaj_progi`

`vgm_zmierz_prog` (RSI) na kilku progach naraz (`pomiar.porownaj_progi`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `progi` | array of number | nie | — | do 20 liczb; z kodu: `25, 30, 35, 40` |
| `kierunek` | string | nie | `"ponizej"` | `ponizej` / `powyzej` |
| `po_ilu` | integer | nie | `10` | 1–500 |
| `spread_proc` | number | nie | `0.02` | 0–100 |

**Wyjście**

`{"kierunek", "sprawdzane_po", "progi": [{"prog", "wejsc", "sredni_zwrot_proc",
"trafien_proc", "przewaga_nad_placebo", "polowy_zgodne", "dosc_wejsc"} | {"prog", "blad"}],
"przechodzi_wszystkie_warunki": [<prog>], "wniosek"}`. Próg przechodzi przy
≥20 wejściach, zgodnym znaku zwrotu w obu połowach, dodatniej przewadze
nad placebo i dodatnim zwrocie.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_porownaj_progi", "arguments": {"progi": [20, 25, 30], "kierunek": "ponizej"}}
```
```
{"kierunek": "ponizej", "sprawdzane_po": "10 świecach", "progi": [{"prog": 20, "wejsc": <int>, ...}, ...],
 "przechodzi_wszystkie_warunki": [...], "wniosek": "<zdanie>"}
```

**Błędy**

Błąd pojedynczego progu (np. za mało świec) trafia do wiersza jako `blad` (do 60 znaków); narzędzie zwraca resztę. `BladWykresu` przy pobieraniu świec trafia do wierszy tak samo.

### `vgm_przeglad_wskaznikow`

Siedem stałych warunków `vgm_zmierz` w jednym przebiegu: RSI<30, RSI>70,
Bollinger<10, Bollinger>90, ADX>30, ADX<15, ATR_proc>0.15 (`pomiar.przeglad_wskaznikow`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `po_ilu` | integer | nie | `10` | 1–500 |
| `spread_proc` | number | nie | `0.02` | 0–100 |

**Wyjście**

`{"sprawdzono": 7, "wyniki": [{"warunek", "wejsc", "zwrot_proc", "trafien_proc",
"przewaga", "wniosek"} | {"warunek", "blad"}], "przeszly": [<warunek>], "wniosek"}`.
Warunek przechodzi przy ≥20 wejściach, dodatnim zwrocie i dodatniej przewadze.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_przeglad_wskaznikow", "arguments": {"po_ilu": 20}}
```
```
{"sprawdzono": 7, "wyniki": [{"warunek": "RSI ponizej 30", "wejsc": <int>, ...}, ...],
 "przeszly": [], "wniosek": "żaden z siedmiu warunków nie dał przewagi na tych danych"}
```

**Błędy**

Błędy pojedynczych warunków trafiają do wierszy (`blad`, do 60 znaków).

### `vgm_przeglad_instrumentow`

`vgm_przeglad_wskaznikow` na kilku parach (instrument, przedział); każdą przełącza
przez `vgm_wykres_przelacz`, na koniec przywraca stan wyjściowy
(`pomiar.przeglad_instrumentow`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `instrumenty` | array of array | nie | — | do 10 par `[symbol, przedział]`; z kodu: `FX:EURUSD 60`, `FX:EURUSD D`, `COMEX:GC1! 60`, `COINBASE:BTCUSD 60` |
| `po_ilu` | integer | nie | `10` | 1–500; spread stały 0.02 (nie da się go podać) |

**Wyjście**

`{"instrumentow", "stan_przywrocony": "<symbol> <przedział>", "wyniki": {"<symbol> <przedział>":
{"sprawdzono", "przeszly", "najlepszy": {"warunek", "zwrot_proc", "wejsc", "trafien_proc"} | null}
| {"pominiete", "szczegol"} | {"blad"}}, "warunki_ktore_przeszly_gdziekolwiek": [...], "wniosek"}`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; trwa kilkanaście–kilkadziesiąt
sekund na parę i może dojść do limitu 240 s.

**Przykład**

```json
{"name": "vgm_przeglad_instrumentow", "arguments": {"instrumenty": [["FX:EURUSD", "60"], ["FX:GBPUSD", "60"]]}}
```
```
{"instrumentow": 2, "stan_przywrocony": "FX:EURUSD 15", "wyniki": {"FX:EURUSD 60": {...}, "FX:GBPUSD 60": {...}},
 "warunki_ktore_przeszly_gdziekolwiek": [], "wniosek": "<zdanie>"}
```

**Błędy**

- zła para → „niepoprawny argument — instrumenty: każda pozycja to [symbol, przedział]";
- `BladWykresu` przy odczycie stanu początkowego; błędy par trafiają do `wyniki`; „przekroczono limit 240 s".

### `vgm_sygnal_czy_trend`

Porównuje warunek, warunek odwrotny, samo trzymanie i losowe wejście
(`pomiar.czy_sygnal_czy_trend`). Dla RSI i Bollingera próg odwrotny to `100 − prog`.

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `wskaznik` | string | nie | `"Bollinger"` | `RSI`, `Bollinger`, `ADX`, `ATR_proc` |
| `prog` | number | nie | `90` | ±1e9 |
| `kierunek` | string | nie | `"powyzej"` | `ponizej` / `powyzej` |
| `po_ilu` | integer | nie | `10` | 1–500 |

**Wyjście**

`{"warunek", "warunek_odwrotny", "zwrot_warunku_proc", "zwrot_odwrotnego_proc",
"zwrot_trzymania_proc", "zwrot_losowego_proc", "nad_trzymaniem_pp",
"rozstep_warunek_odwrotny_pp", "wejsc_warunku", "ocena"}`. Liczby bywają `null`,
gdy któryś warunek nie wystąpił — wtedy `ocena` brzmi „za mało danych do rozstrzygnięcia".

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_sygnal_czy_trend", "arguments": {"wskaznik": "RSI", "prog": 30, "kierunek": "ponizej"}}
```
```
{"warunek": "RSI ponizej 30", "warunek_odwrotny": "RSI powyzej 70", "zwrot_warunku_proc": <liczba|null>, ..., "ocena": "<zdanie>"}
```

**Błędy**

„BladPomiaru: za mało świec…"; `BladWykresu`.

### `vgm_odniesienie_trzymanie`

Średni wynik wejścia na każdej świecy (od 26.) i trzymania przez `po_ilu` świec,
bez sygnału (`pomiar.odniesienie_trzymanie`). Spread stały 0.02.

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `po_ilu` | integer | nie | `10` | 1–500 |

**Wyjście**

Blok statystyki: `{"wejsc", "sredni_zwrot_proc", "mediana_proc", "trafien_proc",
"najlepsze", "najgorsze", "odchylenie"}` albo `{"wejsc": 0}`, gdy świec jest za mało
(narzędzie nie zgłasza wtedy błędu).

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_odniesienie_trzymanie", "arguments": {"po_ilu": 20}}
```
```
{"wejsc": <int>, "sredni_zwrot_proc": <liczba>, "mediana_proc": <liczba>, "trafien_proc": <liczba>,
 "najlepsze": <liczba>, "najgorsze": <liczba>, "odchylenie": <liczba>}
```

**Błędy**

`BladWykresu`.

### `vgm_jak_dlugo_trzymac`

`vgm_sygnal_czy_trend` dla kilku długości trzymania (`pomiar.jak_dlugo_trzymac`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `wskaznik` | string | nie | `"Bollinger"` | `RSI`, `Bollinger`, `ADX`, `ATR_proc` |
| `prog` | number | nie | `90` | ±1e9 |
| `kierunek` | string | nie | `"powyzej"` | `ponizej` / `powyzej` |
| `dlugosci` | array of integer | nie | — | do 20 liczb 1–500; z kodu: `3, 5, 10, 20, 40` |

**Wyjście**

`{"warunek", "dlugosci": [{"po_swiecach", "zwrot_warunku_proc", "zwrot_odwrotnego_proc",
"zwrot_trzymania_proc", "nad_trzymaniem_pp", "rozstep_pp", "wejsc", "dziala"} |
{"po_swiecach", "blad"}], "dziala_od": <int|null>, "najlepsza_dlugosc": <int|null>,
"wniosek", "uwaga"}`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_jak_dlugo_trzymac", "arguments": {"wskaznik": "Bollinger", "prog": 90, "dlugosci": [5, 10, 40]}}
```
```
{"warunek": "Bollinger powyzej 90", "dlugosci": [{"po_swiecach": 5, ...}, ...],
 "dziala_od": <int|null>, "najlepsza_dlugosc": <int|null>, "wniosek": "<zdanie>", "uwaga": "<zdanie>"}
```

**Błędy**

Błędy pojedynczych długości trafiają do wierszy (`blad`, do 60 znaków).

### `vgm_koszt_a_przewaga`

Sumaryczny wynik sygnału (transakcje bez nakładania, wejście i wyjście na
zamknięciach) wobec jednego kupna z trzymaniem, przy kilku kosztach na
transakcję (`pomiar.koszt_a_przewaga`). Zawsze cała wczytana historia.

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `wskaznik` | string | nie | `"Bollinger"` | `RSI`, `Bollinger`, `ADX`, `ATR_proc` |
| `prog` | number | nie | `90` | ±1e9 |
| `kierunek` | string | nie | `"powyzej"` | `ponizej` / `powyzej` |
| `po_ilu` | integer | nie | `40` | 1–500 |
| `koszty` | array of number | nie | — | do 20 liczb 0–100 (%); z kodu: `0.02, 0.05, 0.1, 0.2, 0.5, 1.0` |

**Wyjście**

`{"warunek", "po_swiecach", "transakcji_sygnalu", "wejsc_pominietych_bo_pozycja_otwarta",
"transakcji_trzymania": 1, "trzymanie_bez_kosztu_proc", "warianty": [{"koszt_proc",
"sygnal_suma_proc", "sygnal_srednio_proc", "trzymanie_proc", "sygnal_lepszy"}],
"dziala_do_kosztu_proc": <liczba|null>, "wniosek"}`.
Brak wejść: `{"wejsc": 0, "uwaga": "warunek nie wystąpił ani razu"}`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_koszt_a_przewaga", "arguments": {"wskaznik": "Bollinger", "prog": 90, "po_ilu": 40, "koszty": [0.02, 0.1]}}
```
```
{"warunek": "Bollinger powyzej 90", "po_swiecach": 40, "transakcji_sygnalu": <int>, ...,
 "warianty": [{"koszt_proc": 0.02, ...}, {"koszt_proc": 0.1, ...}], "dziala_do_kosztu_proc": <liczba|null>, "wniosek": "<zdanie>"}
```

**Błędy**

„BladPomiaru: za mało świec: <n>" (mniej niż 60); `BladWykresu`.

### `vgm_walk_forward`

Pomiar poza próbą: próg wybrany na pierwszych `czesc_ucz` świec (najwyższy z-score
wobec placebo, co najmniej 8 wejść), sprawdzony na pozostałych (`pomiar.walk_forward`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `wskaznik` | string | tak | — | `RSI`, `Bollinger`, `ADX`, `ATR_proc`; schemat go wymaga, choć kod ma domyślne `RSI` |
| `kierunek` | string | nie | — | `ponizej` / `powyzej`; z kodu: `ponizej` |
| `progi` | array of number | nie | — | do 20 liczb; pominięte = percentyle wskaźnika z części uczącej (10–50 dla `ponizej`, 50–90 dla `powyzej`) |
| `po_ilu` | integer | nie | `10` | 1–500 |
| `czesc_ucz` | number | nie | `0.7` | 0.5–0.9 |
| `spread_proc` | number | nie | `0.0` | 0–100 |

Kod przyjmuje też `ile_swiec` (0–5000, 0 = cała historia), choć schemat go nie wymienia.

**Wyjście**

`{"wskaznik", "kierunek", "po_ilu", "swiec", "granica", "czesc_ucz",
"uczenie": [{"prog", "wejsc", "zwrot", "przewaga", "z"}], "wybrany_prog",
"test": {"prog", "wejsc", "zwrot", "przewaga", "z"}, "wniosek"}`.
Gdy żaden próg nie dał 8 wejść na uczeniu: `{"wskaznik", "kierunek", "swiec",
"granica", "uczenie", "wniosek"}`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_walk_forward", "arguments": {"wskaznik": "RSI", "kierunek": "ponizej", "po_ilu": 10}}
```
```
{"wskaznik": "RSI", "kierunek": "ponizej", "po_ilu": 10, "swiec": <int>, "granica": <int>, "czesc_ucz": 0.7,
 "uczenie": [...], "wybrany_prog": <liczba>, "test": {...}, "wniosek": "<zdanie>"}
```

**Błędy**

- mniej niż 200 świec → „BladPomiaru: za mało świec: <n>, walk-forward wymaga co najmniej 200";
- „BladPomiaru: za mało wartości wskaźnika w części uczącej"; `czesc_ucz` spoza 0.5–0.9 → „niepoprawny argument — …".

## Sesja (zalogowane konto TradingView)

Wymagają przeglądarki z CDP i zalogowanej sesji. Błędy `BladSesji` mają
`podpowiedz: "zaloguj się na TradingView w przeglądarce z CDP"`. Błąd
przeglądarki (`BladWykresu`: brak portu, brak karty, wyjątek na stronie) wraca
jako `{"blad": "BladWykresu: <treść>", "narzedzie"}` **bez** podpowiedzi.
Zapytania HTTP idą z ciasteczkami sesji tylko do hostów TradingView; 401/403 →
„TradingView odmówił (<kod>) — sesja wygasła?", 429 → „za dużo zapytań (429) — zatrzymuję się, nie ponawiam".

### `vgm_sesja`

Czy w przeglądarce jest sesja TradingView i jaki plan (`sesja.czy_zalogowany`).

**Wejście**

Brak parametrów.

**Wyjście**

`{"zalogowany": <bool>, "sessionid": <bool>, "uzytkownik": "<3 znaki>***" | null, "plan": <tekst|null>}`.
`zalogowany` wymaga i ciasteczka `sessionid`, i obiektu użytkownika z `id` na stronie.
`plan` to `pro_plan` z obiektu strony.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; klucz `plan` zależy od obiektu strony TradingView.

**Przykład**

```json
{"name": "vgm_sesja", "arguments": {}}
```
```
{"zalogowany": true, "sessionid": true, "uzytkownik": "abc***", "plan": "<plan>"}
```

**Błędy**

„BladWykresu: …" (brak portu, brak karty); `BladSesji` „przeglądarka nie oddała ciasteczek w 20 s".

### `vgm_alerty`

Alerty cenowe z konta przez `pricealerts.tradingview.com/list_alerts` (`sesja.alerty`).

**Wejście**

Brak parametrów.

**Wyjście**

`{"ile": <int>, "alerty": [{"id", "symbol", "nazwa", "aktywny", "warunek", "interwal"}]}`.
`symbol` jest rozpakowany z formatu `={"symbol": ...}`; `nazwa` do 60 znaków.
Gdy odpowiedź nie jest listą: `{"ile": 0, "surowe": "<do 200 znaków>"}`.
Pola alertu przepisywane są z odpowiedzi TradingView (`alert_id`/`id`, `name`,
`active`, `condition.type`, `resolution`) i mogą być `null`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; klucze zależą od odpowiedzi TradingView.

**Przykład**

```json
{"name": "vgm_alerty", "arguments": {}}
```
```
{"ile": <int>, "alerty": [{"id": <id>, "symbol": "FX:EURUSD", "nazwa": "<nazwa>", "aktywny": <bool>,
 "warunek": "<typ>", "interwal": "<przedział>"}, ...]}
```

**Błędy**

„brak sesji TradingView w przeglądarce — zaloguj się"; 401/403/429/HTTP → `BladSesji`; „BladWykresu: …".

### `vgm_lista_obserwowanych`

Symbole z listy obserwowanych otwartej w prawym panelu (`sesja.lista_obserwowanych`).
Czyta z DOM strony, nie przez HTTP.

**Wejście**

Brak parametrów.

**Wyjście**

`{"nazwa": <tytuł listy, do 40 znaków | null>, "ile": <int>, "symbole": [<data-symbol-full>]}`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; zależy od klas CSS strony TradingView.

**Przykład**

```json
{"name": "vgm_lista_obserwowanych", "arguments": {}}
```
```
{"nazwa": "<nazwa listy>", "ile": <int>, "symbole": ["FX:EURUSD", ...]}
```

**Błędy**

„panel prawy nie jest otwarty" (`BladSesji` z podpowiedzią); „BladWykresu: …".

### `vgm_skrypty_pine`

Skrypty Pine zapisane na koncie (`pine-facade …/list/?filter=saved`, `sesja.skrypty_pine`).

**Wejście**

Brak parametrów.

**Wyjście**

`{"ile": <int>, "skrypty": [{"nazwa", "id", "wersja", "zmieniony"}]}` — `id` to
`scriptIdPart` do `vgm_zrodlo_pine` i `vgm_usun_pine`. Gdy odpowiedź nie jest
listą: `{"ile": 0, "surowe": "…"}`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; klucze z odpowiedzi TradingView.

**Przykład**

```json
{"name": "vgm_skrypty_pine", "arguments": {}}
```
```
{"ile": <int>, "skrypty": [{"nazwa": "<nazwa>", "id": "USER;<id>", "wersja": <wersja>, "zmieniony": <czas>}, ...]}
```

**Błędy**

Jak w `vgm_alerty`.

### `vgm_zrodlo_pine`

Kod źródłowy zapisanego skryptu (`pine-facade …/get/<id>/last`, `sesja.zrodlo_pine`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `id` | string | tak | — | `id` z `vgm_skrypty_pine` |

**Wyjście**

`{"nazwa", "kod", "wersja"}` albo `{"surowe": "<do 300 znaków>"}`, gdy odpowiedź nie jest obiektem.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; klucze z odpowiedzi TradingView.

**Przykład**

```json
{"name": "vgm_zrodlo_pine", "arguments": {"id": "USER;0123456789abcdef"}}
```
```
{"nazwa": "<nazwa>", "kod": "//@version=5\n...", "wersja": <wersja>}
```

**Błędy**

Zły `id` → „niepoprawny argument — id: …"; `BladSesji` jak w `vgm_alerty`.

### `vgm_zapisz_pine`

Zapisuje nowy skrypt Pine na koncie przez `pineEditorApi` strony (`sesja.zapisz_pine`).
Zmienia stan konta. Najpierw sprawdź kod przez `vgm_pine_sprawdz`.

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `kod` | string | tak | — | niepusty, do 200 000 znaków (sprawdza warstwa sesji) |
| `nazwa` | string | tak | — | do 100 znaków, bez `"` i `\`, bez znaków sterujących |

**Wyjście**

`{"zapisany": <bool>, "id": <scriptIdPart|null>, "zapisanych_teraz": <int>}` —
`id` to ostatni skrypt o tej nazwie na liście po zapisie.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; zależy od wewnętrznego API strony.

**Przykład**

```json
{"name": "vgm_zapisz_pine", "arguments": {"kod": "//@version=5\nindicator(\"Test\")\nplot(close)", "nazwa": "Test"}}
```
```
{"zapisany": true, "id": "USER;<id>", "zapisanych_teraz": <int>}
```

**Błędy**

- zła nazwa/kod → `{"blad": "nazwa: cudzysłów i ukośnik odwrotny niedozwolone"}` itp. (bez przedrostka „niepoprawny argument");
- wyjątek na stronie → „BladWykresu: …".

### `vgm_usun_pine`

Usuwa zapisany skrypt — nieodwracalnie (`sesja.usun_pine`). Wymaga `potwierdz: true`.

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `id` | string | tak | — | `id` z `vgm_skrypty_pine` |
| `potwierdz` | boolean | tak | — | musi być `true` |

**Wyjście**

`{"usuniety": <bool>, "zapisanych_teraz": <int>}`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; `usuniety` zgaduje sukces z wartości zwróconej przez `deleteScript`.

**Przykład**

```json
{"name": "vgm_usun_pine", "arguments": {"id": "USER;0123456789abcdef", "potwierdz": true}}
```
```
{"usuniety": true, "zapisanych_teraz": <int>}
```

**Błędy**

- `potwierdz` różne od `true` → `{"blad": "usunięcie jest nieodwracalne — dodaj potwierdz=true"}`;
- `potwierdz` nie jest bool → „niepoprawny argument — potwierdz: oczekiwano true/false"; „BladWykresu: …".

### `vgm_strategie_wbudowane`

Wbudowane skrypty TradingView, z których nazwy wybrano strategie
(`pine-facade …/list/?filter=standard`, `sesja.strategie_wbudowane`).

**Wejście**

Brak parametrów.

**Wyjście**

`{"wbudowanych": <int>, "strategii": <int>, "strategie": [{"nazwa", "id"}]}` —
filtr to podciąg „strateg" w `scriptName` albo `scriptTitle`. Gdy odpowiedź
nie jest listą: `{"ile": 0, "surowe": "…"}`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; klucze z odpowiedzi TradingView.

**Przykład**

```json
{"name": "vgm_strategie_wbudowane", "arguments": {}}
```
```
{"wbudowanych": <int>, "strategii": <int>, "strategie": [{"nazwa": "<nazwa>", "id": "STD;<id>"}, ...]}
```

**Błędy**

Jak w `vgm_alerty`.

### `vgm_tester_raport`

Otwiera Strategy Tester (`bottomWidgetBar.open('backtesting')`), czeka 5 s
i czyta tekst dolnego panelu (`sesja.tester_raport`).

**Wejście**

Brak parametrów.

**Wyjście**

`{"otwarty": <bool>, "strategie_na_wykresie": [<nazwa>], "linie": [<do 60 linii tekstu>], "ma_transakcje": <bool>}`.
`ma_transakcje` jest fałszem, gdy tekst panelu zawiera „requires trade data"
albo „even one trade" — zależy od angielskiej wersji strony.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; zależy od DOM i języka strony TradingView.

**Przykład**

```json
{"name": "vgm_tester_raport", "arguments": {}}
```
```
{"otwarty": true, "strategie_na_wykresie": ["<moja strategia>"], "linie": ["<tekst>", ...], "ma_transakcje": true}
```

**Błędy**

Wyjątek na stronie (np. brak `bottomWidgetBar`) → „BladWykresu: …".

## Układ okna (kilka wykresów)

Błędy `BladUkladu` (zły kod, indeks, symbol — sprawdzane po stronie Pythona)
wracają jako `{"blad", "narzedzie"}`. Błędy połączenia z przeglądarką i wyjątki
JavaScriptu na stronie (`BladWykresu`) mają podpowiedź `sprawdź vgm_wykres_zdrowie`.

### `vgm_uklad_stan`

Układ okna, liczba wykresów, aktywny wykres i co stoi na każdym (`uklad.stan`).
Przy kilku wykresach chwilowo przełącza aktywny, żeby odczytać każdy.

**Wejście**

Brak parametrów.

**Wyjście**

`{"uklad": <kod>, "nazwa", "wykresow": <int>, "aktywny": <int>, "paneli_w_wykresie": <int|null>,
"niezapisane_zmiany": <bool|null>, "uklad_opis": <opis z UKLADY | "nieznany">}` oraz
`"wykresy": [{"indeks", "symbol", "interwal"}]`, gdy wykresów jest więcej niż jeden.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; klucze z API strony TradingView.

**Przykład**

```json
{"name": "vgm_uklad_stan", "arguments": {}}
```
```
{"uklad": "2h", "nazwa": "<nazwa>", "wykresow": 2, "aktywny": 0, "paneli_w_wykresie": 1,
 "niezapisane_zmiany": false, "uklad_opis": "dwa obok siebie w poziomie",
 "wykresy": [{"indeks": 0, "symbol": "FX:EURUSD", "interwal": "60"}, {"indeks": 1, ...}]}
```

**Błędy**

`BladWykresu` (brak portu, brak karty, wyjątek na stronie, np. brak `api.layout`).

### `vgm_uklad_ustaw`

Dzieli okno według kodu układu (`uklad.ustaw`). Zmienia to, co widzi użytkownik.

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `kod` | string | nie | `"s"` | `s, 2h, 2v, 2-1, 3h, 3v, 4, 6, 8` |

**Wyjście**

Wyjście `vgm_uklad_stan` plus `"zgodny": <bool>` (czy układ po zmianie równa się
kodowi) i `"uwaga": "układ okna zmieniony — wróć przez vgm_uklad_ustaw z kodem s"`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_uklad_ustaw", "arguments": {"kod": "2h"}}
```
```
{"uklad": "2h", "wykresow": 2, ..., "zgodny": true, "uwaga": "układ okna zmieniony — ..."}
```

**Błędy**

Nieznany kod → `{"blad": "nieznany układ: <kod> — dostępne: s, 2h, …"}`.

### `vgm_uklad_wybierz`

Ustawia aktywny wykres w układzie, licząc od zera (`uklad.wybierz`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `indeks` | integer | nie | `0` | 0–8 i mniejszy niż liczba wykresów |

**Wyjście**

Wyjście `vgm_uklad_stan` plus `"zgodny": <bool>` (czy aktywny jest teraz ten wskazany).

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_uklad_wybierz", "arguments": {"indeks": 1}}
```
```
{"uklad": "2h", "wykresow": 2, "aktywny": 1, ..., "zgodny": true}
```

**Błędy**

„indeks <i> poza zakresem — wykresów jest <n>"; `indeks` spoza 0–8 → „niepoprawny argument — indeks: …".

### `vgm_uklad_symbol`

Ustawia instrument (i opcjonalnie przedział) na wskazanym wykresie układu;
ten wykres zostaje aktywny (`uklad.symbol_w_wykresie`). Z `interwal` używa
`vgm_wykres_przelacz`, bez niego `vgm_wykres_symbol`.

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `indeks` | integer | tak | — | 0–8 |
| `symbol` | string | tak | — | z giełdą |
| `interwal` | string | nie | — | pominięty = bez zmiany |

**Wyjście**

`{"indeks", "symbol", "interwal", "zgodny": <bool>, "uklad": <wyjście vgm_uklad_stan>}` —
`symbol`/`interwal` odczytane z wykresu po zmianie; `zgodny`, gdy ticker
(część po dwukropku) występuje w odczytanym symbolu.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_uklad_symbol", "arguments": {"indeks": 1, "symbol": "FX:GBPUSD", "interwal": "60"}}
```
```
{"indeks": 1, "symbol": "FX:GBPUSD", "interwal": "60", "zgodny": true, "uklad": {...}}
```

**Błędy**

Jak w `vgm_uklad_wybierz`; zły symbol/przedział → „niepoprawny argument — …".

## Odtwarzanie historii (replay)

Błędy `BladReplay` (sprawdzane po stronie Pythona: brak odtwarzania, zła data,
zły krok) wracają jako `{"blad", "narzedzie"}`. Błędy połączenia i wyjątki
JavaScriptu na stronie (np. brak `_replayApi`) to `BladWykresu` z podpowiedzią.

### `vgm_replay_stan`

Stan odtwarzania z `_replayApi` strony (`replay.stan`).

**Wejście**

Brak parametrów.

**Wyjście**

`{"dostepne", "trwa", "autoodtwarzanie", "gotowe_do_gry", "pasek_widoczny",
"opoznienie", "tryb", "historia_od": "<YYYY-MM-DD>"|null, "wybrana_data": "<YYYY-MM-DD HH:MM>"|null,
"pozycja": {"ilosc", "cena"}|null, "wynik", "waluta"}`, a gdy `trwa` — dodatkowo
`"stoi_na": "<YYYY-MM-DD HH:MM>"` i `"ostatnie_zamkniecie"` albo `"stoi_na": null`
z `"uwaga_swiece"`. `wybrana_data` to data startu, nie bieżąca świeca.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; klucze `pozycja`,
`wynik`, `waluta`, `tryb`, `opoznienie` przepisywane wprost z wewnętrznego API
strony — ich wartości nie zostały tu sprawdzone.

**Przykład**

```json
{"name": "vgm_replay_stan", "arguments": {}}
```
```
{"dostepne": true, "trwa": false, "autoodtwarzanie": false, "gotowe_do_gry": <bool>,
 "pasek_widoczny": false, "opoznienie": <liczba|null>, "tryb": "<tekst>",
 "historia_od": "<YYYY-MM-DD>", "wybrana_data": null, "pozycja": null, "wynik": <wartość>, "waluta": <wartość>}
```

**Błędy**

`BladWykresu` (brak portu, brak karty, wyjątek na stronie, np. brak `_replayApi`).

### `vgm_replay_start`

Cofa wykres do daty i włącza odtwarzanie; czeka do 20 s na start (`replay.start`).
Zostawia wykres w trybie odtwarzania.

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `data` | string | nie | — | `YYYY-MM-DD`, `YYYY-MM-DD HH:MM` (UTC) albo sekundy od 1970 (także liczba JSON, 0–4102444800); pominięta = pierwsza dostępna świeca |

**Wyjście**

Wyjście `vgm_replay_stan` (z `trwa: true`) plus
`"uwaga": "wykres jest w trybie odtwarzania — wyjście przez vgm_replay_stop"`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_replay_start", "arguments": {"data": "2026-09-11 13:30"}}
```
```
{"dostepne": true, "trwa": true, ..., "stoi_na": "2026-09-11 13:30", "uwaga": "wykres jest w trybie odtwarzania — ..."}
```

**Błędy**

„odtwarzanie niedostępne dla tego instrumentu lub przedziału",
„nie rozumiem daty: <data> — podaj YYYY-MM-DD albo sekundy", „data poza zakresem",
„odtwarzanie nie wystartowało w 20 s".

### `vgm_replay_krok`

Przesuwa odtwarzanie o `ile` świec (`replay.krok`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `ile` | integer | nie | `1` | 1–500 |

**Wyjście**

Wyjście `vgm_replay_stan` plus `"krokow": <int>` i `"ruszyl": <bool>` — czy czas
ostatniej świecy zmienił się po krokach.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_replay_krok", "arguments": {"ile": 4}}
```
```
{"trwa": true, ..., "stoi_na": "<YYYY-MM-DD HH:MM>", "krokow": 4, "ruszyl": true}
```

**Błędy**

„odtwarzanie nie trwa — najpierw vgm_replay_start"; `ile` spoza 1–500 → „niepoprawny argument — ile: …".

### `vgm_replay_autoplay`

Włącza lub wyłącza samoczynne przesuwanie świec, opcjonalnie ustawia opóźnienie (`replay.autoplay`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `wlacz` | boolean | nie | `true` | — |
| `opoznienie_ms` | integer | nie | — | 50–60000 ms na świecę (sprawdza warstwa odtwarzania) |

**Wyjście**

Wyjście `vgm_replay_stan` po zmianie.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; które opóźnienia
TradingView faktycznie przyjmuje, nie zostało tu sprawdzone.

**Przykład**

```json
{"name": "vgm_replay_autoplay", "arguments": {"wlacz": true, "opoznienie_ms": 300}}
```
```
{"trwa": true, "autoodtwarzanie": true, "opoznienie": 300, ...}
```

**Błędy**

„odtwarzanie nie trwa — najpierw vgm_replay_start"; „opoznienie_ms: <n> poza zakresem 50–60000";
`wlacz` nie bool → „niepoprawny argument — wlacz: oczekiwano true/false".

### `vgm_replay_stop`

Kończy odtwarzanie, wyłącza autoodtwarzanie i chowa pasek (`replay.stop`).

**Wejście**

Brak parametrów.

**Wyjście**

Wyjście `vgm_replay_stan` plus `"uwaga": "wykres wrócił do czasu rzeczywistego"`,
albo — gdy odtwarzanie nie trwało — `"uwaga": "odtwarzanie już nie trwało"`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_replay_stop", "arguments": {}}
```
```
{"dostepne": true, "trwa": false, ..., "uwaga": "wykres wrócił do czasu rzeczywistego"}
```

**Błędy**

`BladWykresu` (brak portu, brak karty, wyjątek na stronie).

## Pine Script (bez przeglądarki)

Błędy `BladPine` wracają jako `{"blad", "narzedzie"}`.

### `vgm_pine_sprawdz`

Kompiluje kod w kompilatorze TradingView (`pine-facade …/translate_light/`,
`pine.sprawdz`). Bez konta i przeglądarki.

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `kod` | string | tak | — | niepusty, do 200 000 znaków |

**Wyjście**

`{"poprawny": <bool>, "bledy": [{"linia", "kolumna", "komunikat"}]}`, przy błędach
dodatkowo `"podglad"` (linie z błędem i znacznik `^--` pod kolumną, najwyżej 10
błędów), przy ostrzeżeniach `"ostrzezenia": [<do 10 komunikatów>]`.
`linia`/`kolumna` biorą się z `start.line`/`start.column` albo `line`/`column` odpowiedzi.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; klucze błędów z odpowiedzi kompilatora TradingView.

**Przykład**

```json
{"name": "vgm_pine_sprawdz", "arguments": {"kod": "//@version=5\nindicator(\"test\")\nplot(ta.sma(clse, 20))"}}
```
```
{"poprawny": false, "bledy": [{"linia": 3, "kolumna": <int>, "komunikat": "<komunikat kompilatora>"}],
 "podglad": "   3 | plot(ta.sma(clse, 20))\n     |             ^-- <komunikat>"}
```

**Błędy**

„kod: pusty", „kod: za długi (…)", „kompilator odmówił (403|429)…",
„HTTP <kod> od kompilatora", „kompilator odrzucił zapytanie: …".

### `vgm_pine_sprawdz_plik`

`vgm_pine_sprawdz` na kodzie z pliku (`pine.sprawdz_plik`).

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `sciezka` | string | tak | — | względna wobec `VGM_KATALOG_PINE` (musi być ustawiona, bezwzględna); tylko zwykłe pliki `.pine`/`.txt` do 400 000 bajtów, UTF-8 |

**Wyjście**

Wyjście `vgm_pine_sprawdz` plus `"plik": <ścieżka bezwzględna po rozwiązaniu dowiązań>`.

Na żywym rynku: niesprawdzone przy pisaniu tego dokumentu; kształt z kodu.

**Przykład**

```json
{"name": "vgm_pine_sprawdz_plik", "arguments": {"sciezka": "moj_wskaznik.pine"}}
```
```
{"poprawny": true, "bledy": [], "plik": "/sciezka/do/VGM_KATALOG_PINE/moj_wskaznik.pine"}
```

**Błędy**

„odczyt plików wyłączony — ustaw VGM_KATALOG_PINE…", „VGM_KATALOG_PINE musi być ścieżką bezwzględną",
„sciezka: plik poza katalogiem VGM_KATALOG_PINE", „sciezka: dozwolone tylko pliki .pine i .txt",
„sciezka: nie ma takiego pliku: …", „sciezka: plik większy niż 400000 bajtów", błąd dekodowania UTF-8;
dalej jak w `vgm_pine_sprawdz`.

### `vgm_pine_szkielet`

Szkielet wskaźnika Pine v5 z prostą średnią (`pine.szkielet`). Lokalnie, bez sieci.

**Wejście**

| parametr | typ | wym. | domyślnie | uwagi |
|---|---|---|---|---|
| `nazwa` | string | nie | — | z kodu: `Nowy wskaźnik`; do 80 znaków, bez `"` i `\` |
| `na_wykresie` | boolean | nie | `true` | `overlay=true/false` |

**Wyjście**

`{"kod": "<tekst skryptu>"}`.

Na żywym rynku: nie dotyczy (szablon z kodu); to, że szkielet się kompiluje, nie zostało sprawdzone przy pisaniu tego dokumentu.

**Przykład**

```json
{"name": "vgm_pine_szkielet", "arguments": {"nazwa": "Mój wskaźnik", "na_wykresie": false}}
```
```
{"kod": "//@version=5\nindicator(\"Mój wskaźnik\", overlay=false)\n..."}
```

**Błędy**

Zła nazwa → `{"blad": "nazwa: cudzysłów i ukośnik odwrotny niedozwolone"}` itp.;
`na_wykresie` nie bool → „niepoprawny argument — na_wykresie: oczekiwano true/false".
