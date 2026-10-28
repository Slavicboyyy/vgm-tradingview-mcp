# VGM MCP

Serwer MCP do TradingView. Czyta rynek, steruje wykresem i sprawdza,
czy sygnał jest cokolwiek wart.

![Wilk z lupą nad wykresem](obrazy/glowna.png)

Sześćdziesiąt trzy narzędzia, dziewięćdziesiąt jeden pól danych, dziesięć rynków.

Cztery warstwy, każda o innych wymaganiach:

| warstwa | narzędzi | czego potrzebuje |
|---|---:|---|
| dane, analiza, sprawdzanie Pine | 20 | niczego: ani konta, ani przeglądarki |
| pomiar wartości sygnału | 10 | świec z wykresu |
| wykres, odtwarzanie, układ okna | 24 | otwartej karty TradingView |
| alerty, listy, zapis Pine, tester | 9 | zalogowanego konta |

---

## Po co

Większość narzędzi tego typu nie ruszy bez uruchomionej aplikacji TradingView.
Sięgają też po garść pól, zwykle sześć albo dwanaście, choć publicznie
dostępnych jest dziewięćdziesiąt jeden.

VGM bierze wszystkie dziewięćdziesiąt jeden, a warstwa danych i analizy chodzi
na serwerze bez żadnego okna. Do tego ma coś, czego nie ma nikt inny: warstwę
sprawdzającą, czy sygnał daje przewagę, czy tylko tak wygląda.

---

## Narzędzia

### Odczyt

| narzędzie | do czego | sprawdzone na |
|---|---|---|
| `vgm_odczyt` | wybrane pola dla instrumentu | FX:EURUSD, 91 pól |
| `vgm_obraz` | wszystkie 91 pól naraz, w dziewięciu grupach | FX:EURUSD |
| `vgm_pola` | spis dostępnych pól, do sprawdzenia przed zgadywaniem nazwy | tylko wywołanie |
| `vgm_rynki` | spis dziesięciu sprawdzonych rynków | tylko wywołanie |
| `vgm_obraz_pelny` | wszystko o instrumencie jednym wywołaniem | FX:EURUSD, 6 sekcji |

### Położenie ceny

| narzędzie | do czego | sprawdzone na |
|---|---|---|
| `vgm_polozenie` | miejsce ceny w kanale Bollingera, w rozpiętości rocznej, względem średnich | FX:EURUSD |
| `vgm_srednie` | układ sześciu średnich wykładniczych od 5 do 200 | FX:EURUSD |

### Wiele przedziałów czasu

| narzędzie | do czego |
|---|---|
| `vgm_mtf` | ten sam wskaźnik na kilku przedziałach, jednym zapytaniem |
| `vgm_zgodnosc` | ile przedziałów wskazuje w tę samą stronę |
| `vgm_zgodnosc_pelna` | tabela wielu wskaźników na wielu przedziałach |

### Porównania i skany

| narzędzie | do czego |
|---|---|
| `vgm_wiele` | kilka instrumentów w jednym zapytaniu |
| `vgm_porownaj` | instrumenty obok siebie, po sile ruchu |
| `vgm_skan_wyprzedane` | RSI poniżej progu |
| `vgm_skan_wykupione` | RSI powyżej progu |
| `vgm_skan_trend` | ADX powyżej progu, z kierunkiem |
| `vgm_skan_wolumen` | wolumen ponad wielokrotność średniej z dziesięciu dni |
| `vgm_skan` | dowolny filtr TradingView |

### Wykres

![Wykres z narzędziami](obrazy/wykres.png)

Instrumenty na obrazkach są wymyślone. Zrzuty pokazują układ, nie czyjeś konto.


Ta grupa wymaga otwartej karty z TradingView. Port podajesz w `VGM_CDP_PORT`.

