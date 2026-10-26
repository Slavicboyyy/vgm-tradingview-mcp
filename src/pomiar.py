#!/usr/bin/env python3
"""VGM MCP — pomiar. Sprawdza, czy sygnał cokolwiek przewiduje.

Narzędzie, którego nie ma żaden inny serwer MCP do TradingView. Reszta pozwala
sygnał policzyć. To pozwala sprawdzić, czy jest cokolwiek wart.

Cztery zasady, każda po to, żeby nie oszukać samego siebie:

1. **Placebo.** Ten sam pomiar na sygnale losowym, o tej samej częstości.
   Jeśli prawdziwy nie bije placebo, nie ma przewagi.
2. **Podział na dwie połowy.** Wynik z jednego okresu nic nie znaczy, dopóki
   nie powtórzy się w drugim.
3. **Koszt odjęty.** Spread wchodzi do rachunku. Sygnał zarabiający mniej niż
   koszt wejścia jest stratny.
4. **Licznik wejść.** Trzy trafienia na trzy próby to nie przewaga, to przypadek.

Liczy na świecach z wykresu, więc działa na dowolnym instrumencie i przedziale,
który wykres ma wczytany.
"""
from __future__ import annotations

import random
import statistics
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


class BladPomiaru(Exception):
    """Za mało danych albo błędne ustawienia pomiaru."""


def _wynik_po(swiece: list, wejscia: list[int], po_ilu: int,
              spread_proc: float) -> dict:
    """Co się działo po każdym wejściu, licząc w procentach ceny wejścia."""
    # Sygnał liczymy z zamknięcia świecy i, ale wejść realnie można dopiero
    # na otwarciu i+1. Zmierzone: wejście po zamknięciu i zawyżało zwrot
    # o 0,38 pp (RSI<30 na złocie), bo dla powrotu do średniej to zamknięcie
    # jest lokalnym dołkiem, którego nikt nie złapie.
    zwroty = []
    for i in wejscia:
        if i + 1 + po_ilu >= len(swiece):
            continue
        wejscie = swiece[i + 1]["otwarcie"]
        wyjscie = swiece[i + 1 + po_ilu]["zamkniecie"]
        if not wejscie:
            continue
        zwrot = (wyjscie - wejscie) / wejscie * 100 - spread_proc
        zwroty.append(zwrot)

    if not zwroty:
        return {"wejsc": 0}

    dodatnie = sum(1 for z in zwroty if z > 0)
    return {
        "wejsc": len(zwroty),
        "sredni_zwrot_proc": round(statistics.mean(zwroty), 4),
        "mediana_proc": round(statistics.median(zwroty), 4),
        "trafien_proc": round(dodatnie / len(zwroty) * 100, 1),
        "najlepsze": round(max(zwroty), 4),
        "najgorsze": round(min(zwroty), 4),
        "odchylenie": round(statistics.pstdev(zwroty), 4) if len(zwroty) > 1 else 0,
    }


def _losuj_probe(swiece, wejscia, od, do, rng, kw=None):
    """Losowa próba wejść o tej samej liczności co `wejscia`, z zakresu [od, do).

    Z `kw` (kwintyle zmienności) losuje z tych samych kwintyli i w tych samych
    proporcjach, w jakich wypadły świece sygnału. Gdy w którymś kwintylu brakuje
    świec, wraca do zwykłego losowania i mówi o tym drugą wartością.
    """
    pula = list(range(max(od, 25), max(od + 1, do)))
    if not pula:
        return [], False
    n = min(len(wejscia), max(1, len(pula) - 1))
    if kw:
        wg_kw, potrzeba = {}, {}
        for i in pula:
            if kw[i] is not None:
                wg_kw.setdefault(kw[i], []).append(i)
        for i in wejscia:
            if kw[i] is not None:
                potrzeba[kw[i]] = potrzeba.get(kw[i], 0) + 1
        if potrzeba and all(len(wg_kw.get(k, [])) > c for k, c in potrzeba.items()):
            return [j for k, c in potrzeba.items() for j in rng.sample(wg_kw[k], c)], True
    return rng.sample(pula, n), False


def _kwintyle_zmiennosci(swiece):
    """Numer kwintyla ATR_proc (0-4) dla każdej świecy; None bez wartości."""
    atr = _policz("ATR_proc", swiece)
    znane = sorted(v for v in atr if v is not None)
    if len(znane) < 25:
        return [None] * len(swiece)
    progi = [znane[int(len(znane) * q / 5)] for q in (1, 2, 3, 4)]
    return [None if v is None else sum(1 for pr in progi if v >= pr) for v in atr]


def _placebo_dla(swiece, wejscia, od, do, po_ilu, spread_proc, rng, losowan,
                 blokowe=True):
    """Placebo, odchylenie i z-score dla wejść ograniczonych do zakresu świec.

    Używane osobno dla każdej połowy okresu. Zgodność ZNAKU PRZEWAGI w obu
    połowach mówi o trwałości sygnału; zgodność samego zysku mówi tylko o tym,
    że rynek rósł w obu — a to nie to samo.

    `blokowe`: placebo losowane tylko ze świec o zmienności (ATR_proc) z tych
    samych kwintyli, w których wypadły świece sygnału — w tych samych
    proporcjach. Bez tego placebo jest łatwiejsze niż sygnał: warunek
    „ATR powyżej progu" z definicji trafia w burzliwe świece, a losowanie
    z całej historii porównuje go ze spokojnymi. Ostatnia uwaga z przeglądu.
    """
    w = _wynik_po(swiece, wejscia, po_ilu, spread_proc)
    if not w.get("wejsc"):
        return {"wejsc": 0}
    kw = _kwintyle_zmiennosci(swiece) if blokowe else None
    losowe, blokowo = [], False
    for _ in range(losowan):
        prob, blokowo = _losuj_probe(swiece, wejscia, od, do - po_ilu - 1, rng, kw)
        r = _wynik_po(swiece, prob, po_ilu, spread_proc)
        if r.get("wejsc"):
            losowe.append(r["sredni_zwrot_proc"])
    if len(losowe) < 2:
        return {**w, "placebo": None, "przewaga": None, "z": None, "placebo_blokowe": blokowo}
    sr = statistics.mean(losowe)
    od_ = statistics.pstdev(losowe)
    prz = round(w["sredni_zwrot_proc"] - sr, 4)
    return {**w, "placebo": round(sr, 4), "przewaga": prz,
            "z": round(prz / od_, 2) if od_ else None, "placebo_blokowe": blokowo}


