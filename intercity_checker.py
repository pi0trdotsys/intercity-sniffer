#!/usr/bin/env python3
"""
Sprawdza wolne miejsca na bezpośrednich połączeniach Wrocław Główny -> Kielce
po godzinie 17:00, dla 7 kolejnych dni (od jutra), i wysyła jeden zbiorczy
raport na Telegram, podzielony dzień po dniu. Klasa 2 sprawdzana zawsze,
klasa 1 tylko awaryjnie - gdy w klasie 2 brak wolnych miejsc.

api-gateway.intercity.pl stoi za Akamai Bot Manager - zwykłe zapytania HTTP
(bez prawdziwego środowiska przeglądarki) dostają 418 "I'm a teapot", a nawet
headless Chromium (także --headless=new) jest blokowany/zawieszany na
ebilet.intercity.pl. Dlatego wszystkie zapytania do intercity.pl wykonujemy
jako fetch() z wnętrza prawdziwego, WIDOCZNEGO okna Chromium (Playwright,
headless=False) - dopiero po jednym przejściu strony mamy poprawne
ciasteczka/sensor Akamai, których używają wszystkie kolejne zapytania w tej
samej sesji. Telegram nie ma takiej ochrony, więc tam zwykłe requests.

Konfiguracja przez zmienne środowiskowe:
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID

Użycie:
    pip install playwright requests
    playwright install chromium
    TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python3 intercity_checker.py
"""

import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta

import requests
from playwright.sync_api import sync_playwright

API_BASE = "https://api-gateway.intercity.pl"

STACJA_WYJAZDU = 5100069   # Wrocław Główny (kod EVA/IBNR)
STACJA_PRZYJAZDU = 5100022  # Kielce Główne (kod EVA/IBNR)

# Osobne, stałe kody używane wyłącznie przez podsystem rezerwacji miejsc
# ("wbnet") dla tej konkretnej relacji - nie da się ich wyprowadzić z kodów
# EVA powyżej, ustalone przez przechwycenie ruchu (patrz memory/sniffer_status.md).
GRM_STACJA_PRZYJAZDU = "5100143"
GRM_STACJA_WYJAZDU = "5100044"

MIN_GODZINA = 17
DNI_DO_PRZODU = 7
MAX_MIEJSC_W_LINII = 12  # ile numerów miejsc pokazać zanim zwiniemy do "+N"
PAUZA_MIEDZY_ZAPYTANIAMI = 0.5  # sekundy - żeby nie walić API seriami
PAUZA_MIEDZY_DNIAMI = 2.0  # sekundy - przerwa przed startem sesji dla kolejnego dnia

# api-gateway.intercity.pl (Akamai Bot Manager) czasem odpowiada 418 na
# pierwszą próbę danego zapytania jako sensor/challenge - potwierdzone, że
# nawet oficjalny frontend intercity.pl dostaje to i po prostu automatycznie
# ponawia (patrz MAX_PROBY_418 / fetch() poniżej). Ale samo retry nie
# wystarcza: "ryzyko" narasta też w obrębie CAŁEJ sesji/ciasteczka wraz z
# liczbą zapytań - test na 7 dni w jednej sesji padał na piątym dniu mimo
# retry. Dlatego każdy dzień dostaje własny, świeży kontekst przeglądarki.

DNI_TYGODNIA = ["PON", "WT", "ŚR", "CZW", "PT", "SOB", "NDZ"]

SEAT_RE = re.compile(
    r'<g[^>]*aria-label="Miejsce (\d+) klasa (\d+),\s*([^,]+),\s*(Wolne|Niedostepne)[^"]*"'
    r'[^>]*>\s*<image[^>]*status="(\d+)"',
    re.IGNORECASE,
)

FETCH_JS = """
async ({url, method, body}) => {
    const opts = {method, headers: {"accept": "application/json, text/plain, */*"}};
    if (body !== null) {
        opts.body = JSON.stringify(body);
        opts.headers["content-type"] = "application/json";
    }
    const resp = await fetch(url, opts);
    const text = await resp.text();
    return {status: resp.status, text};
}
"""


class CheckError(Exception):
    pass