| narzędzie | do czego | sprawdzone na |
|---|---|---|
| `vgm_wykres_zdrowie` | czy da się sterować, sprawdź przed resztą | karta z wykresem |
| `vgm_wykres_stan` | instrument, przedział, typ, wskaźniki, rysunki | BATS:AAPL, FX:GBPUSD |
| `vgm_wykres_wartosci` | bieżące wartości wskaźników z wykresu | RSI 53,16 i Volume |
| `vgm_wykres_przelacz` | zmiana instrumentu Z WERYFIKACJĄ danych | EURUSD i złoto, ceny zgodne |
| `vgm_wykres_symbol` | zmiana instrumentu | AAPL na EURUSD, potwierdzone odczytem |
| `vgm_wykres_interwal` | zmiana przedziału czasu | D na 60, potwierdzone odczytem |
| `vgm_wykres_typ` | świece, słupki, linia, Heikin Ashi | wywołanie przechodzi |
| `vgm_wskaznik_dodaj` | dodanie wskaźnika po nazwie | RSI dodany i widoczny |
| `vgm_wskaznik_usun` | usunięcie po identyfikatorze | RSI usunięty |
| `vgm_wykres_swiece` | świece historyczne z pełnym OHLCV | 300 świec GBPUSD 1h |
| `vgm_wykres_zrzut` | obraz wykresu do pliku PNG | 84 KB, wykres widoczny |
| `vgm_swiece_statystyka` | rozpiętość, zasięg świec, udział wzrostowych, luki | 200 świec GBPUSD |
| `vgm_swiece_zmiennosc` | zmienność w dwóch oknach i ich stosunek | 2 okna po 20 świec |
| `vgm_swiece_przedzialy` | statystyka świec z kilku przedziałów naraz | 15, 60 i 240 minut |

`vgm_wykres_wartosci` czyta również wskaźniki własne, napisane w Pine. Publiczne
dane ich nie znają, bo istnieją tylko na Twoim wykresie.

`vgm_wykres_swiece` bierze historię z serii, którą wykres i tak ma wczytaną. Zwykle
dostępnych jest kilkaset świec z czasem, otwarciem, szczytem, dołkiem, zamknięciem
i wolumenem. Żadne osobne źródło danych nie jest potrzebne.

`vgm_wykres_zrzut` zapisuje obraz wykresu do pliku. Model może dzięki temu wykres
obejrzeć, a nie tylko odczytać z niego liczby.


🔴 **Bez zalogowania TradingView liczy tylko jeden wskaźnik naraz.** Zmierzone:
po wyczyszczeniu wykresu pierwszy dodany zaczyna zwracać wartości, drugi i trzeci
pojawiają się na liście, ale ich serie zostają puste. `vgm_wskaznik_dodaj`
czeka na dane i w odpowiedzi mówi, czy wskaźnik faktycznie liczy.

Chcesz kilku naraz, zaloguj się. Chcesz jednego, usuń poprzedni przez
`vgm_wskaznik_usun`.
---

### Sesja

Ta grupa wymaga zalogowanego konta TradingView w przeglądarce z CDP. Sesję
sprawdzamy przez ciasteczko HttpOnly, bo z JavaScriptu strony nie widać go nigdy.
Alerty i skrypty idą zwykłym HTTP z tymi ciasteczkami, bez klikania w stronę.

| narzędzie | do czego | sprawdzone na |
|---|---|---|
| `vgm_sesja` | czy jest sesja i jaki plan | konto pro_premium |
| `vgm_alerty` | wszystkie alerty cenowe z konta | 208 alertów |
| `vgm_lista_obserwowanych` | instrumenty z otwartej listy w panelu | 29 symboli, lista Forex |
| `vgm_skrypty_pine` | skrypty Pine zapisane na koncie | 59 skryptów |
| `vgm_zrodlo_pine` | kod zapisanego skryptu | 6316 znaków |
| `vgm_zapisz_pine` | zapis nowego skryptu na konto | lista 59 → 60 → 59 po usunięciu |
| `vgm_usun_pine` | usunięcie skryptu, nieodwracalne; wymaga `potwierdz=true` | testowy usunięty |
| `vgm_strategie_wbudowane` | wbudowane strategie z identyfikatorami | 20 ze 145 |
| `vgm_tester_raport` | Strategy Tester: raport strategii z wykresu | panel otwarty, raport odczytany |