def _sprawdz_kierunek(kierunek):
    if kierunek not in ("ponizej", "powyzej"):
        raise BladPomiaru(f"nieznany kierunek: {kierunek} — dostępne: ponizej, powyzej")


def zmierz_prog(pole: str = "RSI", prog: float = 30, kierunek: str = "ponizej",
                po_ilu: int = 10, ile_swiec: int = 0,
                spread_proc: float = 0.02, losowan: int = 50, seed: int = 42) -> dict:
    """Czy przekroczenie progu przez wskaźnik cokolwiek zapowiada.

    pole:        na razie tylko "RSI" — liczony na świecach z wykresu
    prog:        wartość graniczna
    kierunek:    "ponizej" albo "powyzej"
    po_ilu:      ile świec po wejściu sprawdzamy wynik
    spread_proc: koszt wejścia w procentach ceny
    losowan:     ile powtórzeń placebo
    """
    import analiza

    _sprawdz_kierunek(kierunek)
    swiece = analiza._swiece_z_wykresu(ile_swiec)
    if len(swiece) < 60:
        raise BladPomiaru(f"za mało świec: {len(swiece)}, potrzeba co najmniej 60")

    zamkniecia = [s["zamkniecie"] for s in swiece]
    rsi = _rsi(zamkniecia, 14)

    wejscia = []
    for i in range(15, len(swiece) - po_ilu):
        w = rsi[i]
        if w is None:
            continue
        if (kierunek == "ponizej" and w < prog) or (kierunek == "powyzej" and w > prog):
            wejscia.append(i)

    if not wejscia:
        return {"wejsc": 0,
                "uwaga": f"warunek {pole} {kierunek} {prog} nie wystąpił ani razu"}

    polowa = len(swiece) // 2
    prawdziwy = _wynik_po(swiece, wejscia, po_ilu, spread_proc)
    rng_pol = random.Random(seed + 1)
    pierwsza = _placebo_dla(swiece, [i for i in wejscia if i < polowa], 0, polowa,
                            po_ilu, spread_proc, rng_pol, losowan)
    druga = _placebo_dla(swiece, [i for i in wejscia if i >= polowa], polowa, len(swiece),
                         po_ilu, spread_proc, rng_pol, losowan)

    # placebo: tyle samo wejść, ale w losowych miejscach
    # seed jawny: bez niego dwa uruchomienia dawały różne placebo i różne wnioski
    rng = random.Random(seed)
    kw = _kwintyle_zmiennosci(swiece)
    losowe, blokowo = [], False
    for _ in range(losowan):
        prob, blokowo = _losuj_probe(swiece, wejscia, 15, len(swiece) - po_ilu, rng, kw)
        w = _wynik_po(swiece, prob, po_ilu, spread_proc)
        if w.get("wejsc"):
            losowe.append(w["sredni_zwrot_proc"])

    placebo = round(statistics.mean(losowe), 4) if losowe else None
    przewaga = (round(prawdziwy["sredni_zwrot_proc"] - placebo, 4)
                if placebo is not None and prawdziwy.get("wejsc") else None)

    # Miara niepewności: sama przewaga nad średnią placebo nic nie mówi, gdy
    # losowania rozrzucają się szerzej niż ta przewaga. z-score pokazuje,
    # ile odchyleń placebo dzieli prawdziwy wynik od losowego. Poniżej 1
    # to szum; percentyl mówi, jaka część losowań była gorsza od prawdziwego.
    odch_placebo = round(statistics.pstdev(losowe), 4) if len(losowe) > 1 else None
    z = None
    percentyl = None
    if odch_placebo and prawdziwy.get("wejsc"):
        z = round((prawdziwy["sredni_zwrot_proc"] - placebo) / odch_placebo, 2)
        percentyl = round(sum(1 for x in losowe if x < prawdziwy["sredni_zwrot_proc"])
                          / len(losowe) * 100, 1)

    return {
        "warunek": f"{pole} {kierunek} {prog}",
        "swiec": len(swiece),
        "sprawdzane_po": f"{po_ilu} świecach",
        "spread_odjety_proc": spread_proc,
        "caly_okres": prawdziwy,
        "pierwsza_polowa": pierwsza,
        "druga_polowa": druga,
        "placebo_sredni_zwrot": placebo,
        "placebo_odchylenie": odch_placebo,
        "placebo_blokowe": blokowo,
        "przewaga_nad_placebo": przewaga,
        "z_score": z,
        "percentyl_wobec_placebo": percentyl,
        "losowan": len(losowe),
        "wniosek": _wniosek(prawdziwy, placebo, przewaga, pierwsza, druga, z),
    }


