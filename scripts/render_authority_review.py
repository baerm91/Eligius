"""Create a standalone, offline review page from authority proposals."""
import argparse
import json
from pathlib import Path


def render(source, output):
    report = json.loads(source.read_text(encoding='utf-8'))
    # Keep provenance with each record, omit verbose parsed response evidence.
    payload = {k: report[k] for k in ('inventory_sha256', 'generated_at', 'summary')}
    payload['proposals'] = [{k: v for k, v in row.items() if k != 'evidence'} for row in report['proposals']]
    template = Path(__file__).with_name('authority_review.html').read_text(encoding='utf-8')
    data = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    output.write_text(template.replace('/*__REVIEW_DATA__*/', data), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    render(args.source, args.output)