Z zalogowanym kontem znika też ograniczenie jednego wskaźnika: cztery naraz
liczyły się bez problemu.

---
### Odtwarzanie historii

Wykres cofa się do wybranej daty i idzie świeca po świecy, bez podglądania
przyszłości. Do przechodzenia strategii ręcznie albo sprawdzania, jak sygnał
wyglądał w danym dniu.

| narzędzie | do czego | sprawdzone na |
|---|---|---|
| `vgm_replay_stan` | czy dostępne, czy trwa, na której świecy stoi | EURUSD, historia od 2001-11-28 |
| `vgm_replay_start` | cofnięcie wykresu do daty | data podana i początek historii |
| `vgm_replay_krok` | przesunięcie o N świec | 4 kroki na świecach 3-minutowych = 12 minut |
| `vgm_replay_autoplay` | samoczynne przesuwanie, z prędkością | 300 ms: 6 sekund realnych = 69 minut wykresu |
| `vgm_replay_stop` | powrót do czasu rzeczywistego | pasek schowany, wykres przywrócony |

Data jako `YYYY-MM-DD`, `YYYY-MM-DD HH:MM` albo sekundy. `vgm_replay_krok`
zwraca `ruszyl`, bo API potwierdza krok także wtedy, gdy wykres stoi.

---

### Układ okna

Kilka wykresów obok siebie, każdy z własnym instrumentem i przedziałem.

| narzędzie | do czego | sprawdzone na |
|---|---|---|
| `vgm_uklad_stan` | układ, liczba wykresów, co na każdym stoi | 2v: EURUSD 3 min i GBPUSD 60 min |
| `vgm_uklad_ustaw` | podział okna: s, 2h, 2v, 2-1, 3h, 3v, 4, 6, 8 | 2h i 2v, powrót do s |
| `vgm_uklad_wybierz` | który wykres jest aktywny | indeksy 0 i 1 |
| `vgm_uklad_symbol` | instrument na wybranym wykresie | GBPUSD i USDJPY na drugim |

Pozostałe narzędzia wykresu działają na wykresie aktywnym, więc
`vgm_uklad_wybierz` jest przełącznikiem dla nich wszystkich.

---
![Cztery wykresy naraz](obrazy/uklad.png)

---

### Pine Script

Bez przeglądarki i bez konta.

| narzędzie | do czego | sprawdzone na |
|---|---|---|
| `vgm_pine_sprawdz` | kompilacja z dokładną linią i kolumną błędu | kod poprawny, jeden błąd, dwa błędy |
| `vgm_pine_sprawdz_plik` | to samo, z pliku `.pine`/`.txt` z katalogu `VGM_KATALOG_PINE` (domyślnie katalog roboczy) | tylko wywołanie |
| `vgm_pine_szkielet` | gotowy punkt wyjścia, sam się kompiluje | kompiluje się bez błędu |

Sprawdzenie trwa około sekundy i wygląda tak:

```
   3 | plot(ta.sma(clse, 20))
     |             ^-- Undeclared identifier 'clse'
```

Kolumna po prawej mówi, na czym dane narzędzie zostało uruchomione. Puste pole
znaczy, że sprawdziłem tylko, czy się wywołuje.

---

### Pomiar


![Wynik pomiaru sygnału](obrazy/pomiar.png)

Ta grupa nie liczy sygnału. Sprawdza, czy sygnał jest cokolwiek wart.