def _wniosek(prawdziwy, placebo, przewaga, pierwsza, druga, z=None) -> str:
    """Jedno zdanie o tym, co z pomiaru wynika. Bez upiększania."""
    if not prawdziwy.get("wejsc"):
        return "brak wejść — nie ma czego mierzyć"
    if prawdziwy["wejsc"] < 20:
        return (f"tylko {prawdziwy['wejsc']} wejść — za mało, żeby cokolwiek "
                "twierdzić; potrzeba co najmniej dwudziestu")
    if przewaga is None:
        return "placebo nie policzone — wynik nieporównywalny"
    if przewaga <= 0:
        return (f"sygnał NIE bije losowego wejścia (różnica {przewaga}%) — "
                "nie ma przewagi")
    if z is not None and abs(z) < 1.0:
        return (f"przewaga {przewaga}% mieści się w rozrzucie placebo "
                f"(z-score {z}) — to szum, nie sygnał")
    if prawdziwy["sredni_zwrot_proc"] <= 0:
        # bicie placebo nie wystarcza: placebo bywa jeszcze gorsze, a stratny
        # sygnał zostaje stratny niezależnie od tego, z czym go porównamy
        return (f"sygnał bije placebo o {przewaga}%, ale sam traci "
                f"{prawdziwy['sredni_zwrot_proc']}% po spreadzie — bez wartości")

    a = pierwsza.get("sredni_zwrot_proc")
    b = druga.get("sredni_zwrot_proc")
    if a is None or b is None:
        return f"przewaga {przewaga}%, ale jedna połowa okresu bez wejść — niepewne"
    if min(pierwsza.get("wejsc", 0), druga.get("wejsc", 0)) < 8:
        return (f"przewaga {przewaga}%, ale w jednej połowie tylko "
                f"{min(pierwsza.get('wejsc', 0), druga.get('wejsc', 0))} wejść — "
                "za mało, żeby mówić o zgodności połów")
    pa, pb = pierwsza.get("przewaga"), druga.get("przewaga")
    if pa is None or pb is None:
        if (a > 0) != (b > 0):
            return (f"przewaga {przewaga}%, ale połowy okresu przeczą sobie "
                    f"({a}% i {b}%) — wynik niestabilny")
    elif (pa > 0) != (pb > 0):
        # zysk w obu połowach może być wspólny dla całego rynku;
        # o trwałości mówi dopiero przewaga nad placebo w każdej z osobna
        return (f"przewaga {przewaga}% w całości, ale nad placebo tylko w jednej "
                f"połowie ({pa} pp i {pb} pp) — sygnał nietrwały")
    return (f"przewaga {przewaga}% nad losowym wejściem, w obu połowach osobno "
            f"({pa} pp i {pb} pp) przy {prawdziwy['wejsc']} wejściach")


def _rsi(ceny: list[float], okres: int = 14) -> list[float | None]:
    """RSI liczony u nas, żeby dało się go policzyć dla każdej świecy wstecz."""
    wynik: list[float | None] = [None] * len(ceny)
    if len(ceny) < okres + 1:
        return wynik

    zyski, straty = [], []
    for i in range(1, len(ceny)):
        r = ceny[i] - ceny[i - 1]
        zyski.append(max(r, 0))
        straty.append(max(-r, 0))

    sz = sum(zyski[:okres]) / okres
    ss = sum(straty[:okres]) / okres
    for i in range(okres, len(ceny)):
        if i > okres:
            sz = (sz * (okres - 1) + zyski[i - 1]) / okres
            ss = (ss * (okres - 1) + straty[i - 1]) / okres
        wynik[i] = 100.0 if ss == 0 else 100 - 100 / (1 + sz / ss)
    return wynik


def porownaj_progi(progi: list[float] | None = None, kierunek: str = "ponizej",
                   po_ilu: int = 10, ile_swiec: int = 0,
                   spread_proc: float = 0.02) -> dict:
    """Ten sam pomiar na kilku progach naraz — który daje dość wejść i przewagę.

    Luźniejszy próg daje więcej wejść, ale słabszy sygnał. Ostrzejszy odwrotnie.
    To zestawienie pokazuje, gdzie leży granica, zamiast zgadywać.
    """
    progi = progi or [25, 30, 35, 40]
    wiersze = []
    for prog in progi:
        try:
            w = zmierz_prog("RSI", prog, kierunek, po_ilu, ile_swiec, spread_proc)
            c = w.get("caly_okres", {})
            a = w.get("pierwsza_polowa", {}).get("sredni_zwrot_proc")
            b = w.get("druga_polowa", {}).get("sredni_zwrot_proc")
            wiersze.append({
                "prog": prog,
                "wejsc": c.get("wejsc", 0),
                "sredni_zwrot_proc": c.get("sredni_zwrot_proc"),
                "trafien_proc": c.get("trafien_proc"),
                "przewaga_nad_placebo": w.get("przewaga_nad_placebo"),
                "polowy_zgodne": (a is not None and b is not None and (a > 0) == (b > 0)),
                "dosc_wejsc": c.get("wejsc", 0) >= 20,
            })
        except Exception as e:
            wiersze.append({"prog": prog, "blad": str(e)[:60]})

    uzyteczne = [w for w in wiersze
                 if w.get("dosc_wejsc") and w.get("polowy_zgodne")
                 and (w.get("przewaga_nad_placebo") or 0) > 0
                 # sam zwrot musi być dodatni — bicie placebo nie wystarcza,
                 # bo placebo bywa jeszcze gorsze od stratnego sygnału
                 and (w.get("sredni_zwrot_proc") or 0) > 0]

    return {
        "kierunek": kierunek,
        "sprawdzane_po": f"{po_ilu} świecach",
        "progi": wiersze,
        "przechodzi_wszystkie_warunki": [w["prog"] for w in uzyteczne],
        "wniosek": (
            f"progi z dodatnim zwrotem, przewagą nad placebo, zgodnymi połowami "
            f"i co najmniej 20 wejściami: {[w['prog'] for w in uzyteczne]}"
            if uzyteczne else
            "żaden próg nie przeszedł wszystkich czterech warunków"
        ),
    }


# ── wskaźniki liczone u nas, żeby dało się je policzyć dla każdej świecy ──
def _sma(ceny, okres):
    w = [None] * len(ceny)
    for i in range(okres - 1, len(ceny)):
        w[i] = sum(ceny[i - okres + 1:i + 1]) / okres
    return w


def _atr(swiece, okres=14):
    """Średni zasięg z uwzględnieniem luk między świecami."""
    zasiegi = []
    for i, s in enumerate(swiece):
        if i == 0:
            zasiegi.append(s["szczyt"] - s["dolek"])
            continue
        poprz = swiece[i - 1]["zamkniecie"]
        zasiegi.append(max(s["szczyt"] - s["dolek"],
                           abs(s["szczyt"] - poprz),
                           abs(s["dolek"] - poprz)))
    return _sma(zasiegi, okres)


def _bollinger(ceny, okres=20, odchylen=2.0):
    """Zwraca położenie ceny w kanale: 0 to dolna wstęga, 100 to górna."""
    srodek = _sma(ceny, okres)
    w = [None] * len(ceny)
    for i in range(okres - 1, len(ceny)):
        wycinek = ceny[i - okres + 1:i + 1]
        sr = srodek[i]
        odch = (sum((x - sr) ** 2 for x in wycinek) / okres) ** 0.5
        gora, dol = sr + odchylen * odch, sr - odchylen * odch
        w[i] = None if gora == dol else (ceny[i] - dol) / (gora - dol) * 100
    return w


