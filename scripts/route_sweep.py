#!/usr/bin/env python3
import os
import sys
from pathlib import Path
import django
from django.test import Client

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoproject.settings')
django.setup()

client = Client()

URLS = [
    '/', '/api/', '/about/', '/browse/', '/browse_legacy/', '/timeline/',
    '/admin/login/?next=/admin/',
    '/api/collections/', '/api/stats/', '/api/sammlungen/', '/api/facet/?facet=Nominal',
    '/api/ereignisse/', '/api/adjacent-invnrs/?invnr=1-1-1&slg_id=1',
    '/api/muenzen/1/kontext/', '/api/cycle-coin/?type_id=1504&current_obj_id=1&direction=next',
    '/export_xlsx/?id__exact=1', '/ajax/get-konkordanzen/?typ=1',
]

failed = []
for u in URLS:
    r = client.get(u)
    print(f"{u} -> {r.status_code}")
    if r.status_code >= 500:
        failed.append((u, r.status_code))

if failed:
    print("\nFAILED:")
    for u, s in failed:
        print(f"- {u}: {s}")
    raise SystemExit(1)

print("\nAll sweep routes returned < 500")