| narzędzie | do czego | sprawdzone na |
|---|---|---|
| `vgm_zmierz_prog` | czy przekroczenie progu cokolwiek zapowiada | RSI 30, 300 świec |
| `vgm_porownaj_progi` | ten sam pomiar na kilku progach naraz | pięć progów RSI |
| `vgm_walk_forward` | próg wybrany na 70% historii, sprawdzony na 30% — jedyny pomiar poza próbą; progi z percentyli wskaźnika | złoto dzienne: RSI z 2,24 na uczeniu, −0,44 poza próbą |
| `vgm_zmierz` | to samo dla czterech wskaźników | RSI, Bollinger, ADX, ATR |
| `vgm_przeglad_wskaznikow` | siedem warunków jednym przebiegiem | GBPUSD 1h, 300 świec |
| `vgm_sygnal_czy_trend` | czy warunek wnosi coś ponad sam trend | złoto, ropa, srebro |
| `vgm_odniesienie_trzymanie` | ile daje samo trzymanie bez sygnału | 265 wejść |
| `vgm_jak_dlugo_trzymac` | po ilu świecach sygnał daje najwięcej | złoto i ropa, 5 długości |
| `vgm_koszt_a_przewaga` | przy jakim koszcie sygnał traci sens | złoto i ropa, 6 poziomów |

Pięć warunków, wszystkie muszą być spełnione naraz:

**Dodatni zwrot po spreadzie.** Koszt wejścia wchodzi do rachunku.

**Przewaga nad sygnałem losowym.** Ten sam pomiar na losowych wejściach
o tej samej częstości. Placebo bywa gorsze od stratnego sygnału, więc samo
pobicie go nie wystarcza.

**Zgodność obu połów okresu.** Placebo i z-score liczone osobno dla każdej
połowy. Liczy się znak przewagi nad placebo w obu, nie sam zysk: zysk w obu
połowach może być wspólny dla całego rynku, przewaga nad losowym wejściem już nie.

**Co najmniej dwadzieścia wejść.** Trzy trafienia na trzy próby to przypadek.

**Przewaga większa niż rozrzut placebo.** Losowań jest pięćdziesiąt, z jawnym
ziarnem. Narzędzie liczy ich odchylenie i z-score prawdziwego wyniku. Poniżej
jednego odchylenia to szum, nawet gdy liczba wygląda dobrze. Losowe wejścia
biorą się tylko ze świec o zmienności z tych samych kwintyli, w których wypadły
świece sygnału: warunek „ATR powyżej progu" trafia w burzliwe świece i wobec
spokojnych wyglądałby raz lepiej, raz gorzej niż jest. Na złocie zmieniało to
z-score z −1,55 na 0,19 w jedną stronę i z 0,06 na −0,70 w drugą.

Pomiar bierze domyślnie całą historię, jaką wykres ma wczytaną. Świeże
przełączenie symbolu daje około 400 świec i nic tego nie doczytuje: ani
przewijanie, ani zakres widoku, ani otwarcie testera (sprawdzone). Pełne 2518
świec na złocie dziennym pojawiło się tylko przy strategii z głębokim testem
na wykresie. Na trzystu świecach jeden warunek wyglądał na
sygnał; na dziesięciu latach ma z-score −0,69 i wypada gorzej niż losowe wejście.

Przegląd siedmiu warunków na czterech wskaźnikach dał wynik odmowny w całości:

```
ADX poniżej 15:   +0,1687%   85,7% trafień   ale 7 wejść
RSI poniżej 30:   +0,0416%   76,5% trafień   ale 17 wejść
ADX powyżej 30:   -0,0260%   40,1% trafień   137 wejść, zwrot ujemny
```

Dwa pierwsze wyglądają świetnie i oba odpadają na liczbie wejść. Trzeci ma dość
wejść, ale traci po spreadzie. Narzędzie mówi to wprost, zamiast wybierać
najładniejszy wiersz.

Warstwa pomiaru powstała po to, żeby odsiewać sygnały, które tylko wyglądają
dobrze. Pierwszy badany warunek odpadł: na złocie dawał sześć procent tam, gdzie
zwykłe kupno z trzymaniem dawało trzydzieści.