def _adx(swiece, okres=14):
    """Siła ruchu kierunkowego z wygładzaniem Wildera, jak w TradingView.

    Zmierzone przed poprawką: sumy proste dawały 48,89 tam, gdzie TradingView
    pokazywał 25,71 — 23 punkty różnicy, więc progi 30/15 nie znaczyły nic.
    Wartość na pozycji i jest ADX ze świecy i, bez przesunięcia.
    """
    w = [None] * len(swiece)
    if len(swiece) < okres * 2 + 1:
        return w

    plus, minus, tr = [0.0], [0.0], [swiece[0]["szczyt"] - swiece[0]["dolek"]]
    for i in range(1, len(swiece)):
        gora = swiece[i]["szczyt"] - swiece[i - 1]["szczyt"]
        dol = swiece[i - 1]["dolek"] - swiece[i]["dolek"]
        plus.append(gora if gora > dol and gora > 0 else 0.0)
        minus.append(dol if dol > gora and dol > 0 else 0.0)
        poprz = swiece[i - 1]["zamkniecie"]
        tr.append(max(swiece[i]["szczyt"] - swiece[i]["dolek"],
                      abs(swiece[i]["szczyt"] - poprz),
                      abs(swiece[i]["dolek"] - poprz)))

    def wilder(seria):
        out = [None] * len(seria)
        if len(seria) <= okres:
            return out
        s = sum(seria[1:okres + 1])
        out[okres] = s
        for i in range(okres + 1, len(seria)):
            s = s - s / okres + seria[i]
            out[i] = s
        return out

    s_tr, s_plus, s_minus = wilder(tr), wilder(plus), wilder(minus)
    dx = [None] * len(swiece)
    for i in range(okres, len(swiece)):
        if s_tr[i] is None or not s_tr[i]:
            continue
        dp = s_plus[i] / s_tr[i] * 100
        dm = s_minus[i] / s_tr[i] * 100
        dx[i] = 0.0 if dp + dm == 0 else abs(dp - dm) / (dp + dm) * 100

    pierwszy = 2 * okres
    ok = [v for v in dx[okres:pierwszy + 1] if v is not None]
    if len(ok) < okres:
        return w
    adx = sum(ok[-okres:]) / okres
    w[pierwszy] = adx
    for i in range(pierwszy + 1, len(swiece)):
        if dx[i] is None:
            continue
        adx = (adx * (okres - 1) + dx[i]) / okres
        w[i] = adx
    return w


WSKAZNIKI = {
    "RSI": "siła względna, 0 do 100",
    "Bollinger": "położenie w kanale, 0 to dolna wstęga, 100 to górna",
    "ADX": "siła ruchu kierunkowego",
    "ATR_proc": "zasięg świecy jako procent ceny",
}


def _policz(nazwa: str, swiece: list) -> list:
    zamkniecia = [s["zamkniecie"] for s in swiece]
    if nazwa == "RSI":
        return _rsi(zamkniecia, 14)
    if nazwa == "Bollinger":
        return _bollinger(zamkniecia, 20, 2.0)
    if nazwa == "ADX":
        return _adx(swiece, 14)
    if nazwa == "ATR_proc":
        atr = _atr(swiece, 14)
        return [None if a is None or not c else a / c * 100
                for a, c in zip(atr, zamkniecia)]
    raise BladPomiaru(f"nieznany wskaźnik: {nazwa}. Dostępne: {list(WSKAZNIKI)}")


def zmierz(wskaznik: str = "RSI", prog: float = 30, kierunek: str = "ponizej",
           po_ilu: int = 10, ile_swiec: int = 0,
           spread_proc: float = 0.02, losowan: int = 50, seed: int = 42) -> dict:
    """To samo co zmierz_prog, ale dla dowolnego z czterech wskaźników.

    Dostępne: RSI, Bollinger (położenie w kanale), ADX, ATR_proc.
    """
    import analiza

    _sprawdz_kierunek(kierunek)
    swiece = analiza._swiece_z_wykresu(ile_swiec)
    if len(swiece) < 60:
        raise BladPomiaru(f"za mało świec: {len(swiece)}, potrzeba co najmniej 60")

    wartosci = _policz(wskaznik, swiece)
    od = 25  # tyle świec potrzebuje najdłuższy wskaźnik na rozbieg

    # Epizody, nie sąsiednie świece: po wejściu czekamy do wyjścia, zanim
    # policzymy następne. Bez tego wejście na świecy 30 i 31 liczyło się jako
    # dwie niezależne próby, a próg dwudziestu wejść przechodził na powtórkach.
    wejscia, wolne_od, sygnalow = [], 0, 0
    for i in range(od, len(swiece) - po_ilu - 1):
        w = wartosci[i]
        if w is None:
            continue
        if (kierunek == "ponizej" and w < prog) or (kierunek == "powyzej" and w > prog):
            sygnalow += 1
            if i >= wolne_od:
                wejscia.append(i)
                wolne_od = i + 1 + po_ilu

    if not wejscia:
        return {"wejsc": 0,
                "uwaga": f"warunek {wskaznik} {kierunek} {prog} nie wystąpił ani razu"}

    polowa = len(swiece) // 2
    prawdziwy = _wynik_po(swiece, wejscia, po_ilu, spread_proc)
    rng_pol = random.Random(seed + 1)
    pierwsza = _placebo_dla(swiece, [i for i in wejscia if i < polowa], 0, polowa,
                            po_ilu, spread_proc, rng_pol, losowan)
    druga = _placebo_dla(swiece, [i for i in wejscia if i >= polowa], polowa, len(swiece),
                         po_ilu, spread_proc, rng_pol, losowan)

    # seed jawny: bez niego dwa uruchomienia dawały różne placebo i różne wnioski
    rng = random.Random(seed)
    kw = _kwintyle_zmiennosci(swiece)
    losowe, blokowo = [], False
    for _ in range(losowan):
        prob, blokowo = _losuj_probe(swiece, wejscia, od, len(swiece) - po_ilu, rng, kw)
        w = _wynik_po(swiece, prob, po_ilu, spread_proc)
        if w.get("wejsc"):
            losowe.append(w["sredni_zwrot_proc"])

    placebo = round(statistics.mean(losowe), 4) if losowe else None
    przewaga = (round(prawdziwy["sredni_zwrot_proc"] - placebo, 4)
                if placebo is not None and prawdziwy.get("wejsc") else None)

    # Miara niepewności: sama przewaga nad średnią placebo nic nie mówi, gdy
    # losowania rozrzucają się szerzej niż ta przewaga. z-score pokazuje,
    # ile odchyleń placebo dzieli prawdziwy wynik od losowego. Poniżej 1
    # to szum; percentyl mówi, jaka część losowań była gorsza od prawdziwego.
    odch_placebo = round(statistics.pstdev(losowe), 4) if len(losowe) > 1 else None
    z = None
    percentyl = None
    if odch_placebo and prawdziwy.get("wejsc"):
        z = round((prawdziwy["sredni_zwrot_proc"] - placebo) / odch_placebo, 2)
        percentyl = round(sum(1 for x in losowe if x < prawdziwy["sredni_zwrot_proc"])
                          / len(losowe) * 100, 1)

    return {
        "warunek": f"{wskaznik} {kierunek} {prog}",
        "opis_wskaznika": WSKAZNIKI.get(wskaznik, ""),
        "sygnalow_lacznie": sygnalow,
        "epizodow_bez_nakladania": len(wejscia),
        "swiec": len(swiece),
        "sprawdzane_po": f"{po_ilu} świecach",
        "spread_odjety_proc": spread_proc,
        "caly_okres": prawdziwy,
        "pierwsza_polowa": pierwsza,
        "druga_polowa": druga,
        "placebo_sredni_zwrot": placebo,
        "placebo_odchylenie": odch_placebo,
        "placebo_blokowe": blokowo,
        "przewaga_nad_placebo": przewaga,
        "z_score": z,
        "percentyl_wobec_placebo": percentyl,
        "losowan": len(losowe),
        "wniosek": _wniosek(prawdziwy, placebo, przewaga, pierwsza, druga, z),
    }