MAX_PROBY_418 = 4  # nawet oficjalny frontend intercity.pl dostaje czasem 418
                    # (sensor/challenge Akamai) przy pierwszej próbie i po prostu ponawia


def fetch(page, url: str, method: str = "GET", body: dict | None = None) -> str:
    for proba in range(1, MAX_PROBY_418 + 1):
        result = page.evaluate(FETCH_JS, {"url": url, "method": method, "body": body})
        if result["status"] == 418 and proba < MAX_PROBY_418:
            time.sleep(1.0 * proba)
            continue
        if result["status"] >= 400:
            raise CheckError(f"{method} {url} -> HTTP {result['status']}: {result['text'][:300]}")
        time.sleep(PAUZA_MIEDZY_ZAPYTANIAMI)
        return result["text"]


def search_connections(page, dzien: date) -> list[dict]:
    dzien_str = dzien.isoformat()
    body = {
        "metoda": "wyszukajPolaczenia",
        "wersja": "1.5.20_desktop",
        "url": (
            f"https://ebilet.intercity.pl/wyszukiwanie?dwyj={dzien_str}"
            f"&swyj={STACJA_WYJAZDU}&sprzy={STACJA_PRZYJAZDU}&time=17%3A00"
            "&przy=0&sprzez=&ticket100=1990&ticket50=&polbez=0"
        ),
        "dataWyjazdu": f"{dzien_str} 00:00:00",
        "dataPrzyjazdu": f"{dzien_str} 23:59:59",
        "stacjaWyjazdu": STACJA_WYJAZDU,
        "stacjaPrzyjazdu": STACJA_PRZYJAZDU,
        "czasNaPrzesiadkeMin": 5,
        "stacjePrzez": [],
        "polaczeniaBezposrednie": 0,
        "polaczeniaNajszybsze": 0,
        "liczbaPolaczen": 0,
        "kategoriePociagow": [],
        "kodyPrzewoznikow": [],
        "rodzajeMiejsc": [],
        "typyMiejsc": [],
        "czasNaPrzesiadkeMax": 1440,
        "braille": 0,
        "liczbaPrzesiadekMax": 2,
        "atrybutyHandlowe": [],
        "urzadzenieNr": 956,
    }
    text = fetch(page, f"{API_BASE}/server/public/endpoint/Pociagi", "POST", body)
    data = json.loads(text)
    if data.get("bledy"):
        raise CheckError(f"Błąd wyszukiwania połączeń: {data['bledy']}")
    return data.get("polaczenia", [])


def bezposrednie_po_17(polaczenia: list[dict]) -> list[dict]:
    wynik = []
    for p in polaczenia:
        pociagi = p.get("pociagi", [])
        if len(pociagi) != 1:
            continue  # pomijamy połączenia z przesiadką
        pociag = pociagi[0]
        if pociag.get("grm") != 1:
            continue  # brak dostępnej mapy miejsc dla tego pociągu
        odjazd = datetime.strptime(pociag["dataWyjazdu"], "%Y-%m-%d %H:%M:%S")
        if odjazd.hour < MIN_GODZINA:
            continue
        wynik.append(pociag)
    return wynik


def pobierz_sklad(page, pociag: dict) -> dict:
    odjazd = datetime.strptime(pociag["dataWyjazdu"], "%Y-%m-%d %H:%M:%S")
    przyjazd = datetime.strptime(pociag["dataPrzyjazdu"], "%Y-%m-%d %H:%M:%S")
    url = (
        f"{API_BASE}/grm/sklad/wbnet/{pociag['kategoriaPociagu']}/{pociag['nrPociagu']}/"
        f"{przyjazd:%Y%m%d%H%M}/{GRM_STACJA_PRZYJAZDU}/"
        f"{odjazd:%Y%m%d%H%M}/{GRM_STACJA_WYJAZDU}"
    )
    return json.loads(fetch(page, url))