Po drodze te same narzędzia wykryły trzy błędy w moich własnych obliczeniach,
każdy wyglądający na sukces. Pełny przebieg badania: [POMIARY.md](POMIARY.md).

---

## Pola danych

Sześćdziesiąt dwa pola, wszystkie sprawdzone na żywym rynku:

**Cena.** Otwarcie, zamknięcie, szczyt, dołek, luka, zmiana, VWAP
**Wolumen.** Bieżący, średnia dziesięciodniowa, stosunek jednego do drugiego
**Pęd.** RSI, RSI7, Stochastic K i D, Stochastic RSI K i D, CCI, Momentum, Awesome, ROC, Ultimate, Williams, przepływ pieniądza, przepływ Chaikina
**Trend.** ADX z obiema składowymi kierunkowymi, MACD z linią i histogramem, Parabolic SAR, Aroon w górę i w dół, pełny Ichimoku (bazowa, konwersji, obie wyprzedzające)
**Średnie.** SMA i EMA po siedem każda, od 5 do 200, plus VWMA i Hull
**Zmienność.** ATR, wstęgi Bollingera, siła wstęg, zmienność dzienna, tygodniowa i miesięczna, kanały Donchiana i Keltnera
**Poziomy.** Pięć systemów punktów zwrotnych (klasyczny, Fibonacciego, Woodiego, Camarilli, DeMarka) oraz szczyt i dołek z roku
**Wyniki.** Tydzień, miesiąc, trzy i sześć miesięcy, od początku roku, rok, pięć lat
**Ocena.** Zbiorcza TradingView, osobno dla średnich i oscylatorów, plus ocena siedmiu pojedynczych wskaźników

Każde z tych pól przyjmuje przyrostek z przedziałem czasu. `RSI|240` daje RSI z czterech godzin. Zmierzone przedziały: 1, 5, 15, 60, 240 minut oraz tydzień.

Dziewięćdziesiąt jeden pól razy sześć przedziałów to 546 wartości. Jedno zapytanie.

---

## Jak zacząć

```bash
pip install mcp
```

W ustawieniach klienta MCP:

```json
{
  "mcpServers": {
    "vgm": {
      "command": "python3",
      "args": ["/ścieżka/do/vgm-mcp/src/serwer.py"]
    }
  }
}
```

Sprawdzenie bez klienta MCP:

```bash
python3 test_vgm.py      # sprawdza wszystko: pola, rynki, Pine, wykres
python3 src/dane.py      # warstwa danych
python3 src/analiza.py   # warstwa analizy
python3 src/pola.py      # sprawdza, czy wszystkie 91 pól nadal działają
```

Ostatnie polecenie warto puścić, kiedy coś zacznie zwracać puste wartości. Powie,
która grupa pól przestała odpowiadać.

---

## Przykłady

```python
from src import analiza

analiza.polozenie("FX:EURUSD")
# cena 1.16211
# w kanale Bollingera: 56.7%
# w rozpiętości rocznej: 39.1%
# nad EMA200: +0.47%
# szerokość kanału: 1.79% ceny
# ATR: 0.395% ceny

analiza.zgodnosc_pelna("FX:EURUSD")
# RSI       1min 54.4 | 5min 51.8 | 15min 45.3 | 60min 51.3
# ADX       1min 29.3 | 5min 23.6 | 15min 21.7 | 60min 26.3
# MACD.hist 1min -0.0 | 5min  0.0 | 15min -0.0 | 60min -0.0

analiza.skan_silny_trend("forex", prog_adx=30)
# instrumenty z ADX ponad 30, z kierunkiem
```


## Rynki

Sprawdzone, wszystkie zwracają wyniki:

