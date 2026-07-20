# 🚄 Intercity Sniffer

**Nieoficjalny watchdog wolnych miejsc na połączeniach [intercity.pl](https://www.intercity.pl) — omija ochronę antybotową Akamai, czyta mapy miejsc wprost z wewnętrznego API i wysyła dwa razy dziennie raport na Telegram (w obie strony trasy).**

![Status](https://img.shields.io/badge/status-unofficial-red)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![Playwright](https://img.shields.io/badge/browser-Playwright-45ba4b)
![mitmproxy](https://img.shields.io/badge/proxy-mitmproxy-orange)
[![Last commit](https://img.shields.io/github/last-commit/pi0trdotsys/intercity-sniffer)](https://github.com/pi0trdotsys/intercity-sniffer/commits/main)

## Dlaczego to nie jest zwykły scraper

- 🛡️ **Obejście Akamai Bot Manager** — `api-gateway.intercity.pl` odpowiada `418` zwykłym requestom, a nawet headless Chromium bywa blokowany na `ebilet.intercity.pl`. Wszystkie zapytania wykonywane są jako `fetch()` z wnętrza prawdziwego, **widocznego** okna Chromium (Playwright, `headless=False`) — dopiero jedno przejście strony daje poprawne ciasteczka/sensor Akamai.
- 🔍 **Reverse-engineered API** — wewnętrzne endpointy (wyszukiwanie połączeń, mapy miejsc SVG per wagon) odkryte przez przechwytywanie ruchu (`intercity_sniff.py`, addon do [mitmproxy](https://mitmproxy.org)).
- 🎫 **Realna dostępność, nie tylko "jest miejsce"** — parsuje SVG mapy wagonu, żeby policzyć dokładne numery wolnych miejsc: klasa 2 sprawdzana zawsze, klasa 1 tylko awaryjnie, gdy w klasie 2 zero wolnych.
- 🔁 **Świadome ryzyka antybotowego** — osobna, świeża sesja przeglądarki na każdy sprawdzany dzień (ryzyko sensor'a Akamai narasta z liczbą zapytań w jednej sesji), automatyczny retry na `418`.
- 📬 **Jeden czytelny raport, nie spam** — 7 dni do przodu w jednej wiadomości, HTML-owe formatowanie, wskaźniki 🟢🟡🔴, automatyczny podział na części przy przekroczeniu limitu 4096 znaków Telegrama.
- 🧯 **Awarie tłumaczone na ludzki** — najpopularniejsze błędy (blokada Akamai, brak sieci/DNS, timeout, zepsuty JSON) dostają czytelny opis po polsku zamiast surowego tracebacku; nierozpoznany błąd i tak trafia na Telegram z traceback w `<pre>`. Nawet jeśli wysyłka RAPORTU o błędzie też chwilowo padnie, skrypt kończy się czysto zamiast crashować bez śladu.
- 💓 **Dwie trasy = darmowy heartbeat** — ten sam skrypt sprawdza obie strony (Wrocław→Kielce i Kielce→Wrocław) o różnych porach dnia; dwa oddzielne powiadomienia w ciągu doby potwierdzają, że automatyzacja żyje, bez dodatkowego mechanizmu.
- 🕐 **Świadomość godzin pracy/snu** — pociągi odjeżdżające 00:00-16:00 (sen + praca) są odsiane całkowicie, nawet z fallbacku poniżej — i tak nie da się na nie zdążyć.
- 🎯 **Nigdy pusty raport bez potrzeby** — gdy dla danego dnia brak osiągalnego bezpośredniego połączenia z mapą miejsc po `MIN_GODZINA`, zamiast "brak połączeń" pokazuje najbliższe dostępne (wcześniej albo później, ale zawsze poza godzinami pracy/snu) z wyraźnie oznaczoną godziną odjazdu.
- 💅 **Podsumowanie tygodnia + smaczek** — suma wolnych miejsc na cały tydzień w nagłówku, a na końcu raportu losowy, złośliwy/"sigma" komentarz dobrany do tego, ile miejsc się znalazło.

## Jak to działa

1. `intercity_sniff.py` — addon do mitmproxy użyty do przechwycenia i zrozumienia wewnętrznego API intercity.pl.
2. `intercity_checker.py` — sprawdza bezpośrednie połączenia na 7 dni do przodu dla wybranej trasy (`INTERCITY_ROUTE`, patrz niżej), dla każdego pociągu pobiera mapę miejsc i wysyła zbiorczy raport przez Telegram bota.

## Trasy i harmonogram (heartbeat)

Skrypt obsługuje dwie relacje przez zmienną środowiskową `INTERCITY_ROUTE`:

| `INTERCITY_ROUTE` | Trasa | Domyślna pora uruchomienia |
|---|---|---|
| `WRO_KLC` (domyślnie) | Wrocław Główny → Kielce | 20:00 |
| `KLC_WRO` | Kielce → Wrocław Główny | 08:00 |

Dwa oddzielne LaunchAgenty (`pl.intercity.sniffer.plist` i `pl.intercity.sniffer.klcwro.plist`) uruchamiają ten sam skrypt o dwóch różnych porach — w efekcie dwa powiadomienia na dobę, ~12h od siebie, pełniące rolę heartbeatu (brak wiadomości o oczekiwanej porze = coś nie działa).

> ✅ **Kody GRM dla `KLC_WRO` zweryfikowane.** Kody stacji EVA/IBNR (wyszukiwarka połączeń) są bezpiecznie wymienne przy odwróceniu kierunku. Kody GRM (podsystem rezerwacji miejsc `wbnet`) zostały pierwotnie ustalone przez sniffing ruchu tylko dla `WRO_KLC` — hipoteza, że to kody per-stacja i można je zamienić rolami dla `KLC_WRO`, została potwierdzona ręcznym testem 2026-07-21 (pociąg IC 2606 Kielce→Wrocław: poprawny skład wagonów i 46 poprawnie sparsowanych miejsc w mapie SVG).

## Wymagania

```bash
pip install -r requirements.txt
playwright install chromium
```

## Użycie

```bash
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python3 intercity_checker.py
# albo dla trasy powrotnej:
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... INTERCITY_ROUTE=KLC_WRO python3 intercity_checker.py
```

Godzina graniczna (`MIN_GODZINA`, domyślnie 17:00) jest współdzielona przez obie trasy i ustawiona na stałe w `intercity_checker.py`. Nowe trasy dodaje się w słowniku `ROUTES` na górze pliku.

Do codziennego uruchamiania używane są dwa macOS LaunchAgenty (`StartCalendarInterval`) — patrz sekcja wyżej.

## GitHub Actions — świadomie nieużywane

[`.github/workflows/daily-check.yml`](.github/workflows/daily-check.yml) istnieje wyłącznie do ręcznych testów (`workflow_dispatch`). Sprawdzone empirycznie (2026-07-19): zapytania do `api-gateway.intercity.pl` failują sieciowo (`TypeError: Failed to fetch`) z adresów IP GitHub-hosted runnerów, niezależnie od `xvfb` i retry na `418` — wygląda na blokadę IP data center lub ograniczenie geograficzne, którego nie da się obejść z poziomu kodu. Codzienny check zostaje na macOS LaunchAgent; workflow zostaje w repo do ewentualnych testów z innego runnera/IP w przyszłości.

## Zastrzeżenie

Projekt nieoficjalny, niezwiązany z PKP Intercity S.A. Korzysta z wewnętrznego, nieudokumentowanego API — może przestać działać w każdej chwili bez ostrzeżenia. Wyłącznie do użytku osobistego/edukacyjnego, tylko odczyt (bez rezerwacji/zakupu biletów).
