# 🚄 Intercity Sniffer

**Nieoficjalny watchdog wolnych miejsc na połączeniach [intercity.pl](https://www.intercity.pl) — omija ochronę antybotową Akamai, czyta mapy miejsc wprost z wewnętrznego API i wysyła codzienny raport na Telegram.**

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
- 🧯 **Awarie też lecą na Telegram** — w razie wyjątku pełny traceback trafia jako wiadomość zamiast zniknąć w logu LaunchAgenta.

## Jak to działa

1. `intercity_sniff.py` — addon do mitmproxy użyty do przechwycenia i zrozumienia wewnętrznego API intercity.pl.
2. `intercity_checker.py` — codziennie sprawdza bezpośrednie połączenia na 7 dni do przodu, dla każdego pociągu pobiera mapę miejsc i wysyła zbiorczy raport przez Telegram bota.

## Wymagania

```bash
pip install -r requirements.txt
playwright install chromium
```

## Użycie

```bash
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python3 intercity_checker.py
```

Trasa i godzina są ustawione na stałe w `intercity_checker.py` (domyślnie Wrocław Główny → Kielce, po 17:00) — zmień `STACJA_WYJAZDU` / `STACJA_PRZYJAZDU` / `MIN_GODZINA`, żeby dopasować pod swoje połączenie.

Do codziennego uruchamiania używany jest macOS LaunchAgent (`StartCalendarInterval`, 20:00).

## GitHub Actions — świadomie nieużywane

[`.github/workflows/daily-check.yml`](.github/workflows/daily-check.yml) istnieje wyłącznie do ręcznych testów (`workflow_dispatch`). Sprawdzone empirycznie (2026-07-19): zapytania do `api-gateway.intercity.pl` failują sieciowo (`TypeError: Failed to fetch`) z adresów IP GitHub-hosted runnerów, niezależnie od `xvfb` i retry na `418` — wygląda na blokadę IP data center lub ograniczenie geograficzne, którego nie da się obejść z poziomu kodu. Codzienny check zostaje na macOS LaunchAgent; workflow zostaje w repo do ewentualnych testów z innego runnera/IP w przyszłości.

## Zastrzeżenie

Projekt nieoficjalny, niezwiązany z PKP Intercity S.A. Korzysta z wewnętrznego, nieudokumentowanego API — może przestać działać w każdej chwili bez ostrzeżenia. Wyłącznie do użytku osobistego/edukacyjnego, tylko odczyt (bez rezerwacji/zakupu biletów).
