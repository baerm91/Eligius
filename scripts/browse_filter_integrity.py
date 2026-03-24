#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from django.test import Client, RequestFactory

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoproject.settings')
import django

django.setup()

from slg.models import MuenztypObjektAnzeige
from slg.views import _get_filtered_mtoa_queryset


def get_first_value(qs, field):
    val = qs.exclude(**{f"{field}__isnull": True}).values_list(field, flat=True).first()
    if isinstance(val, str):
        val = val.strip()
    return val if val not in (None, "") else None


def parse_count(html):
    m = re.search(r"Anzahl der Objekte:\s*([0-9]+)", html)
    return int(m.group(1)) if m else None


def expected_count(params):
    rf = RequestFactory()
    req = rf.get('/browse/', data=params)
    qs, _, _ = _get_filtered_mtoa_queryset(req)
    return qs.count()


def check_case(client, params, label):
    url = '/browse/?' + urlencode(params, doseq=True)
    r = client.get(url)
    if r.status_code != 200:
        return False, f"{label}: HTTP {r.status_code} for {url}"

    html = r.content.decode('utf-8', 'ignore')
    shown = parse_count(html)
    exp = expected_count(params)
    if shown is None:
        return False, f"{label}: count not found in HTML"
    if shown != exp:
        return False, f"{label}: count mismatch shown={shown}, expected={exp}, params={params}"

    # Tag links (remove one filter value)
    tag_links = re.findall(r'class="btn btn-outline-secondary btn-sm"\s*>|class="btn btn-outline-secondary btn-sm"', html)
    if params and not tag_links:
        return False, f"{label}: no filter tags rendered for active params {params}"

    # Find first remove link href and validate reduced expected count
    hrefs = re.findall(r'<a href="([^"]+)" rel="tag" class="btn btn-outline-secondary btn-sm">', html)
    if hrefs:
        href = hrefs[0]
        # Resolve relative href
        reduced_qs = parse_qs(urlparse(href).query)
        # flatten single values
        reduced_params = {k: v if len(v) > 1 else v[0] for k, v in reduced_qs.items()}
        r2 = client.get('/browse/?' + urlencode(reduced_params, doseq=True)) if reduced_params else client.get('/browse/')
        if r2.status_code != 200:
            return False, f"{label}: remove-tag target failed {r2.status_code} href={href}"
        shown2 = parse_count(r2.content.decode('utf-8', 'ignore'))
        exp2 = expected_count(reduced_params)
        if shown2 != exp2:
            return False, f"{label}: remove-tag mismatch shown={shown2}, expected={exp2}, reduced={reduced_params}"

    return True, f"{label}: OK (count={shown}, expected={exp})"


def main():
    client = Client()
    qs = MuenztypObjektAnzeige.objects.all()

    # Build sample filter values from current DB
    samples = {
        'Slg': get_first_value(qs, 'slg_fk_id'),
        'Muenzstaette': get_first_value(qs, 'mzstaette'),
        'Nominal': get_first_value(qs, 'nominal'),
        'material': get_first_value(qs, 'metall'),
        'av_bildtyp': get_first_value(qs, 'av_bildtyp_fk_id'),
        'rv_bildtyp': get_first_value(qs, 'rv_bildtyp_fk_id'),
        'obj_type': get_first_value(qs, 'objekttyp'),
    }

    # Remove empty samples
    samples = {k: v for k, v in samples.items() if v not in (None, "")}

    cases = []
    # single filters
    for k, v in samples.items():
        cases.append((f"single:{k}", {k: v}))

    # combined filters
    keys = list(samples.keys())
    if len(keys) >= 2:
        cases.append(("combo:Slg+Muenzstaette", {k: samples[k] for k in keys[:2]}))
    if len(keys) >= 3:
        cases.append(("combo:3-filters", {k: samples[k] for k in keys[:3]}))

    # date range from data
    min_year = qs.exclude(datierung_von__isnull=True).order_by('datierung_von').values_list('datierung_von', flat=True).first()
    max_year = qs.exclude(datierung_bis__isnull=True).order_by('-datierung_bis').values_list('datierung_bis', flat=True).first()
    if min_year is not None and max_year is not None:
        mid = int((min_year + max_year) / 2)
        cases.append(("date-range", {'dat_von': min_year, 'dat_bis': mid}))

    failures = 0
    for label, params in cases:
        ok, msg = check_case(client, params, label)
        print(msg)
        if not ok:
            failures += 1

    # reset behavior
    r = client.get('/browse/?' + urlencode(cases[0][1], doseq=True)) if cases else client.get('/browse/')
    html = r.content.decode('utf-8', 'ignore')
    if 'href="."' not in html:
        print('reset-link: FAIL (missing reset link)')
        failures += 1
    else:
        r_reset = client.get('/browse/')
        if r_reset.status_code == 200 and parse_count(r_reset.content.decode('utf-8', 'ignore')) is not None:
            print('reset-link: OK')
        else:
            print('reset-link: FAIL (reset target invalid)')
            failures += 1

    if failures:
        print(f"\nFAILURES: {failures}")
        sys.exit(1)
    print("\nAll browse filter integrity checks passed.")


if __name__ == '__main__':
    main()