| nazwa | co obejmuje |
|---|---|
| `forex` | pary walutowe |
| `crypto`, `coin` | kryptowaluty, dwa różne zestawy |
| `america` | akcje amerykańskie |
| `poland` | GPW i NewConnect |
| `germany`, `uk`, `japan` | akcje z tych giełd |
| `futures` | kontrakty terminowe |
| `cfd` | kontrakty na różnicę |

Wszystkie 91 pól działa na każdym z tych rynków. Sprawdzone na kryptowalutach,
akcjach amerykańskich, GPW i kontraktach na złoto: za każdym razem 91 z 91.

---

## Z terminala

Te same narzędzia bez klienta MCP:

```bash
vgm odczyt FX:EURUSD              cena i wskaźniki
vgm obraz FX:EURUSD               wszystkie 91 pól
vgm polozenie FX:EURUSD           miejsce ceny względem odniesień
vgm mtf FX:EURUSD                 wskaźnik na kilku przedziałach
vgm zgodnosc FX:EURUSD            ile przedziałów mówi to samo
vgm porownaj FX:EURUSD FX:GBPUSD  instrumenty obok siebie
vgm skan trend                    przegląd rynku
vgm pine moj-wskaznik.pine        sprawdzenie kodu
vgm wykres stan                   co jest na wykresie
vgm wykres zrzut obraz.png        zapis wykresu
vgm swiece 200 --statystyka       liczby ze świec
vgm wszystko FX:EURUSD            pełny obraz jednym poleceniem
```

Każde polecenie przyjmuje `--json`, gdy wynik ma iść dalej do skryptu.

---

## Bezpieczeństwo wejścia

Argumenty narzędzi sprawdza `src/walidacja.py` zanim trafią do adresu, ścieżki albo kodu JS.
Zmienne środowiskowe:

- `VGM_KATALOG_PINE` — skąd wolno czytać pliki dla `vgm_pine_sprawdz_plik` (domyślnie katalog roboczy),
- `VGM_KATALOG_ZRZUTOW` — gdzie wolno zapisywać `vgm_wykres_zrzut` (domyślnie `<tmp>/vgm-mcp`), tylko `*.png`,
- `VGM_CDP_PORT` — port przeglądarki, 1–65535.

Zapytania HTTP idą tylko do hostów TradingView, bez przekierowań, z limitem rozmiaru odpowiedzi.
Jedno wywołanie narzędzia ma twardy limit 240 s. Testy (bez sieci): `pip install -r requirements-dev.txt && pytest`.

## Czego brakuje

| brakuje | powód, zmierzony |
|---|---|
| wstawianie własnego kodu do edytora Pine | Monaco w oknie aplikacji nie przyjmuje wejścia z CDP; `insertText`, zdarzenia klawiszy i `execCommand` sprawdzone, żadne nie działa bezpiecznie |
| zapis układu na konto | `saveChartAs` istnieje, ale w tym samym API nie ma kasowania — każdy test zostawiłby śmieć na koncie, a bez testu na żywo nic tu nie wchodzi |
| pozycje papierowe w odtwarzaniu | `buy(1)` zwraca `undefined`, `position()` zostaje pusta także przy otwartym panelu Replay Trading |
| wbudowane strategie w testerze | `createStudy` nie dodaje ich pod żadną z trzech nazw; tester czyta raport tylko własnej strategii |
| rysowanie na wykresie | wywołanie przechodzi, nic się nie pojawia |
| karty przeglądarki | TradingView nie wystawia API kart; `vgm_wykres_karta` otwiera nową kartę przez samą przeglądarkę |

Obejście dla pierwszego: zapisz skrypt na konto przez `vgm_zapisz_pine`, otwórz go
w edytorze ręcznie i dodaj na wykres przyciskiem.
---|---|
| wstawianie własnego kodu do edytora Pine | Monaco w oknie aplikacji nie przyjmuje wejścia z CDP; `insertText`, zdarzenia klawiszy i `execCommand` sprawdzone, żadne nie działa bezpiecznie |
| wbudowane strategie w testerze | `createStudy` nie dodaje ich pod żadną z trzech nazw; tester czyta raport tylko własnej strategii |
| rysowanie na wykresie | wywołanie przechodzi, nic się nie pojawia |
| `compileScript` z API strony | zwraca błąd serwera przy każdym zestawie argumentów; kompilacja działa osobną drogą przez `vgm_pine_sprawdz` |

