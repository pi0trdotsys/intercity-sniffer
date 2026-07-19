#!/usr/bin/env python3
"""
Przechwytuje requesty API intercity.pl przez mitmproxy.

Użycie:
    pip install mitmproxy
    mitmdump -s intercity_sniff.py --listen-port 8080 --ssl-insecure

Następnie w Dia (lub systemowych ustawieniach sieci na Macu):
    Proxy HTTP/HTTPS: 127.0.0.1:8080

Wejdź na intercity.pl, wyszukaj połączenie Wrocław→Kielce,
kliknij w jeden pociąg żeby zobaczyć miejsca.

Skrypt zapisuje znalezione requesty do intercity_api_log.json
"""

import json
import re
from mitmproxy import http

INTERESTING = re.compile(
    r"(^https?://)?([\w-]+\.)*intercity\.pl",
    re.IGNORECASE,
)

STATIC_EXT = re.compile(
    r"\.(png|jpe?g|svg|gif|webp|ico|css|woff2?|ttf|map)(\?|$)",
    re.IGNORECASE,
)

found: list[dict] = []


class InterceptIntercity:
    def response(self, flow: http.HTTPFlow) -> None:
        url = flow.request.pretty_url

        if not INTERESTING.search(url):
            return
        if STATIC_EXT.search(url):
            return

        entry = {
            "method":      flow.request.method,
            "url":         url,
            "query":       dict(flow.request.query),
            "req_headers": dict(flow.request.headers),
            "req_body":    flow.request.get_text(strict=False) or "",
            "status":      flow.response.status_code,
            "res_headers": dict(flow.response.headers),
            "res_body":    flow.response.get_text(strict=False) or "",
        }

        found.append(entry)

        print("\n" + "═" * 70)
        print(f"  {entry['method']}  {url}")
        print(f"  Status: {entry['status']}")
        if entry["query"]:
            print(f"  Query:  {json.dumps(entry['query'], ensure_ascii=False)}")
        if entry["req_body"]:
            print(f"  Body:   {entry['req_body'][:300]}")
        print(f"  Response ({len(entry['res_body'])} chars):")
        print(f"  {entry['res_body'][:500]}")
        print("═" * 70)

        # Zapisz do pliku na bieżąco
        with open("intercity_api_log.json", "w", encoding="utf-8") as f:
            json.dump(found, f, ensure_ascii=False, indent=2)


addons = [InterceptIntercity()]