def pobierz_miejsca_wagonu(page, pociag: dict, nr_wagonu: int, schemat: str) -> list[dict]:
    odjazd = datetime.strptime(pociag["dataWyjazdu"], "%Y-%m-%d %H:%M:%S")
    przyjazd = datetime.strptime(pociag["dataPrzyjazdu"], "%Y-%m-%d %H:%M:%S")
    url = (
        f"{API_BASE}/grm/wagon/svg/wbnet/{pociag['kategoriaPociagu']}/{pociag['nrPociagu']}/"
        f"{nr_wagonu}/{schemat}/{odjazd:%Y%m%d%H%M}/{przyjazd:%Y%m%d%H%M}/"
        f"{GRM_STACJA_PRZYJAZDU}/{GRM_STACJA_WYJAZDU}"
    )
    svg_text = fetch(page, url)
    miejsca = []
    for seat_num, klasa, gdzie, _status_tekst, status in SEAT_RE.findall(svg_text):
        miejsca.append({
            "numer": seat_num,
            "klasa": klasa,
            "gdzie": gdzie.strip(),
            "wolne": status == "1",
        })
    return miejsca


def pobierz_wolne_dla_wagonow(page, pociag: dict, numery_wagonow: list[int],
                              wagony_schemat: dict, niedostepne: set) -> list[dict]:
    wynik = []
    for nr_wagonu in numery_wagonow:
        if nr_wagonu in niedostepne:
            continue
        schemat = wagony_schemat.get(str(nr_wagonu))
        if not schemat:
            continue
        miejsca = pobierz_miejsca_wagonu(page, pociag, nr_wagonu, schemat)
        wolne = [m["numer"] for m in miejsca if m["wolne"]]
        if wolne:
            wynik.append({
                "wagon": nr_wagonu,
                "klasa": miejsca[0]["klasa"] if miejsca else "?",
                "wolne_miejsca": wolne,
            })
    return wynik


def sprawdz_pociag(page, pociag: dict) -> dict:
    sklad = pobierz_sklad(page, pociag)
    niedostepne = set(sklad.get("wagonyNiedostepne", []))
    wagony_schemat = sklad.get("wagonySchemat", {})

    wagony_klasa2 = pobierz_wolne_dla_wagonow(
        page, pociag, sklad.get("klasa2", []), wagony_schemat, niedostepne,
    )
    total_klasa2 = sum(len(w["wolne_miejsca"]) for w in wagony_klasa2)

    # klasa 1 sprawdzana tylko awaryjnie - gdy w klasie 2 zero wolnych miejsc
    wagony_klasa1 = []
    if total_klasa2 == 0:
        wagony_klasa1 = pobierz_wolne_dla_wagonow(
            page, pociag, sklad.get("klasa1", []), wagony_schemat, niedostepne,
        )

    return {
        "pociag": pociag,
        "pojazd": sklad.get("pojazdNazwa", ""),
        "klasa2": wagony_klasa2,
        "klasa1_awaryjnie": wagony_klasa1,
    }


def wskaznik(total: int) -> str:
    if total == 0:
        return "🔴"
    if total < 5:
        return "🟡"
    return "🟢"


def skroc_miejsca(numery: list[str]) -> str:
    if len(numery) > MAX_MIEJSC_W_LINII:
        pokazane = ", ".join(numery[:MAX_MIEJSC_W_LINII])
        return f"{pokazane} <i>+{len(numery) - MAX_MIEJSC_W_LINII}</i>"
    return ", ".join(numery)


