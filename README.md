# VGM MCP

Serwer MCP (Model Context Protocol) do TradingView. Pozwala modelowi czytać
dane rynkowe, sprawdzać kod Pine Script, sterować wykresem otwartym w przeglądarce
i mierzyć, czy dany sygnał (np. „RSI poniżej 30") cokolwiek zapowiada.

![Wilk z lupą nad wykresem](obrazy/glowna.png)

Serwer ma **63 narzędzia** o nazwach `vgm_*`. Nie wszystkie wymagają tego samego,
dlatego zaczynamy od tabeli.

| warstwa | co robi | czego potrzebuje |
|---|---|---|
| dane i analiza | odczyt pól, położenie ceny, wiele przedziałów czasu, porównania, skany rynku | tylko internetu |
| Pine Script | sprawdzanie kodu w kompilatorze TradingView, szkielet skryptu | tylko internetu |
| wykres | sterowanie kartą TradingView, świece, zrzut ekranu, odtwarzanie historii, układ okna, **pomiar sygnałów** | przeglądarka z debugowaniem (CDP) i otwartą kartą TradingView |
| sesja | alerty, zapisane skrypty Pine, lista obserwowanych, Strategy Tester | to samo co wykres, plus zalogowane konto TradingView |

Narzędzia pomiaru sygnałów liczą na świecach z wykresu, więc należą do warstwy
wykresu, mimo że nie dotykają samej strony.

---

## Wymagania

- **Python 3.12 lub nowszy.** Kod używa składni f-stringów dostępnej od 3.12
  (np. w `src/dane.py`), więc na starszym Pythonie moduł nie zaimportuje się.
- Pakiety z `requirements.txt`:
  - `mcp>=1.0.0,<2` – biblioteka serwera MCP. Górna granica jest celowa: serwer
    używa dekoratorów `list_tools`/`call_tool` z mcp 1.x, których w mcp 2.x nie ma
    (świeża instalacja bez granicy dostaje 2.x i `src/serwer.py` się nie uruchamia),
  - `websocket-client>=1.6.0` – potrzebny tylko warstwie wykresu i sesji
    (importowany dopiero przy pierwszym użyciu takiego narzędzia).
- Dostęp do internetu (publiczne punkty TradingView).
- Dla warstwy wykresu i sesji: przeglądarka na silniku Chromium uruchomiona
  z włączonym zdalnym debugowaniem (CDP) i karta z `tradingview.com`.
  Warstwa sesji dodatkowo wymaga, żeby w tej przeglądarce było zalogowane
  konto TradingView.
- Żadnych kluczy API ani tokenów. Serwer nie ma ich w konfiguracji.

---

## Instalacja

```bash
git clone https://github.com/Slavicboyyy/vgm-mcp.git
cd vgm-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Serwer uruchamia się poleceniem `python3 src/serwer.py` i rozmawia z klientem
przez standardowe wejście/wyjście (stdio). Normalnie nie uruchamiasz go ręcznie,
tylko wpisujesz do konfiguracji klienta MCP.

## Konfiguracja

### Klient MCP

Do ustawień klienta MCP dodaj serwer (ścieżki zamień na swoje; jeśli instalujesz
w wirtualnym środowisku, w `command` podaj ścieżkę do jego `python`):

```json
{
  "mcpServers": {
    "vgm": {
      "command": "/SCIEZKA/DO/vgm-mcp/.venv/bin/python",
      "args": ["/SCIEZKA/DO/vgm-mcp/src/serwer.py"],
      "env": {
        "VGM_CDP_PORT": "<PORT>",
        "VGM_KATALOG_PINE": "/SCIEZKA/DO/skryptow-pine"
      }
    }
  }
}
```

`<PORT>` zamień na port, z którym uruchamiasz przeglądarkę. Blok `env` jest
potrzebny tylko warstwom wykresu i sesji (`VGM_CDP_PORT`) oraz narzędziu
`vgm_pine_sprawdz_plik` (`VGM_KATALOG_PINE`); warstwa danych działa bez niego.

### Zmienne środowiskowe

| zmienna | do czego | gdy jej brak |
|---|---|---|
| `VGM_CDP_PORT` | port zdalnego debugowania przeglądarki, liczba 1–65535 | narzędzia wykresu i sesji zwracają błąd „brak zmiennej VGM_CDP_PORT"; `vgm_wykres_zdrowie` zwraca `"port": null` i ten powód |
| `VGM_KATALOG_PINE` | jedyny katalog, z którego `vgm_pine_sprawdz_plik` (i `vgm.py pine`) czyta pliki; ścieżka bezwzględna | odczyt plików jest wyłączony |
| `VGM_KATALOG_ZRZUTOW` | gdzie `vgm_wykres_zrzut` zapisuje pliki `*.png` | `<tmp>/vgm-mcp` |

Port nie ma wartości domyślnej i serwer go nie zgaduje: nie sprawdza po kolei
żadnych portów, łączy się tylko z `localhost:<VGM_CDP_PORT>`. Zły format portu
(np. `abc`, `0`, `70000`) daje błąd z nazwą zmiennej.

### Przeglądarka dla warstwy wykresu i sesji

Uruchom przeglądarkę Chromium z debugowaniem na wybranym porcie (flaga
`--remote-debugging-port=<PORT>`, ten sam port co w `VGM_CDP_PORT`), otwórz w niej `https://www.tradingview.com/chart/`
i (dla warstwy sesji) zaloguj się na swoje konto. Potem wywołaj `vgm_wykres_zdrowie`,
żeby sprawdzić, czy serwer widzi kartę.

Jeśli karty nie ma, `vgm_wykres_karta` otworzy nową przez przeglądarkę.

---

## Odpowiedzi i błędy

Każde narzędzie zwraca jeden blok tekstu z JSON-em (`ensure_ascii=False`, wcięcie 1).
Poniżej przy każdym narzędziu jest **kształt** odpowiedzi: nazwy kluczy z kodu,
a w miejscu wartości opis typu w nawiasach ostrych. To nie są prawdziwe notowania.

Błędy też są JSON-em, nie wyjątkiem:

```json
{"blad": "<treść>", "narzedzie": "vgm_nazwa"}
```

Narzędzia wykresu i sesji dokładają do niego pole `podpowiedz`
(odpowiednio: „sprawdź vgm_wykres_zdrowie" i „zaloguj się na TradingView
w przeglądarce z CDP"). Brak wymaganego parametru daje
`{"blad": "brakuje wymaganego pola: 'symbol'", "narzedzie": "..."}`.

Do każdego opisu narzędzia serwer dopisuje zastrzeżenie, że dane pochodzą
z publicznego punktu TradingView, a nie od brokera.

Symbol zawsze podajesz z giełdą: `FX:EURUSD`, `NASDAQ:NVDA`, `COINBASE:BTCUSD`.
Przedziały czasu: `1`, `5`, `15`, `60`, `240`, `1W`. Tyle przedziałów
zostało sprawdzonych dla danych publicznych (`vgm_pola` zwraca je w polu
`interwaly_zmierzone`).

---

## Narzędzia

Parametry oznaczone **(wym.)** są wymagane. Wartości domyślne podano po `=`.

### Odczyt (6 narzędzi)

#### `vgm_odczyt`
Wartości wybranych pól dla jednego instrumentu.
Parametry: `symbol` (wym.), `pola` – lista nazw pól (pominięta = zestaw domyślny:
cena, 12 pierwszych wskaźników i trzy oceny zbiorcze).

```json
{"symbol": "FX:EURUSD", "pola": ["close", "RSI", "ADX"]}
```
```
{ "close": <liczba>, "RSI": <liczba>, "ADX": <liczba> }
```
Klucz to nazwa pola, wartość może być `null`. Zła nazwa instrumentu daje błąd
„brak danych dla …".

#### `vgm_obraz`
Wszystkie 91 pól jednym zapytaniem, w dziewięciu grupach.
Parametry: `symbol` (wym.), `interwal` (pominięty = bieżący).

```json
{"symbol": "FX:EURUSD", "interwal": "60"}
```
```
{ "symbol": "FX:EURUSD", "interwal": "60",
  "cena": {"close": <liczba>, ...}, "wolumen": {...}, "ped": {...},
  "trend": {...}, "srednie": {...}, "zmiennosc": {...},
  "poziomy": {...}, "wynik": {...}, "ocena": {...} }
```
Pola bez wartości są pomijane w grupach. Bez `interwal` zamiast przedziału
dostajesz `"interwal": "biezacy"`.

#### `vgm_obraz_pelny`
Wszystko o instrumencie jednym wywołaniem.
Parametry: `symbol` (wym.).

```json
{"symbol": "FX:EURUSD"}
```
```
{ "symbol": "...",
  "pola": <wynik vgm_obraz>, "polozenie": <wynik vgm_polozenie>,
  "srednie": <wynik vgm_srednie>, "zgodnosc": <wynik vgm_zgodnosc_pelna>,
  "wykres": <wynik vgm_wykres_stan> lub {"niedostepny": "<powód>"},
  "wskazniki_z_wykresu": [...]   // tylko gdy wykres dostępny
}
```
Bez przeglądarki dostajesz część publiczną, a pole `wykres` mówi, że jest niedostępny.

#### `vgm_rynki`
Spis rynków przyjmowanych przez skany. Bez parametrów.

```json
{}
```
```
{ "forex": "pary walutowe", "crypto": "kryptowaluty", "coin": "kryptowaluty, inny zestaw",
  "america": "...", "poland": "...", "germany": "...", "uk": "...",
  "japan": "...", "futures": "...", "cfd": "..." }
```

#### `vgm_pola`
Spis dostępnych pól z podziałem na grupy. Bez parametrów.

```json
{}
```
```
{ "cena": [<nazwy pól>], "wolumen": [...], "ped": [...], "trend": [...],
  "srednie": [...], "zmiennosc": [...], "poziomy": [...], "wynik": [...],
  "ocena": [...], "interwaly_zmierzone": ["1","5","15","60","240","1W"] }
```
Do każdego pola można dopisać przyrostek przedziału, np. `RSI|60`.

#### `vgm_polozenie`
Gdzie stoi cena względem swoich odniesień, w procentach.
Parametry: `symbol` (wym.), `interwal`.

```json
{"symbol": "FX:EURUSD"}
```
```
{ "symbol": "...", "interwal": "biezacy", "cena": <liczba>,
  "w_kanale_bollingera_proc": <liczba|null>, "w_zakresie_rocznym_proc": <liczba|null>,
  "nad_ema20_proc": ..., "nad_ema50_proc": ..., "nad_ema200_proc": ...,
  "szerokosc_bollingera_proc": ..., "atr_proc_ceny": ... }
```

### Średnie i wiele przedziałów czasu (4)

#### `vgm_srednie`
Układ sześciu średnich wykładniczych (EMA 5, 10, 20, 50, 100, 200).
Parametry: `symbol` (wym.), `interwal`.

```json
{"symbol": "FX:EURUSD"}
```
```
{ "symbol": "...", "interwal": "biezacy",
  "srednie": {"EMA5": <liczba>, ..., "EMA200": <liczba>}, "cena": <liczba>,
  "par_w_kolejnosci_rosnacej": <int>, "par_w_kolejnosci_malejacej": <int>,
  "par_razem": <int>, "uporzadkowane_w_pelni": <true|false> }
```
Zwraca fakt o ułożeniu średnich, nie ocenę trendu.

#### `vgm_mtf`
Te same wskaźniki na kilku przedziałach jednym zapytaniem.
Parametry: `symbol` (wym.), `wskazniki` (= RSI, ADX, Recommend.All),
`interwaly` (= 5, 15, 60, 240).

```json
{"symbol": "FX:EURUSD", "wskazniki": ["RSI"], "interwaly": ["15", "60"]}
```
```
{ "RSI": {"15": <liczba|null>, "60": <liczba|null>} }
```

#### `vgm_zgodnosc`
Ile przedziałów wskazuje w tę samą stronę według RSI. Nie podejmuje decyzji
handlowej, tylko zlicza.
Parametry: `symbol` (wym.), `interwaly` (= 5, 15, 60, 240),
`prog_kupno` = 55, `prog_sprzedaz` = 45.

```json
{"symbol": "FX:EURUSD", "prog_kupno": 60, "prog_sprzedaz": 40}
```
```
{ "symbol": "...", "rsi": {"5": <liczba|null>, ...},
  "za_kupnem": ["<przedział>", ...], "za_sprzedaza": [...],
  "bez_danych": [...], "wszystkie_zgodne": <true|false> }
```

#### `vgm_zgodnosc_pelna`
Tabela wielu wskaźników na wielu przedziałach.
Parametry: `symbol` (wym.), `wskazniki` (= RSI, ADX, MACD.hist, Recommend.All),
`interwaly` (= 1, 5, 15, 60).

```json
{"symbol": "FX:EURUSD", "wskazniki": ["RSI", "ADX"], "interwaly": ["15", "60"]}
```
```
{ "symbol": "...", "interwaly": ["15","60"],
  "wartosci": {"RSI": {"15": <liczba|null>, "60": ...}, "ADX": {...}},
  "brakujace": ["RSI|15", ...] }
```

### Porównania i skany (7)

#### `vgm_wiele`
Kilka instrumentów jednym zapytaniem.
Parametry: `symbole` (wym.), `pola` (= close, open, high, low, RSI, ADX, Recommend.All).

```json
{"symbole": ["FX:EURUSD", "FX:GBPUSD"], "pola": ["close", "RSI"]}
```
```
[ {"symbol": "FX:EURUSD", "close": <liczba>, "RSI": <liczba>},
  {"symbol": "FX:GBPUSD", ...} ]
```
Zapytanie idzie zawsze do punktu `/forex/scan` (zob. [Znane ograniczenia](#znane-ograniczenia)).

#### `vgm_porownaj`
To samo co `vgm_wiele`, ale posortowane malejąco po wartości bezwzględnej pola `change`.
Parametry: `symbole` (wym.), `pola` (= close, change, RSI, ADX,
relative_volume_10d_calc, Recommend.All).

```json
{"symbole": ["FX:EURUSD", "FX:GBPUSD", "FX:USDJPY"]}
```
```
[ {"symbol": "...", "close": <liczba>, "change": <liczba>, "RSI": ..., "ADX": ...,
   "relative_volume_10d_calc": ..., "Recommend.All": ...}, ... ]
```

Cztery gotowe skany mają ten sam kształt odpowiedzi: lista wierszy
`{"symbol": ..., <kolumny>}`; różnią się warunkiem i kolumnami. Wspólne
parametry: `rynek` = forex (jeden z: forex, crypto, coin, america, poland,
germany, uk, japan, futures, cfd), `ile` = 20.

#### `vgm_skan_wyprzedane`
RSI poniżej progu. Parametry: `rynek` = forex, `prog` = 30, `ile` = 20.
Kolumny: close, change, RSI, ADX, volume.

```json
{"rynek": "forex", "prog": 30, "ile": 5}
```
```
[ {"symbol": "...", "close": <liczba>, "change": <liczba>, "RSI": <liczba>,
   "ADX": <liczba>, "volume": <liczba>}, ... ]
```

#### `vgm_skan_wykupione`
RSI powyżej progu. Parametry: `rynek` = forex, `prog` = 70, `ile` = 20. Kolumny jak wyżej.

```json
{"rynek": "america", "prog": 75}
```
```
[ {"symbol": "...", "close": ..., "change": ..., "RSI": ..., "ADX": ..., "volume": ...} ]
```

#### `vgm_skan_trend`
ADX powyżej progu. Parametry: `rynek` = forex, `prog_adx` = 30, `ile` = 20.
Kolumny: close, change, ADX, ADX+DI, ADX-DI, RSI.

```json
{"rynek": "forex", "prog_adx": 30}
```
```
[ {"symbol": "...", "close": ..., "change": ..., "ADX": ..., "ADX+DI": ..., "ADX-DI": ..., "RSI": ...} ]
```

#### `vgm_skan_wolumen`
Wolumen względny (do średniej z 10 dni) powyżej krotności. Parametry: `rynek` = forex, `krotnosc` = 2.0, `ile` = 20.
Kolumny: close, change, volume, relative_volume_10d_calc, RSI.

```json
{"rynek": "crypto", "krotnosc": 3}
```
```
[ {"symbol": "...", "close": ..., "change": ..., "volume": ..., "relative_volume_10d_calc": ..., "RSI": ...} ]
```

#### `vgm_skan`
Dowolny filtr TradingView.
Parametry: `rynek` (wym.), `warunki` (wym.) – lista obiektów
`{"left": <pole>, "operation": <operacja>, "right": <wartość>}`,
`pola` (= close, change, RSI, ADX, volume), `ile` = 30.
Operacje podane w opisie narzędzia: `less`, `greater`, `equal`, `in_range`,
`above_pct`, `below_pct`.

```json
{"rynek": "forex",
 "warunki": [{"left": "RSI", "operation": "less", "right": 30},
             {"left": "ADX", "operation": "greater", "right": 25}],
 "pola": ["close", "RSI", "ADX"], "ile": 10}
```
```
[ {"symbol": "...", "close": <liczba>, "RSI": <liczba>, "ADX": <liczba>}, ... ]
```
Wyniki są sortowane po zmianie ceny malejąco i obcięte do `ile`.

### Pine Script (3)

#### `vgm_pine_sprawdz`
Kompiluje kod w kompilatorze TradingView. Odpowiedź w około sekundę.
Parametry: `kod` (wym.).

```json
{"kod": "//@version=5\nindicator(\"test\")\nplot(ta.sma(clse, 20))"}
```
```
{ "poprawny": false,
  "bledy": [{"linia": <int>, "kolumna": <int>, "komunikat": "<tekst>"}],
  "podglad": "   3 | plot(ta.sma(clse, 20))\n     |             ^-- ...",
  "ostrzezenia": ["..."] }
```
Przy poprawnym kodzie: `{"poprawny": true, "bledy": []}` (`podglad` jest tylko przy błędach,
`ostrzezenia` tylko gdy kompilator je zgłosił). Pusty kod daje błąd z `blad`.

#### `vgm_pine_sprawdz_plik`
To samo, ale kod czytany z pliku `.pine`/`.txt` z katalogu `VGM_KATALOG_PINE`.
Bez tej zmiennej odczyt jest odrzucony. Ścieżka może być względna wobec tego
katalogu albo bezwzględna wewnątrz niego; dowiązania są rozwiązywane (liczy się
cel), czytane są tylko zwykłe pliki do 400 000 bajtów. Parametry: `sciezka` (wym.).

```json
{"sciezka": "skrypt.pine"}
```
```
{ "poprawny": true, "bledy": [], "plik": "/SCIEZKA/DO/skryptow-pine/skrypt.pine" }
```
Brak pliku daje `{"blad": "sciezka: nie ma takiego pliku: ...", "narzedzie": ...}`,
brak zmiennej — `{"blad": "odczyt plików wyłączony — ustaw VGM_KATALOG_PINE ...", ...}`.

#### `vgm_pine_szkielet`
Gotowy szkielet wskaźnika Pine v5. Parametry: `nazwa` (= „Nowy wskaźnik"),
`na_wykresie` = true (ustawia `overlay`).

```json
{"nazwa": "Moja srednia", "na_wykresie": true}
```
```
{ "kod": "//@version=5\nindicator(\"Moja srednia\", overlay=true)\n..." }
```

### Wykres (15)

Wymagają przeglądarki z CDP i otwartej karty TradingView. Wszystkie działają
na **aktywnym** wykresie. Przed użyciem wywołaj `vgm_wykres_zdrowie`.

#### `vgm_wykres_zdrowie`
Czy da się sterować wykresem. Bez parametrów.

```json
{}
```
```
{ "port": <int|null>, "przegladarka": <bool>, "karta_tv": <bool>, "api_wykresu": <bool>,
  "gotowy": <bool>, "tytul": "<tytuł karty>", "symbol": "<symbol>" }
```
Gdy się nie da, jest też `"powod": "<tekst>"`. Bez `VGM_CDP_PORT` odpowiedź ma
`"port": null` i powód z nazwą zmiennej; serwer nie próbuje wtedy żadnego portu.

#### `vgm_wykres_karta`
Otwiera kartę z wykresem, jeśli żadna nie jest otwarta. Parametry: `symbol` = FX:EURUSD.

```json
{"symbol": "FX:EURUSD"}
```
```
{ "bylo_gotowe": true, "symbol": "..." }
```
Gdy karty nie było: `{"bylo_gotowe": false, "otwarta": <bool>, "id": "<id>", "symbol": ..., "sekund": 20.0}`
(przy niepowodzeniu zamiast `symbol` jest `powod`).

#### `vgm_wykres_stan`
Co jest na wykresie. Bez parametrów.

```json
{}
```
```
{ "symbol": "<symbol>", "interwal": "<przedział>", "typ_wykresu": <int>,
  "wskazniki": [{"id": "<id>", "nazwa": "<nazwa>"}],
  "rysunki": [{"id": "<id>", "nazwa": "<nazwa>"}] }
```

#### `vgm_wykres_wartosci`
Bieżące wartości wskaźników z wykresu, także własnych (Pine). Bez parametrów.

```json
{}
```
```
[ {"nazwa": "<opis wskaźnika>", "wartosci": [<liczba>, ...]} ]
```

#### `vgm_wykres_symbol`
Zmienia instrument. Parametry: `symbol` (wym.).
Uwaga: nie czeka na dane, zob. pułapkę poniżej; do czytania świec użyj `vgm_wykres_przelacz`.

```json
{"symbol": "NASDAQ:NVDA"}
```
```
{ "ok": true, "symbol": "NASDAQ:NVDA" }
```

#### `vgm_wykres_interwal`
Zmienia przedział. Parametry: `interwal` (wym.): 1, 5, 15, 60, 240, D, W, M.

```json
{"interwal": "60"}
```
```
{ "ok": true, "interwal": "60" }
```

#### `vgm_wykres_typ`
Typ wykresu. Parametry: `typ` (wym., liczba całkowita): 0 słupki, 1 świece, 3 linia, 9 Heikin Ashi.

```json
{"typ": 1}
```
```
{ "ok": true, "typ": 1 }
```

#### `vgm_wykres_przelacz`
Zmienia instrument i czeka, aż świece naprawdę do niego należą (porównuje cenę
z publicznym punktem; gdy się nie zgadza, przeładowuje stronę).
Parametry: `symbol` (wym.), `interwal`.

```json
{"symbol": "COINBASE:BTCUSD", "interwal": "60"}
```
```
{ "symbol": "...", "interwal": "60", "sposob": "zmiana na miejscu",
  "potwierdzone": <bool>, "cena_wykresu": <liczba>, "cena_odniesienia": <liczba>,
  "przedzial_sprawdzony": <bool|null>, "odstep_swiec_s": <int|null> }
```
`sposob` to „zmiana na miejscu" albo „przeładowanie strony". Przy niepowodzeniu
dochodzi `powod`.

#### `vgm_wskaznik_dodaj`
Dodaje wskaźnik po pełnej nazwie z okna wyboru TradingView
(np. „Relative Strength Index", „Volume"). Parametry: `nazwa` (wym.).

```json
{"nazwa": "Relative Strength Index"}
```
```
{ "ok": true, "dodano": "Relative Strength Index", "liczy": true }
```
Gdy wskaźnik jest na wykresie, ale nie zwraca wartości: `"liczy": false`,
`"wskaznikow_liczacych": <int>` i `"uwaga": "<wyjaśnienie>"`.

#### `vgm_wskaznik_usun`
Usuwa wskaźnik po `id` z `vgm_wykres_stan`. Parametry: `id` (wym.).

```json
{"id": "<id z vgm_wykres_stan>"}
```
```
{ "ok": true, "usuniete": "<id>" }
```
Nieznane `id` daje błąd „nie ma wskaźnika o takim identyfikatorze".

#### `vgm_wykres_swiece`
Świece historyczne z serii wczytanej na wykresie. Parametry: `ile` = 100
(kod ogranicza do 1–5000).

```json
{"ile": 3}
```
```
{ "dostepnych": <int>, "zwrocono": 3,
  "swiece": [{"czas": <sekundy unix>, "otwarcie": <liczba>, "szczyt": <liczba>,
              "dolek": <liczba>, "zamkniecie": <liczba>, "wolumen": <liczba|null>}] }
```

#### `vgm_wykres_zrzut`
Zapisuje obraz wykresu do PNG. Parametry: `sciezka` (pominięta = plik tymczasowy),
`zamknij_okna` = true (zamyka okna zachęt przed zrzutem).

```json
{"sciezka": "/tmp/wykres.png"}
```
```
{ "plik": "/tmp/wykres.png", "bajtow": <int>, "tytul": "<tytuł karty>" }
```

#### `vgm_swiece_statystyka`
Liczby policzone na świecach z wykresu. Parametry: `ile` = 200.

```json
{"ile": 200}
```
```
{ "swiec": <int>, "od": <czas>, "do": <czas>,
  "najwyzsze_zamkniecie": ..., "najnizsze_zamkniecie": ..., "ostatnie_zamkniecie": ...,
  "w_zakresie_proc": <liczba|null>, "sredni_zasieg": ..., "najwiekszy_zasieg": ...,
  "swiec_wzrostowych": <int>, "udzial_wzrostowych_proc": ...,
  "najwieksza_luka": ..., "zmiana_od_poczatku_proc": ... }
```
Wymaga co najmniej 2 świec.

#### `vgm_swiece_zmiennosc`
Zmienność w dwóch oknach (świeższym i wcześniejszym) i ich stosunek.
Parametry: `ile` = 200, `okno` = 20 (potrzeba co najmniej `2 * okno` świec).

```json
{"ile": 200, "okno": 20}
```
```
{ "okno": 20,
  "swiezsze":     {"sredni_zasieg": ..., "sredni_zasieg_proc_ceny": ..., "zakres": ...},
  "wczesniejsze": {"sredni_zasieg": ..., "sredni_zasieg_proc_ceny": ..., "zakres": ...},
  "stosunek_zasiegow": <liczba|null> }
```

#### `vgm_swiece_przedzialy`
Statystyka świec z kilku przedziałów. Przełącza wykres na każdy przedział
i wraca na wyjściowy. Parametry: `przedzialy` (= 15, 60, 240), `ile` = 100.

```json
{"przedzialy": ["15", "60"], "ile": 100}
```
```
{ "przedzial_wyjsciowy": "<przedział>",
  "wyniki": {"15": <jak w vgm_swiece_statystyka lub {"blad": "..."}>, "60": {...}} }
```

### Pomiar sygnałów (10)

Narzędzia tej grupy liczą na świecach wczytanych na **aktywnym wykresie**
(nie przyjmują symbolu – najpierw ustaw instrument przez `vgm_wykres_przelacz`).
Sygnał jest porównywany z losowymi wejściami (placebo, 50 losowań, ziarno 42),
sprawdzany osobno w obu połowach okresu i obciążany spreadem. W większości
narzędzi wejście następuje na otwarciu świecy po sygnale (`vgm_koszt_a_przewaga`
liczy od zamknięcia świecy sygnału). Wynik zawsze zawiera zdanie `wniosek`
(lub `ocena`), także gdy sygnał nic nie wart.

Wspólne parametry: `prog`, `kierunek` (`ponizej` / `powyzej`), `po_ilu` – ile świec
po wejściu mierzymy zwrot, `spread_proc` – koszt w procentach ceny.

Blok `caly_okres`, `pierwsza_polowa`, `druga_polowa` to statystyka wejść:
`{"wejsc", "sredni_zwrot_proc", "mediana_proc", "trafien_proc", "najlepsze",
"najgorsze", "odchylenie"}`; dla połów dochodzą `placebo`, `przewaga`, `z`.
Gdy warunek nigdy nie wystąpił, narzędzia zwracają `{"wejsc": 0, "uwaga": "..."}`.

#### `vgm_zmierz_prog`
Czy przekroczenie progu przez **RSI (14)** cokolwiek zapowiada.
Parametry: `prog` = 30, `kierunek` = ponizej, `po_ilu` = 10,
`ile_swiec` = 0 (0 = cała wczytana historia), `spread_proc` = 0.02.
Wymaga co najmniej 60 świec.

```json
{"prog": 30, "kierunek": "ponizej", "po_ilu": 10}
```
```
{ "warunek": "RSI ponizej 30", "swiec": <int>, "sprawdzane_po": "10 świecach",
  "spread_odjety_proc": 0.02,
  "caly_okres": {...}, "pierwsza_polowa": {...}, "druga_polowa": {...},
  "placebo_sredni_zwrot": <liczba|null>, "placebo_odchylenie": <liczba|null>,
  "placebo_blokowe": <bool>, "przewaga_nad_placebo": <liczba|null>,
  "z_score": <liczba|null>, "percentyl_wobec_placebo": <liczba|null>,
  "losowan": <int>, "wniosek": "<zdanie>" }
```

#### `vgm_zmierz`
To samo dla jednego z czterech wskaźników: `RSI`, `Bollinger` (0 = dolna wstęga,
100 = górna), `ADX`, `ATR_proc`.
Parametry: `wskaznik` = RSI, `prog` = 30, `kierunek` = ponizej, `po_ilu` = 10,
`spread_proc` = 0.02. Zawsze używa całej wczytanej historii.

```json
{"wskaznik": "Bollinger", "prog": 90, "kierunek": "powyzej"}
```
```
{ "warunek": "Bollinger powyzej 90", "opis_wskaznika": "<opis>",
  "sygnalow_lacznie": <int>, "epizodow_bez_nakladania": <int>,
  <dalej jak w vgm_zmierz_prog, od "swiec"> }
```

#### `vgm_porownaj_progi`
Pomiar RSI na kilku progach naraz.
Parametry: `progi` (= 25, 30, 35, 40), `kierunek` = ponizej, `po_ilu` = 10,
`spread_proc` = 0.02.

```json
{"progi": [25, 30], "kierunek": "ponizej"}
```
```
{ "kierunek": "ponizej", "sprawdzane_po": "10 świecach",
  "progi": [{"prog": 25, "wejsc": <int>, "sredni_zwrot_proc": ..., "trafien_proc": ...,
             "przewaga_nad_placebo": ..., "polowy_zgodne": <bool>, "dosc_wejsc": <bool>}],
  "przechodzi_wszystkie_warunki": [<progi>], "wniosek": "<zdanie>" }
```
Wiersz z błędem ma postać `{"prog": ..., "blad": "..."}`.

#### `vgm_przeglad_wskaznikow`
Siedem ustalonych warunków (RSI <30 i >70, Bollinger <10 i >90, ADX >30 i <15,
ATR_proc >0.15) w jednym przebiegu. Parametry: `po_ilu` = 10, `spread_proc` = 0.02.

```json
{"po_ilu": 10}
```
```
{ "sprawdzono": 7,
  "wyniki": [{"warunek": "RSI ponizej 30", "wejsc": <int>, "zwrot_proc": ...,
              "trafien_proc": ..., "przewaga": ..., "wniosek": "<skrócone zdanie>"}],
  "przeszly": ["<warunek>", ...], "wniosek": "<zdanie>" }
```

#### `vgm_przeglad_instrumentow`
Ten sam przegląd na kilku instrumentach i przedziałach; przełącza wykres
z weryfikacją danych i przywraca stan wyjściowy.
Parametry: `instrumenty` – lista par `[symbol, przedział]`
(pominięta = EURUSD 60, EURUSD D, COMEX:GC1! 60, COINBASE:BTCUSD 60), `po_ilu` = 10.

```json
{"instrumenty": [["FX:EURUSD", "60"], ["FX:GBPUSD", "60"]], "po_ilu": 10}
```
```
{ "instrumentow": 2, "stan_przywrocony": "<symbol> <przedział>",
  "wyniki": {"FX:EURUSD 60": {"sprawdzono": 7, "przeszly": [...],
                              "najlepszy": {"warunek", "zwrot_proc", "wejsc", "trafien_proc"}}},
  "warunki_ktore_przeszly_gdziekolwiek": [...], "wniosek": "<zdanie>" }
```
Pozycja, której dane nie zostały potwierdzone, ma postać
`{"pominiete": "...", "szczegol": "..."}`. Trwa długo: każde przełączenie to kilka sekund.

#### `vgm_sygnal_czy_trend`
Czy warunek coś wnosi, czy tylko łapie trend: porównuje warunek, jego odwrotność,
samo trzymanie i losowe wejście.
Parametry: `wskaznik` = Bollinger, `prog` = 90, `kierunek` = powyzej, `po_ilu` = 10.

```json
{"wskaznik": "Bollinger", "prog": 90, "kierunek": "powyzej", "po_ilu": 10}
```
```
{ "warunek": "Bollinger powyzej 90", "warunek_odwrotny": "Bollinger ponizej 10",
  "zwrot_warunku_proc": ..., "zwrot_odwrotnego_proc": ..., "zwrot_trzymania_proc": ...,
  "zwrot_losowego_proc": ..., "nad_trzymaniem_pp": ..., "rozstep_warunek_odwrotny_pp": ...,
  "wejsc_warunku": <int>, "ocena": "<zdanie>" }
```

#### `vgm_odniesienie_trzymanie`
Ile daje samo trzymanie przez `po_ilu` świec, bez sygnału. Parametry: `po_ilu` = 10.

```json
{"po_ilu": 10}
```
```
{ "wejsc": <int>, "sredni_zwrot_proc": ..., "mediana_proc": ..., "trafien_proc": ...,
  "najlepsze": ..., "najgorsze": ..., "odchylenie": ... }
```

#### `vgm_jak_dlugo_trzymac`
Po ilu świecach sygnał daje najwięcej ponad samo trzymanie.
Parametry: `wskaznik` = Bollinger, `prog` = 90, `kierunek` = powyzej,
`dlugosci` (= 3, 5, 10, 20, 40).

```json
{"wskaznik": "Bollinger", "dlugosci": [5, 20]}
```
```
{ "warunek": "Bollinger powyzej 90",
  "dlugosci": [{"po_swiecach": 5, "zwrot_warunku_proc": ..., "zwrot_odwrotnego_proc": ...,
                "zwrot_trzymania_proc": ..., "nad_trzymaniem_pp": ..., "rozstep_pp": ...,
                "wejsc": <int>, "dziala": <bool>}],
  "dziala_od": <int|null>, "najlepsza_dlugosc": <int|null>,
  "wniosek": "<zdanie>", "uwaga": "<tekst>" }
```

#### `vgm_koszt_a_przewaga`
Przy jakim koszcie transakcji sygnał przestaje mieć sens (transakcje bez nakładania).
Parametry: `wskaznik` = Bollinger, `prog` = 90, `kierunek` = powyzej,
`po_ilu` = 40, `koszty` (= 0.02, 0.05, 0.1, 0.2, 0.5, 1.0; w procentach na transakcję).

```json
{"wskaznik": "Bollinger", "po_ilu": 40, "koszty": [0.05, 0.2]}
```
```
{ "warunek": "...", "po_swiecach": 40, "transakcji_sygnalu": <int>,
  "wejsc_pominietych_bo_pozycja_otwarta": <int>, "transakcji_trzymania": 1,
  "trzymanie_bez_kosztu_proc": ...,
  "warianty": [{"koszt_proc": 0.05, "sygnal_suma_proc": ..., "sygnal_srednio_proc": ...,
                "trzymanie_proc": ..., "sygnal_lepszy": <bool>}],
  "dziala_do_kosztu_proc": <liczba|null>, "wniosek": "<zdanie>" }
```

#### `vgm_walk_forward`
Jedyny pomiar poza próbą: próg wybierany na pierwszych 70% świec (najwyższy z-score
wobec placebo), sprawdzany na ostatnich 30%. Wymaga co najmniej 200 świec.
Parametry: `wskaznik` (wym.: RSI, Bollinger, ADX, ATR_proc), `kierunek`,
`progi` (pominięte = pięć progów z percentyli wskaźnika na części uczącej),
`po_ilu` = 10, `czesc_ucz` = 0.7, `spread_proc` = 0.0.

```json
{"wskaznik": "RSI", "kierunek": "ponizej", "po_ilu": 10}
```
```
{ "wskaznik": "RSI", "kierunek": "ponizej", "po_ilu": 10,
  "swiec": <int>, "granica": <int>, "czesc_ucz": 0.7,
  "uczenie": [{"prog": ..., "wejsc": <int>, "zwrot": ..., "przewaga": ..., "z": ...}],
  "wybrany_prog": <liczba>,
  "test": {"prog": ..., "wejsc": <int>, "zwrot": ..., "przewaga": ..., "z": ...},
  "wniosek": "<zdanie>" }
```
Gdy żaden próg nie dał ośmiu wejść na uczeniu, odpowiedź nie ma `wybrany_prog` ani `test`,
a `wniosek` to mówi.

### Sesja (9)

Wymagają zalogowanego konta TradingView w przeglądarce z CDP. Bez sesji zwracają
`{"blad": "...", "narzedzie": "...", "podpowiedz": "zaloguj się na TradingView w przeglądarce z CDP"}`.
Alerty i skrypty idą zwykłym HTTP z ciasteczkami z przeglądarki.

#### `vgm_sesja`
Czy jest sesja i jaki plan. Bez parametrów.

```json
{}
```
```
{ "zalogowany": <bool>, "sessionid": <bool>,
  "uzytkownik": "abc***", "plan": "<plan|null>" }
```
Nazwa użytkownika jest skrócona do trzech znaków i `***`.

#### `vgm_alerty`
Wszystkie alerty cenowe z konta. Bez parametrów.

```json
{}
```
```
{ "ile": <int>,
  "alerty": [{"id": ..., "symbol": "<symbol>", "nazwa": "<do 60 znaków>",
              "aktywny": <bool>, "warunek": ..., "interwal": ...}] }
```

#### `vgm_lista_obserwowanych`
Instrumenty z listy obserwowanych otwartej w prawym panelu wykresu. Bez parametrów.
Panel musi być otwarty.

```json
{}
```
```
{ "nazwa": "<nazwa listy|null>", "ile": <int>, "symbole": ["<symbol>", ...] }
```

#### `vgm_skrypty_pine`
Skrypty Pine zapisane na koncie. Bez parametrów.

```json
{}
```
```
{ "ile": <int>,
  "skrypty": [{"nazwa": "<do 60 znaków>", "id": "<scriptIdPart>", "wersja": ..., "zmieniony": ...}] }
```

#### `vgm_zrodlo_pine`
Kod zapisanego skryptu. Parametry: `id` (wym.) – z `vgm_skrypty_pine`.

```json
{"id": "<id z vgm_skrypty_pine>"}
```
```
{ "nazwa": "<nazwa>", "kod": "<źródło>", "wersja": ... }
```

#### `vgm_zapisz_pine`
Zapisuje **nowy** skrypt na koncie (zmienia stan konta). Przed zapisem sprawdź kod
przez `vgm_pine_sprawdz`. Parametry: `kod` (wym.), `nazwa` (wym.).

```json
{"kod": "//@version=5\nindicator(\"test\")\nplot(close)", "nazwa": "test"}
```
```
{ "zapisany": <bool>, "id": "<scriptIdPart|null>", "zapisanych_teraz": <int> }
```

#### `vgm_usun_pine`
Usuwa zapisany skrypt. **Nieodwracalne.** Parametry: `id` (wym.), `potwierdz` (wym., musi być `true`).

```json
{"id": "<id z vgm_skrypty_pine>", "potwierdz": true}
```
```
{ "usuniety": <bool>, "zapisanych_teraz": <int> }
```

#### `vgm_strategie_wbudowane`
Wbudowane skrypty TradingView, z których wybiera te o nazwie zawierającej „strateg".
Bez parametrów.

```json
{}
```
```
{ "wbudowanych": <int>, "strategii": <int>,
  "strategie": [{"nazwa": "<nazwa>", "id": "<id>"}] }
```

#### `vgm_tester_raport`
Otwiera Strategy Tester i czyta tekst raportu. Bez parametrów.
Na wykresie musi być własna strategia.

```json
{}
```
```
{ "otwarty": <bool>, "strategie_na_wykresie": ["<nazwa>"],
  "linie": ["<linia panelu>", ...],   // do 60 linii
  "ma_transakcje": <bool> }
```

### Odtwarzanie historii (5)

Wymaga karty TradingView z dostępnym trybem Replay. Wykres cofa się do daty
i idzie świeca po świecy. Po skończeniu **zawsze** wywołaj `vgm_replay_stop`,
bo inaczej wykres zostaje cofnięty w przeszłość.

Wszystkie narzędzia z tej grupy zwracają ten sam stan:

```
{ "dostepne": <bool>, "trwa": <bool>, "autoodtwarzanie": <bool>, "gotowe_do_gry": <bool>,
  "pasek_widoczny": <bool>, "opoznienie": <int|null>, "tryb": "<tekst>",
  "historia_od": "<RRRR-MM-DD|null>", "wybrana_data": "<RRRR-MM-DD GG:MM|null>",
  "pozycja": <obiekt|null>, "wynik": ..., "waluta": ...,
  "stoi_na": "<RRRR-MM-DD GG:MM>", "ostatnie_zamkniecie": <liczba> }
```

`stoi_na` i `ostatnie_zamkniecie` są tylko wtedy, gdy odtwarzanie trwa. Gdy wykres
nie ma jeszcze świec, jest `"stoi_na": null` i `uwaga_swiece`.

#### `vgm_replay_stan`
Stan odtwarzania. Bez parametrów. Sprawdź przed innymi narzędziami tej grupy.

```json
{}
```
Odpowiedź: stan jak wyżej.

#### `vgm_replay_start`
Cofa wykres do daty i włącza odtwarzanie. Parametry: `data` – `YYYY-MM-DD`,
`YYYY-MM-DD HH:MM` albo liczba sekund; pominięta = początek historii instrumentu.

```json
{"data": "2026-09-11 13:30"}
```
Odpowiedź: stan jak wyżej plus `"uwaga": "wykres jest w trybie odtwarzania — wyjście przez vgm_replay_stop"`.
Gdy odtwarzanie nie jest dostępne albo nie wystartuje w 20 s, zwraca błąd.

#### `vgm_replay_krok`
Przesuwa o `ile` świec (1–500, kod ucina wartości spoza zakresu). Parametry: `ile` = 1.

```json
{"ile": 4}
```
Odpowiedź: stan jak wyżej plus `"krokow": 4` i `"ruszyl": <bool>` (czy ostatnia świeca
się zmieniła). Bez trwającego odtwarzania zwraca błąd.

#### `vgm_replay_autoplay`
Włącza lub wyłącza samoczynne przesuwanie. Parametry: `wlacz` = true,
`opoznienie_ms` – opóźnienie na świecę w milisekundach (np. 100, 300, 1000).

```json
{"wlacz": true, "opoznienie_ms": 300}
```
Odpowiedź: stan jak wyżej.

#### `vgm_replay_stop`
Kończy odtwarzanie i wraca do czasu rzeczywistego. Bez parametrów.

```json
{}
```
Odpowiedź: stan jak wyżej plus `"uwaga"` („wykres wrócił do czasu rzeczywistego"
albo „odtwarzanie już nie trwało").

### Układ okna (4)

Kilka wykresów obok siebie. Pozostałe narzędzia wykresu działają na wykresie
aktywnym, a `vgm_uklad_wybierz` zmienia, który jest aktywny.

Wspólne pola stanu układu:

```
{ "uklad": "<kod>", "nazwa": "<nazwa układu>", "wykresow": <int>, "aktywny": <int>,
  "paneli_w_wykresie": <int|null>, "niezapisane_zmiany": <bool|null>,
  "uklad_opis": "<opis kodu>",
  "wykresy": [{"indeks": 0, "symbol": "...", "interwal": "..."}]   // gdy wykresów > 1
}
```

#### `vgm_uklad_stan`
Układ okna i to, co stoi na każdym wykresie. Bez parametrów. Przy kilku wykresach
chwilowo przełącza aktywny wykres i wraca na ten, który był.

```json
{}
```
Odpowiedź: pola stanu jak wyżej.

#### `vgm_uklad_ustaw`
Dzieli okno według kodu: `s` (jeden), `2h`, `2v`, `2-1`, `3h`, `3v`, `4`, `6`, `8`.
Parametry: `kod` = s. **Zmienia to, co widzisz** – wróć kodem `s`.

```json
{"kod": "2h"}
```
Odpowiedź: pola stanu plus `"zgodny": <bool>` i `"uwaga"`. Nieznany kod daje błąd
z listą dostępnych.

#### `vgm_uklad_wybierz`
Wybiera aktywny wykres (licząc od zera). Parametry: `indeks` = 0.

```json
{"indeks": 1}
```
Odpowiedź: pola stanu plus `"zgodny": <bool>`. Indeks poza zakresem daje błąd.

#### `vgm_uklad_symbol`
Ustawia instrument na wybranym wykresie układu. Po wywołaniu aktywny zostaje ten wykres.
Parametry: `indeks` (wym.), `symbol` (wym.), `interwal` (pominięty = bez zmiany).

```json
{"indeks": 1, "symbol": "FX:GBPUSD", "interwal": "60"}
```
```
{ "indeks": 1, "symbol": "<symbol>", "interwal": "<przedział>",
  "zgodny": <bool>, "uklad": { <pola stanu układu> } }
```

---

## Bezpieczeństwo wejścia

Argumenty narzędzi sprawdza `src/walidacja.py` zanim trafią do adresu, ścieżki albo kodu JS.
Zmienne środowiskowe:

- `VGM_KATALOG_PINE` — jedyny katalog, z którego `vgm_pine_sprawdz_plik` czyta pliki
  `*.pine`/`*.txt`; bez tej zmiennej odczyt jest odrzucony,
- `VGM_KATALOG_ZRZUTOW` — gdzie wolno zapisywać `vgm_wykres_zrzut` (domyślnie `<tmp>/vgm-mcp`), tylko `*.png`,
- `VGM_CDP_PORT` — port przeglądarki, 1–65535, bez wartości domyślnej.

Zapytania HTTP idą tylko do hostów TradingView, bez przekierowań, z limitem rozmiaru odpowiedzi.
Jedno wywołanie narzędzia ma twardy limit 240 s.

---

## Testy

Testy z katalogu `tests/` działają **bez sieci, bez przeglądarki i bez konta**:
pakiet `mcp` jest w nich podmieniany atrapą, a każda próba otwarcia połączenia
kończy test błędem. Wyjątkiem jest `tests/test_prawdziwe_mcp.py`: importuje
`src/serwer.py` w osobnym procesie z prawdziwym, zainstalowanym `mcp` i nie przejdzie
na mcp 2.x.

```bash
pip install -r requirements-dev.txt   # pytest, mypy, mcp, websocket-client
python3 -m pytest -q                   # konfiguracja w pytest.ini: testpaths = tests
python3 -m mypy                        # konfiguracja w pyproject.toml, sprawdza src/
```

Osobno są sprawdzenia, które **łączą się z żywym TradingView** (potrzebują internetu,
a część także przeglądarki):

```bash
python3 test_vgm.py      # pola, rynki, Pine, warstwa wykresu (pomija ją, gdy brak przeglądarki)
python3 src/pola.py      # odpytuje wszystkie 91 pól i mówi, które przestały działać
python3 src/dane.py      # krótki pokaz warstwy danych
python3 src/analiza.py   # krótki pokaz warstwy analizy
```

`src/pola.py` warto uruchomić, gdy któreś narzędzie zacznie zwracać puste wartości.

---

## Znane ograniczenia

**Dane**
- Dane pochodzą z publicznego punktu `scanner.tradingview.com` i są liczone po stronie
  TradingView. To nie są kwotowania brokera – do handlu użyj ceny od swojego brokera.
- Odstęp między zapytaniami to 1,2 s (dla kompilatora Pine 1,0 s). Przy odpowiedzi
  403 lub 429 narzędzie zatrzymuje się i **nie ponawia** (ponawianie grozi blokadą adresu).
- Przedziały czasu sprawdzone dla danych publicznych: 1, 5, 15, 60, 240, 1W.
  Dla przedziału dziennego pole bywa puste – wtedy wartość to `null`.
- `vgm_wiele` (a przez nią `vgm_porownaj`) wysyła zapytanie zawsze do `/forex/scan`.
  Kod nie sprawdza, czy zwraca to poprawne dane dla instrumentów z innych rynków.
- `vgm_zgodnosc` liczy zgodność tylko na RSI i niczego nie rekomenduje; progi są
  Twoim parametrem.

**Wykres i sesja**
- Warstwa wykresu korzysta z nieudokumentowanego, wewnętrznego API strony TradingView
  (`window.TradingViewApi`). Może przestać działać po aktualizacji strony.
- Bez zalogowanego konta TradingView liczy tylko jeden wskaźnik naraz. Kolejne dodane
  wskaźniki są na liście, ale ich wartości zostają puste; `vgm_wskaznik_dodaj` zgłasza
  to w polu `liczy`.
- `vgm_wykres_symbol` i `vgm_wykres_interwal` zmieniają nazwę od razu, ale świece mogą
  jeszcze należeć do poprzedniego instrumentu lub przedziału, a nic tego nie sygnalizuje.
  Przed czytaniem świec i pomiarem używaj `vgm_wykres_przelacz`, który sprawdza
  cenę i odstęp między świecami.
- Wszystkie narzędzia wykresu i pomiaru działają na wykresie aktywnym; w układzie
  wielookiennym najpierw wybierz go przez `vgm_uklad_wybierz`.
- Świeże przełączenie symbolu wczytuje zwykle kilkaset świec (w kodzie podano
  ok. 400). Pełniejsza historia pojawia się tylko w szczególnych przypadkach
  opisanych w `src/pomiar.py` (strategia z głębokim testem na wykresie).
- `vgm_replay_start` i `vgm_uklad_ustaw` zmieniają to, co widzisz w przeglądarce;
  sprzątają dopiero `vgm_replay_stop` i `vgm_uklad_ustaw` z kodem `s`.
- `vgm_lista_obserwowanych` czyta stronę, więc wymaga otwartego prawego panelu.
- `vgm_tester_raport` czyta tylko strategię własną; wbudowanych strategii nie da się
  dodać na wykres przez `createStudy`. Wyniki testera są poglądowe.
- `vgm_zapisz_pine` i `vgm_usun_pine` zmieniają konto; usunięcie jest nieodwracalne
  i wymaga `potwierdz=true`.

**Pomiar sygnałów**
- `vgm_zmierz_prog` i `vgm_porownaj_progi` mierzą wyłącznie RSI(14); pozostałe wskaźniki
  (Bollinger, ADX, ATR_proc) obsługują `vgm_zmierz`, `vgm_walk_forward`,
  `vgm_sygnal_czy_trend`, `vgm_jak_dlugo_trzymac` i `vgm_koszt_a_przewaga`.
- Minimum świec: 60 (większość pomiarów), 200 (`vgm_walk_forward`); `vgm_swiece_zmiennosc` wymaga `2 * okno`.
- Wynik z mniej niż 20 wejściami jest uznawany za niewystarczający do jakiegokolwiek
  wniosku. Liczba losowań placebo (50) i ziarno (42) są wpisane w kodzie.
- Pomiar nie jest poradą inwestycyjną: mówi, czy dany warunek wyglądał na przewagę
  na wczytanych świecach, a nie czy zadziała w przyszłości.
- Schemat `vgm_walk_forward` nie deklaruje parametru `ile_swiec`, choć kod go odczytuje.
  `vgm_zmierz` i inne narzędzia pomiaru zawsze używają całej wczytanej historii.

**Czego w serwerze nie ma**
- Wstawiania własnego kodu do edytora Pine (zapisz skrypt przez `vgm_zapisz_pine`
  i dodaj go na wykres ręcznie).
- Rysowania na wykresie, pozycji papierowych w odtwarzaniu, zapisu układu na konto.

---

## Licencja

MIT – zob. plik `LICENSE`.