Obejście dla pierwszego: zapisz skrypt na konto przez `vgm_zapisz_pine`, otwórz go
w edytorze ręcznie i dodaj na wykres przyciskiem.
---|---|
| wstawianie Pine na wykres | wymaga zalogowanego edytora |
| alerty | wymagają konta |
| rysowanie na wykresie | sprawdzone: wywołanie przechodzi, ale nic się nie pojawia bez sesji |
| Strategy Tester | wyniki są i tak tylko poglądowe, więc niski priorytet |

Warstwa wykresu działa bez logowania, gdy chodzi o odczyt i sterowanie. Zapisywanie
skryptów, alerty i listy obserwowanych wymagają zalogowanej sesji.

Te rzeczy są zaplanowane, ale żadnej nie ma w kodzie. Nie chcę, żeby ktoś liczył
na coś, czego nie zbudowałem.

---

## Ograniczenia

🔴 **Pułapka, na którą trzeba uważać.** Zmiana instrumentu przez
`vgm_wykres_symbol` zmienia nazwę natychmiast, ale seria świec potrafi
zostać przy poprzednim instrumencie. Wykres pokazuje wtedy jedną nazwę,
a zwraca ceny innego waloru, przy czym nic tego nie sygnalizuje.

Zmierzone: po przełączeniu na bitcoina wykres deklarował `COINBASE:BTCUSD`,
a ostatnia świeca miała 1,35206, czyli cenę funta. Statystyka policzona na
takich danych jest bezwartościowa i wygląda dokładnie tak samo jak prawdziwa.

Dlatego przed czytaniem świec używaj `vgm_wykres_przelacz`. Sprawdza
on cenę krzyżowo z publicznym punktem TradingView i, gdy trzeba, przeładowuje
stronę z symbolem wpisanym w adres.

🔴 **Druga pułapka, tego samego rodzaju.** Zmiana przedziału czasu przez
`vgm_wykres_interwal` też zmienia samą nazwę. Zmierzone: wykres pokazywał
"1D", a odstęp między świecami wynosił godzinę. Cztery różne przedziały dawały
wtedy identyczne wyniki pomiaru.

`vgm_wykres_przelacz` sprawdza więc dwie rzeczy naraz: czy cena zgadza się
z publicznym punktem i czy **odstęp między świecami odpowiada przedziałowi**.
Sama nazwa nie wystarcza w żadnym z tych dwóch przypadków.


**To nie są ceny brokera.** Dane idą z publicznego punktu TradingView i są liczone
po ich stronie. Twój broker pokaże inną cenę i inny spread. Do handlu bierz jego.

**Przedział dzienny bywa pusty.** Tak zachowuje się TradingView. Narzędzie zwraca
wtedy wartość pustą i wypisuje taki przedział osobno, w polu `bez_danych`.

**`vgm_zgodnosc` nie mówi „kupuj".** Zwraca liczby: tyle przedziałów powyżej progu,
tyle poniżej. Próg jest w parametrze, bo należy do strategii. Wpisanie go na sztywno
sugerowałoby przewagę, której nikt nie zmierzył. To najdroższy rodzaj kłamstwa w handlu.

**Odstęp między zapytaniami: 1,2 sekundy.** Wymuszony w kodzie. Przy odpowiedzi 403
albo 429 serwer staje i nie ponawia. Ponawianie przy tych kodach kończy się blokadą adresu, o czym przekonaliśmy się
na własnej skórze.

---

## Licencja

MIT. Rób, co chcesz.