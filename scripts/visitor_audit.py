#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time

BASE = 'http://127.0.0.1:8014'
PAGES = [
    '/', '/about/', '/browse/', '/timeline/', '/api/',
    '/kontakt/', '/api/collections/', '/api/stats/', '/api/sammlungen/'
]

broken = []
slow = []
asset_urls = set()

for p in PAGES:
    url = urljoin(BASE, p)
    try:
        t0 = time.time()
        r = requests.get(url, timeout=30)
        dt = time.time() - t0
        if dt > 2.5:
            slow.append((p, round(dt, 2), r.status_code))
        if r.status_code >= 400:
            broken.append((p, r.status_code, 'page'))
            continue
        ct = (r.headers.get('content-type') or '').lower()
        if 'text/html' in ct:
            soup = BeautifulSoup(r.text, 'html.parser')
            for tag, attr in [('link', 'href'), ('script', 'src'), ('img', 'src')]:
                for el in soup.find_all(tag):
                    v = el.get(attr)
                    if not v:
                        continue
                    full = urljoin(url, v)
                    if urlparse(full).netloc == urlparse(BASE).netloc:
                        asset_urls.add(full)
    except Exception as e:
        broken.append((p, 'EXC', str(e)))

for a in sorted(asset_urls):
    try:
        r = requests.get(a, timeout=20)
        if r.status_code >= 400:
            broken.append((a, r.status_code, 'asset'))
    except Exception as e:
        broken.append((a, 'EXC', str(e)))

print('PAGES', len(PAGES))
print('ASSETS', len(asset_urls))
print('SLOW_COUNT', len(slow))
for s in slow:
    print('SLOW', s)
print('BROKEN_COUNT', len(broken))
for b in broken:
    print('BROKEN', b)