def przeglad_wskaznikow(po_ilu: int = 10, ile_swiec: int = 0,
                        spread_proc: float = 0.02) -> dict:
    """Wszystkie cztery wskaźniki, sensowne progi, jeden przebieg.

    Odpowiada na pytanie: czy KTÓRYKOLWIEK z nich cokolwiek zapowiada
    na tym instrumencie i przedziale.
    """
    zestaw = [
        ("RSI", 30, "ponizej"), ("RSI", 70, "powyzej"),
        ("Bollinger", 10, "ponizej"), ("Bollinger", 90, "powyzej"),
        ("ADX", 30, "powyzej"), ("ADX", 15, "ponizej"),
        ("ATR_proc", 0.15, "powyzej"),
    ]

    wiersze = []
    for wsk, prog, kier in zestaw:
        try:
            w = zmierz(wsk, prog, kier, po_ilu, ile_swiec, spread_proc)
            c = w.get("caly_okres", {})
            wiersze.append({
                "warunek": f"{wsk} {kier} {prog}",
                "wejsc": c.get("wejsc", 0),
                "zwrot_proc": c.get("sredni_zwrot_proc"),
                "trafien_proc": c.get("trafien_proc"),
                "przewaga": w.get("przewaga_nad_placebo"),
                "wniosek": w.get("wniosek", "")[:70],
            })
        except Exception as e:
            wiersze.append({"warunek": f"{wsk} {kier} {prog}", "blad": str(e)[:60]})

    przeszly = [w for w in wiersze
                if w.get("wejsc", 0) >= 20
                and (w.get("zwrot_proc") or 0) > 0
                and (w.get("przewaga") or 0) > 0]

    return {
        "sprawdzono": len(wiersze),
        "wyniki": wiersze,
        "przeszly": [w["warunek"] for w in przeszly],
        "wniosek": (f"warunki z przewagą: {[w['warunek'] for w in przeszly]}"
                    if przeszly else
                    "żaden z siedmiu warunków nie dał przewagi na tych danych"),
    }


def przeglad_instrumentow(instrumenty: list | None = None,
                          po_ilu: int = 10, spread_proc: float = 0.02) -> dict:
    """Ten sam przegląd na kilku instrumentach i przedziałach.

    Wynik z jednego wykresu to jeden pomiar. Dopiero powtórzenie na innym
    instrumencie pokazuje, czy wniosek się utrzymuje, czy był przypadkiem.

    Każda pozycja to para (symbol, przedział). Wykres jest przełączany
    i przywracany na koniec.
    """
    import wykres

    instrumenty = instrumenty or [
        ("FX:EURUSD", "60"),
        ("FX:EURUSD", "D"),
        ("COMEX:GC1!", "60"),
        ("COINBASE:BTCUSD", "60"),
    ]

    stan_poczatkowy = wykres.stan()
    wyniki = {}

    for symbol, przedzial in instrumenty:
        klucz = f"{symbol} {przedzial}"
        try:
            # przelacz sprawdza krzyzowo, czy swiece naprawde naleza do instrumentu
            p = wykres.przelacz(symbol, przedzial)
            if not p.get("potwierdzone"):
                wyniki[klucz] = {
                    "pominiete": "świece nie potwierdziły instrumentu",
                    "szczegol": p.get("powod", "")[:70],
                }
                continue
            w = przeglad_wskaznikow(po_ilu, 0, spread_proc)
            wyniki[klucz] = {
                "sprawdzono": w["sprawdzono"],
                "przeszly": w["przeszly"],
                "najlepszy": _najlepszy(w["wyniki"]),
            }
        except Exception as e:
            wyniki[klucz] = {"blad": str(e)[:80]}

    try:
        wykres.przelacz(stan_poczatkowy["symbol"], stan_poczatkowy["interwal"])
    except Exception:
        pass

    wszystkie_przeszly = [w for r in wyniki.values() for w in r.get("przeszly", [])]

    return {
        "instrumentow": len(instrumenty),
        "stan_przywrocony": f"{stan_poczatkowy['symbol']} {stan_poczatkowy['interwal']}",
        "wyniki": wyniki,
        "warunki_ktore_przeszly_gdziekolwiek": sorted(set(wszystkie_przeszly)),
        "wniosek": (
            f"warunki z przewagą na przynajmniej jednym instrumencie: "
            f"{sorted(set(wszystkie_przeszly))}"
            if wszystkie_przeszly else
            f"na {len(instrumenty)} instrumentach żaden warunek nie dał przewagi"
        ),
    }


