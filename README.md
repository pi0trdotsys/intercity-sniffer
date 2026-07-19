# Intercity Sniffer

Nieoficjalne narzędzie sprawdzające wolne miejsca na połączeniach [intercity.pl](https://www.intercity.pl), z codziennym raportem na Telegram.

Trasa i godziny są ustawione na stałe w kodzie (`intercity_checker.py`) — domyślnie Wrocław Główny → Kielce, po 17:00.

## Jak to działa

- `intercity_sniff.py` — addon do [mitmproxy](https://mitmproxy.org) użyty do przechwycenia i zrozumienia wewnętrznego API intercity.pl (reverse engineering).
- `intercity_checker.py` — właściwy skrypt: co dzień sprawdza bezpośrednie połączenia na 7 dni do przodu, dla każdego pociągu pobiera mapę miejsc (klasa 2 priorytetowo, klasa 1 tylko gdy w klasie 2 brak wolnych) i wysyła zbiorczy raport przez Telegram bota.

API intercity.pl stoi za Akamai Bot Manager, więc zapytania są wykonywane z wnętrza prawdziwego (widocznego) okna Chromium przez [Playwright](https://playwright.dev) — headless jest blokowany.

## Wymagania

```
pip install playwright requests
playwright install chromium
```

## Użycie

```
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python3 intercity_checker.py
```

Do codziennego uruchamiania używany jest macOS LaunchAgent (`StartCalendarInterval`, 20:00).

### GitHub Actions - wypróbowane, nie działa

`.github/workflows/daily-check.yml` odpala checker ręcznie (`workflow_dispatch`) na `ubuntu-latest` przez `xvfb-run`. Sprawdzone empirycznie (2026-07-19): zapytania do `api-gateway.intercity.pl` failują sieciowo (`TypeError: Failed to fetch`) z adresów IP GitHub-hosted runnerów - niezależnie od obejścia headless Chromium i retry na Akamai 418. Wygląda na blokadę IP data center lub ograniczenie geograficzne, którego nie da się obejść z poziomu kodu. Workflow zostaje w repo tylko do ręcznych testów - codzienny check zostaje na macOS LaunchAgent.

## Zastrzeżenie

Projekt nieoficjalny, niezwiązany z PKP Intercity S.A. Korzysta z wewnętrznego, nieudokumentowanego API — może przestać działać w każdej chwili bez ostrzeżenia. Wyłącznie do użytku osobistego/edukacyjnego, tylko odczyt (bez rezerwacji/zakupu biletów).
