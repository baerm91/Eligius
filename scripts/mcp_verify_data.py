"""Read-only parity audit against the configured Development database.

Optional --baseline-views PATH compares against the pre-deployment Browse code.
Run from project root with the same environment as Django. No database writes.
"""
import argparse
import ast
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoproject.settings')
import django
django.setup()

from slg.services import public_api, search
from slg.models import MuenztypObjektAnzeige


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline-views')
    args = parser.parse_args()
    baseline = search._get_filtered_mtoa_queryset
    if args.baseline_views:
        tree = ast.parse(Path(args.baseline_views).read_text())
        names = {'MTOA_FILTERS', 'MTOA_FACETS', '_get_filtered_mtoa_queryset'}
        nodes = [n for n in tree.body if
                 (isinstance(n, ast.FunctionDef) and n.name in names) or
                 (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets))]
        namespace = vars(search).copy()
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<baseline>', 'exec'), namespace)
        baseline = namespace['_get_filtered_mtoa_queryset']

    example = MuenztypObjektAnzeige.objects.filter(
        mtoaperson__person__name='Valens', mtoaperson__funktion_id__in=[1, 6, 7]).first()
    assert example, 'Valens ruler example required for this dataset audit.'
    cases = [
        {'Praegeherren': ['Valens']},
        {'Praegeherren': ['Valens'], 'Muenzstaette': ['Siscia']},
        {'Praegeherren': ['Valens'], 'Muenzstaette': ['Siscia'], 'Nominal': [example.nominal]},
        {'Praegeherren': ['Pescennius Niger']},
        {'rv_schlagwort': ['Victoria']},
        {'Slg': [example.slg_fk_id]},
        {'Slg': [example.slg_fk_id], 'Praegeherren': ['Valens']},
        {'dat_von': 364, 'dat_bis': 378},
        {'unbestimmt': True, 'Slg': [example.slg_fk_id]},
        {'Dargestellte_AV': ['Valens'], 'Muenzstaette': ['Siscia']},
    ]
    for filters in cases:
        request = public_api.filter_request(filters)
        old, _, _ = baseline(request)
        rows, _, _ = search._get_filtered_mtoa_queryset(request)
        expected = set(old.values_list('obj_id', flat=True))
        actual = set(rows.values_list('obj_id', flat=True))
        assert expected == actual, (filters, 'baseline mismatch', len(expected), len(actual))
        found = set()
        page = 1
        while True:
            result = public_api.search_objects(filters, page, 100)
            ids = {obj['id'] for obj in result['results']}
            assert not found & ids, 'duplicate page IDs'
            found.update(ids)
            if not result['has_more']:
                break
            page += 1
        assert found == expected, (filters, 'MCP mismatch')
        assert public_api.get_statistics(filters)['total'] == len(found)
        print('PASS', filters, 'objects=', len(found), 'pages=', page, flush=True)
    for facet in sorted(set().union(*(set(c) for c in public_api.FILTER_PARAMETERS.values())) - {'q', 'invnr'}):
        result = public_api.get_facets(facet, {'Slg': [example.slg_fk_id]}, page_size=1)
        print('FACET', facet, result['total'], flush=True)


if __name__ == '__main__':
    main()