def _najlepszy(wiersze: list) -> dict | None:
    """Wiersz z najwyższym zwrotem — nawet gdy nie przeszedł, warto go widzieć."""
    z_wynikiem = [w for w in wiersze if w.get("zwrot_proc") is not None]
    if not z_wynikiem:
        return None
    n = max(z_wynikiem, key=lambda w: w["zwrot_proc"])
    return {"warunek": n["warunek"], "zwrot_proc": n["zwrot_proc"],
            "wejsc": n["wejsc"], "trafien_proc": n["trafien_proc"]}


def odniesienie_trzymanie(po_ilu: int = 10, ile_swiec: int = 0,
                          spread_proc: float = 0.02) -> dict:
    """Ile daje samo trzymanie przez N świec, bez żadnego sygnału.

    To uczciwszy punkt odniesienia niż losowe wejście: mówi, ile zarobiłby
    ktoś, kto wchodzi zawsze i nie patrzy na wskaźniki. Sygnał ma sens
    dopiero wtedy, gdy bije TĘ liczbę, nie samo placebo.
    """
    import analiza

    swiece = analiza._swiece_z_wykresu(ile_swiec)
    wszystkie = list(range(25, len(swiece) - po_ilu))
    return _wynik_po(swiece, wszystkie, po_ilu, spread_proc)


def czy_sygnal_czy_trend(wskaznik: str = "Bollinger", prog: float = 90,
                         kierunek: str = "powyzej", po_ilu: int = 10,
                         ile_swiec: int = 0, spread_proc: float = 0.02) -> dict:
    """Rozstrzyga, czy warunek naprawdę coś wnosi, czy tylko łapie trend.

    Porównuje cztery liczby: warunek, warunek odwrotny, samo trzymanie
    i losowe wejście. Prawdziwy sygnał bije trzymanie, a jego odwrotność
    wypada gorzej. Sam trend daje podobny wynik niezależnie od warunku.
    """
    odwrotny = "ponizej" if kierunek == "powyzej" else "powyzej"
    prog_odwrotny = 100 - prog if wskaznik in ("Bollinger", "RSI") else prog

    w = zmierz(wskaznik, prog, kierunek, po_ilu, ile_swiec, spread_proc)
    o = zmierz(wskaznik, prog_odwrotny, odwrotny, po_ilu, ile_swiec, spread_proc)
    trzymanie = odniesienie_trzymanie(po_ilu, ile_swiec, spread_proc)

    zw = w.get("caly_okres", {}).get("sredni_zwrot_proc")
    zo = o.get("caly_okres", {}).get("sredni_zwrot_proc")
    zt = trzymanie.get("sredni_zwrot_proc")

    nad_trzymaniem = round(zw - zt, 4) if zw is not None and zt is not None else None
    rozstep = round(zw - zo, 4) if zw is not None and zo is not None else None

    if nad_trzymaniem is None or rozstep is None:
        ocena = "za mało danych do rozstrzygnięcia"
    elif nad_trzymaniem <= 0:
        ocena = (f"warunek daje {zw}%, a samo trzymanie {zt}% — "
                 "sygnał nie wnosi nic ponad bycie na rynku")
    elif rozstep <= 0:
        ocena = (f"warunek i jego odwrotność dają podobnie ({zw}% i {zo}%) — "
                 "to trend, nie sygnał")
    else:
        ocena = (f"warunek bije trzymanie o {nad_trzymaniem} pp, a jego odwrotność "
                 f"wypada o {rozstep} pp gorzej — zachowuje się jak prawdziwy sygnał")

    return {
        "warunek": f"{wskaznik} {kierunek} {prog}",
        "warunek_odwrotny": f"{wskaznik} {odwrotny} {prog_odwrotny}",
        "zwrot_warunku_proc": zw,
        "zwrot_odwrotnego_proc": zo,
        "zwrot_trzymania_proc": zt,
        "zwrot_losowego_proc": w.get("placebo_sredni_zwrot"),
        "nad_trzymaniem_pp": nad_trzymaniem,
        "rozstep_warunek_odwrotny_pp": rozstep,
        "wejsc_warunku": w.get("caly_okres", {}).get("wejsc"),
        "ocena": ocena,
    }