def formatuj_dzien(dzien: date, wyniki: list[dict]) -> list[str]:
    nazwa_dnia = DNI_TYGODNIA[dzien.weekday()]
    naglowek = f"📅 <b>{nazwa_dnia} {dzien:%d.%m}</b>"

    if not wyniki:
        return [naglowek, "   <i>— brak bezpośrednich połączeń z mapą miejsc —</i>"]

    linie = [naglowek]
    for w in wyniki:
        p = w["pociag"]
        odjazd = datetime.strptime(p["dataWyjazdu"], "%Y-%m-%d %H:%M:%S")
        przyjazd = datetime.strptime(p["dataPrzyjazdu"], "%Y-%m-%d %H:%M:%S")
        linie.append(
            f"   🚄 <b>{p['kategoriaPociagu']} {p['nrPociagu']}</b> {w['pojazd']}"
            f"  <code>{odjazd:%H:%M}→{przyjazd:%H:%M}</code>"
        )

        total_k2 = sum(len(x["wolne_miejsca"]) for x in w["klasa2"])
        linie.append(f"      {wskaznik(total_k2)} klasa 2: <b>{total_k2}</b> wolnych")
        for wg in w["klasa2"]:
            linie.append(f"        ↳ wagon {wg['wagon']}: <code>{skroc_miejsca(wg['wolne_miejsca'])}</code>")

        if w["klasa1_awaryjnie"]:
            total_k1 = sum(len(x["wolne_miejsca"]) for x in w["klasa1_awaryjnie"])
            linie.append(f"      ⚠️ <i>klasa 1 (awaryjnie)</i>: <b>{total_k1}</b> wolnych")
            for wg in w["klasa1_awaryjnie"]:
                linie.append(f"        ↳ wagon {wg['wagon']}: <code>{skroc_miejsca(wg['wolne_miejsca'])}</code>")
    return linie


def formatuj_raport(dni_wyniki: list[tuple[date, list[dict]]]) -> str:
    linie = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "🚄 <b>INTERCITY SNIFFER</b> · raport 7-dniowy",
        "Wrocław Główny ⟶ Kielce · po 17:00",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    for dzien, wyniki in dni_wyniki:
        linie.extend(formatuj_dzien(dzien, wyniki))
        linie.append("")
    return "\n".join(linie).rstrip()


def wyslij_telegram(tekst: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    # Telegram limituje wiadomość do 4096 znaków - w razie potrzeby dzielimy
    # na kawałki po granicach linii, żeby nie przecinać sformatowanego HTML w środku.
    czesci = []
    biezaca = ""
    for linia in tekst.split("\n"):
        if len(biezaca) + len(linia) + 1 > 3900:
            czesci.append(biezaca)
            biezaca = ""
        biezaca += linia + "\n"
    if biezaca.strip():
        czesci.append(biezaca)

    for czesc in czesci:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": czesc, "parse_mode": "HTML"},
            timeout=20,
            proxies={"http": None, "https": None},
        )
        resp.raise_for_status()


def main() -> None:
    try:
        with sync_playwright() as p:
            # headless=False: ebilet.intercity.pl blokuje/zawiesza połączenia
            # z headless Chromium (sprawdzone - także z --headless=new), więc
            # potrzebne jest widoczne okno przeglądarki.
            browser = p.chromium.launch(headless=False, args=["--no-proxy-server"])

            dni_wyniki = []
            for offset in range(1, DNI_DO_PRZODU + 1):
                dzien = date.today() + timedelta(days=offset)
                print(f"[{offset}/{DNI_DO_PRZODU}] sprawdzam {dzien.isoformat()}...", flush=True)
                if offset > 1:
                    time.sleep(PAUZA_MIEDZY_DNIAMI)

                context = browser.new_context()
                page = context.new_page()
                # Ładujemy prawdziwą stronę, żeby przejść wyzwanie JS Akamai
                # i dostać świeże, poprawne ciasteczka sensor dla tego dnia.
                page.goto("https://ebilet.intercity.pl/", wait_until="load", timeout=45000)
                page.wait_for_timeout(5000)

                polaczenia = search_connections(page, dzien)
                kandydaci = bezposrednie_po_17(polaczenia)
                print(f"    -> {len(kandydaci)} kandydatów (bezpośrednie, grm=1, po {MIN_GODZINA}:00)", flush=True)
                wyniki = [sprawdz_pociag(page, p_) for p_ in kandydaci]
                dni_wyniki.append((dzien, wyniki))
                context.close()

            browser.close()
        wiadomosc = formatuj_raport(dni_wyniki)
    except Exception as exc:  # noqa: BLE001 - to ma polecieć na Telegram, nie zniknąć w cronie
        wiadomosc = f"⚠️ Sprawdzanie połączeń Wrocław→Kielce nie powiodło się: {exc}"

    wyslij_telegram(wiadomosc)
    print(wiadomosc)


if __name__ == "__main__":
    sys.exit(main())