def jak_dlugo_trzymac(wskaznik: str = "Bollinger", prog: float = 90,
                      kierunek: str = "powyzej",
                      dlugosci: list[int] | None = None,
                      ile_swiec: int = 0, spread_proc: float = 0.02) -> dict:
    """Po ilu świecach sygnał daje najwięcej ponad samo trzymanie.

    Zmierzone: ten sam warunek potrafi działać odwrotnie na krótkim terminie
    i dobrze na długim. Na złocie przy pięciu świecach dół kanału bił górę,
    a przy czterdziestu góra była lepsza o siedem punktów procentowych.

    Sama wysokość zwrotu nie wystarcza, bo przy dłuższym trzymaniu rośnie
    wszystko. Liczy się różnica wobec trzymania i rozstęp wobec warunku
    odwrotnego.
    """
    dlugosci = dlugosci or [3, 5, 10, 20, 40]
    wiersze = []

    for po in dlugosci:
        try:
            r = czy_sygnal_czy_trend(wskaznik, prog, kierunek, po,
                                     ile_swiec, spread_proc)
            wiersze.append({
                "po_swiecach": po,
                "zwrot_warunku_proc": r["zwrot_warunku_proc"],
                "zwrot_odwrotnego_proc": r["zwrot_odwrotnego_proc"],
                "zwrot_trzymania_proc": r["zwrot_trzymania_proc"],
                "nad_trzymaniem_pp": r["nad_trzymaniem_pp"],
                "rozstep_pp": r["rozstep_warunek_odwrotny_pp"],
                "wejsc": r["wejsc_warunku"],
                "dziala": (r["nad_trzymaniem_pp"] or 0) > 0
                          and (r["rozstep_warunek_odwrotny_pp"] or 0) > 0,
            })
        except Exception as e:
            wiersze.append({"po_swiecach": po, "blad": str(e)[:60]})

    dzialajace = [w for w in wiersze if w.get("dziala")]
    najlepszy = (max(dzialajace, key=lambda w: w["nad_trzymaniem_pp"])
                 if dzialajace else None)
    najkrotszy = min((w["po_swiecach"] for w in dzialajace), default=None)

    if not dzialajace:
        wniosek = "warunek nie bije trzymania na żadnej z badanych długości"
    else:
        wniosek = (
            f"działa od {najkrotszy} świec wzwyż; najwięcej ponad trzymanie daje "
            f"po {najlepszy['po_swiecach']} świecach ({najlepszy['nad_trzymaniem_pp']} pp "
            f"przy {najlepszy['wejsc']} wejściach)"
        )
        nie_dziala = [w["po_swiecach"] for w in wiersze
                      if "blad" not in w and not w.get("dziala")]
        if nie_dziala:
            wniosek += f". Nie działa przy: {nie_dziala} świec"

    return {
        "warunek": f"{wskaznik} {kierunek} {prog}",
        "dlugosci": wiersze,
        "dziala_od": najkrotszy,
        "najlepsza_dlugosc": najlepszy["po_swiecach"] if najlepszy else None,
        "wniosek": wniosek,
        "uwaga": ("Przy dłuższym trzymaniu rosną wszystkie liczby, także trzymanie. "
                  "Dlatego porównuj różnicę, nie sam zwrot."),
    }


def koszt_a_przewaga(wskaznik: str = "Bollinger", prog: float = 90,
                     kierunek: str = "powyzej", po_ilu: int = 40,
                     ile_swiec: int = 0,
                     koszty: list[float] | None = None) -> dict:
    """Przy jakim koszcie transakcji sygnał przestaje mieć sens.

    Uwaga na pułapkę, w którą sam wpadłem: nie wystarczy odjąć spread od obu
    stron porównania. Sygnał wchodzi i wychodzi kilkadziesiąt razy, a kupno
    z trzymaniem płaci koszt RAZ. Przy porównaniu per wejście koszt skraca się
    po obu stronach i różnica wychodzi stała, co niczego nie mówi.

    Dlatego liczymy tu inaczej: bierzemy sumaryczny wynik obu podejść na tym
    samym okresie i obciążamy każde jego prawdziwą liczbą transakcji.
    """
    import analiza

    koszty = koszty or [0.02, 0.05, 0.1, 0.2, 0.5, 1.0]
    swiece = analiza._swiece_z_wykresu(ile_swiec)
    if len(swiece) < 60:
        raise BladPomiaru(f"za mało świec: {len(swiece)}")

    wartosci = _policz(wskaznik, swiece)
    od = 25

    wejscia = []
    for i in range(od, len(swiece) - po_ilu):
        w = wartosci[i]
        if w is None:
            continue
        if (kierunek == "ponizej" and w < prog) or (kierunek == "powyzej" and w > prog):
            wejscia.append(i)

    if not wejscia:
        return {"wejsc": 0, "uwaga": "warunek nie wystąpił ani razu"}

    # Transakcje BEZ NAKŁADANIA: po wejściu czekamy do wyjścia, zanim wejdziemy
    # znowu. Bez tego wejście na świecy 30 i 31 liczyłoby się dwa razy, choć to
    # prawie ta sama pozycja — suma zawyżałaby wynik kilkukrotnie.
    zwroty = []
    wolne_od = 0
    pominietych = 0
    for i in wejscia:
        if i < wolne_od:
            pominietych += 1
            continue
        if i + po_ilu >= len(swiece):
            continue
        we, wy = swiece[i]["zamkniecie"], swiece[i + po_ilu]["zamkniecie"]
        if we:
            zwroty.append((wy - we) / we * 100)
            wolne_od = i + po_ilu

    # kupno z trzymaniem: jedno wejście na początku, jedno wyjście na końcu
    poczatek, koniec = swiece[od]["zamkniecie"], swiece[-1]["zamkniecie"]
    trzymanie_bez_kosztu = (koniec - poczatek) / poczatek * 100

    wiersze = []
    for k in koszty:
        suma_sygnalu = sum(z - k for z in zwroty)
        trzymanie = trzymanie_bez_kosztu - k        # koszt płacony raz
        wiersze.append({
            "koszt_proc": k,
            "sygnal_suma_proc": round(suma_sygnalu, 3),
            "sygnal_srednio_proc": round(suma_sygnalu / len(zwroty), 4),
            "trzymanie_proc": round(trzymanie, 3),
            "sygnal_lepszy": suma_sygnalu > trzymanie,
        })

    dziala = [w["koszt_proc"] for w in wiersze if w["sygnal_lepszy"]]
    granica = max(dziala) if dziala else None

    return {
        "warunek": f"{wskaznik} {kierunek} {prog}",
        "po_swiecach": po_ilu,
        "transakcji_sygnalu": len(zwroty),
        "wejsc_pominietych_bo_pozycja_otwarta": pominietych,
        "transakcji_trzymania": 1,
        "trzymanie_bez_kosztu_proc": round(trzymanie_bez_kosztu, 3),
        "warianty": wiersze,
        "dziala_do_kosztu_proc": granica,
        "wniosek": (
            f"sygnał robi {len(zwroty)} transakcji bez nakładania "
            f"({pominietych} wejść pominiętych, bo pozycja była już otwarta), "
            f"kupno z trzymaniem jedną. "
            + (f"Sygnał wygrywa do kosztu {granica}% na transakcję."
               if granica is not None else
               "Sygnał przegrywa z trzymaniem nawet przy najniższym badanym koszcie.")
        ),
    }


def _demo():
    print("Pomiar: czy RSI poniżej 30 cokolwiek zapowiada\n")
    w = zmierz_prog("RSI", 30, "ponizej", po_ilu=10)
    for k, v in w.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"      {kk:22} {vv}")
        else:
            print(f"  {k:24} {v}")


def _wejscia_dla(wartosci, prog, kierunek, od, do, po_ilu):
    """Epizody bez nakładania w zakresie [od, do)."""
    wejscia, wolne_od = [], 0
    for i in range(max(od, 25), min(do, len(wartosci)) - po_ilu - 1):
        w = wartosci[i]
        if w is None:
            continue
        if (kierunek == "ponizej" and w < prog) or (kierunek == "powyzej" and w > prog):
            if i >= wolne_od:
                wejscia.append(i)
                wolne_od = i + 1 + po_ilu
    return wejscia


def walk_forward(wskaznik: str = "RSI", kierunek: str = "ponizej",
                 progi: list | None = None, po_ilu: int = 10,
                 ile_swiec: int = 0, czesc_ucz: float = 0.7,
                 spread_proc: float = 0.0, losowan: int = 50, seed: int = 42,
                 swiece: list | None = None) -> dict:
    """Jedyny pomiar poza próbą: próg wybrany na części uczącej, sprawdzony na testowej.

    Wszystko wcześniej mierzyło w próbie — próg i wynik z tych samych świec,
    więc najlepszy próg zawsze wyglądał dobrze. Tu: pierwsze `czesc_ucz` świec
    służy do wyboru progu (najwyższy z-score wobec placebo), ostatnie do
    sprawdzenia, czy ten próg trzyma się na danych, których wybór nie widział.

    Wskaźnik liczony na całej serii (bez ucięcia rozgrzewki na granicy),
    wejścia w części testowej tylko od granicy w górę. Placebo losowane
    osobno w każdej części.

    Ile świec da wykres: świeże przełączenie symbolu wczytuje około 400.
    Pełna historia (zmierzone 2518 na złocie dziennym) pojawia się tylko,
    gdy na wykresie jest strategia z włączonym głębokim testem — przewijanie,
    setVisibleRange i scrollTo tego nie doczytują (sprawdzone trzema drogami).
    `swiece` pozwala podać własną serię, np. zapisaną wcześniej do pliku.
    """
    import analiza
    if swiece is None:
        swiece = analiza._swiece_z_wykresu(ile_swiec)
    if len(swiece) < 200:
        raise BladPomiaru(f"za mało świec: {len(swiece)}, walk-forward wymaga co najmniej 200")
    wartosci = _policz(wskaznik, swiece)
    granica = int(len(swiece) * czesc_ucz)
    if progi is None:
        # Progi z percentyli wskaźnika na części uczącej, nie sztywne liczby:
        # sztywne 0,05–0,3 dla ATR łapały każdą świecę złota (ATR dzienny ~1%),
        # a RSI<40 w hossie nie wystąpiło ani razu. Percentyle pasują do
        # każdego instrumentu i interwału, a część testowa ich nie widzi.
        w_ucz = sorted(v for v in wartosci[:granica] if v is not None)
        if len(w_ucz) < 20:
            raise BladPomiaru("za mało wartości wskaźnika w części uczącej")
        pc = [10, 20, 30, 40, 50] if kierunek == "ponizej" else [50, 60, 70, 80, 90]
        progi = sorted({round(w_ucz[min(len(w_ucz) - 1, int(len(w_ucz) * q / 100))], 4) for q in pc})
    rng = random.Random(seed)

    ucz = []
    for prog in progi:
        we = _wejscia_dla(wartosci, prog, kierunek, 0, granica, po_ilu)
        r = _placebo_dla(swiece, we, 0, granica, po_ilu, spread_proc, rng, losowan)
        ucz.append({"prog": prog, "wejsc": r.get("wejsc", 0), "zwrot": r.get("sredni_zwrot_proc"),
                    "przewaga": r.get("przewaga"), "z": r.get("z")})
    z_wejsciami = [u for u in ucz if u["wejsc"] >= 8 and u["z"] is not None]
    if not z_wejsciami:
        return {"wskaznik": wskaznik, "kierunek": kierunek, "swiec": len(swiece),
                "granica": granica, "uczenie": ucz,
                "wniosek": "żaden próg nie dał ośmiu wejść w części uczącej — nie ma czego wybierać"}
    najlepszy = max(z_wejsciami, key=lambda u: u["z"])

    we_t = _wejscia_dla(wartosci, najlepszy["prog"], kierunek, granica, len(swiece), po_ilu)
    test = _placebo_dla(swiece, we_t, granica, len(swiece), po_ilu, spread_proc, rng, losowan)
    test_w = {"prog": najlepszy["prog"], "wejsc": test.get("wejsc", 0),
              "zwrot": test.get("sredni_zwrot_proc"), "przewaga": test.get("przewaga"), "z": test.get("z")}

    if test_w["wejsc"] < 8:
        wn = (f"próg {najlepszy['prog']} wybrany na uczeniu (z {najlepszy['z']}), ale poza próbą "
              f"tylko {test_w['wejsc']} wejść — za mało, żeby cokolwiek powiedzieć")
    elif test_w["z"] is None:
        wn = "placebo w części testowej nie dało się policzyć"
    elif test_w["z"] >= 1 and najlepszy["z"] >= 1:
        wn = (f"próg {najlepszy['prog']}: z {najlepszy['z']} na uczeniu, z {test_w['z']} poza próbą "
              f"przy {test_w['wejsc']} wejściach — trzyma się poza próbą")
    elif test_w["przewaga"] is not None and test_w["przewaga"] > 0:
        wn = (f"próg {najlepszy['prog']}: z {najlepszy['z']} na uczeniu, {test_w['z']} poza próbą "
              f"— przewaga dodatnia, ale w rozrzucie placebo")
    else:
        wn = (f"próg {najlepszy['prog']}: z {najlepszy['z']} na uczeniu, poza próbą {test_w['z']} "
              f"— nie trzyma się; wybór progu dopasował się do przeszłości")

    return {"wskaznik": wskaznik, "kierunek": kierunek, "po_ilu": po_ilu,
            "swiec": len(swiece), "granica": granica, "czesc_ucz": czesc_ucz,
            "uczenie": ucz, "wybrany_prog": najlepszy["prog"], "test": test_w,
            "wniosek": wn}


if __name__ == "__main__":
    _demo()
