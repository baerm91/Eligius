"""Reviewable UI translation drafts. Never writes files or collection data."""
import gettext
import json
import re
from collections import Counter
from pathlib import Path


CATALOG = Path(__file__).resolve().parents[1] / 'locale/en/LC_MESSAGES/django.mo'
PLACEHOLDER = re.compile(r'%\([A-Za-z_][A-Za-z_0-9]*\)s')


def get_ui_translation_catalog(user_id):
    with CATALOG.open('rb') as catalog_file:
        catalog = gettext.GNUTranslations(catalog_file)
    return {
        'language': 'en',
        'source_language': 'de',
        'path': 'slg/locale/en/LC_MESSAGES/django.po',
        'scope': 'UI only; no database values, URLs or URIs',
        'entries': [
            {'source': source, 'translation': target}
            for source, target in sorted(
                (source, target) for source, target in catalog._catalog.items()
                if isinstance(source, str) and source
            )
        ],
    }


def draft_ui_translations(user_id, translations):
    catalog = get_ui_translation_catalog(user_id)
    existing = {entry['source']: entry['translation'] for entry in catalog['entries']}
    if not translations or len(translations) > 100:
        raise ValueError('Provide between 1 and 100 UI translations.')
    changes = []
    for source, target in translations.items():
        if source not in existing:
            raise ValueError('Unknown UI source string: ' + source)
        if not isinstance(target, str) or not target.strip() or len(target) > 4000:
            raise ValueError('Translations must be nonempty text, at most 4000 characters.')
        if any(marker in target for marker in ('<', '>', '{', '}', '\x00')):
            raise ValueError('Only plain UI text is supported in this catalogue.')
        if Counter(PLACEHOLDER.findall(source)) != Counter(PLACEHOLDER.findall(target)):
            raise ValueError('Named placeholders must be preserved exactly.')
        if '%' in PLACEHOLDER.sub('', target):
            raise ValueError('Only named %(variable)s placeholders are supported.')
        changes.append({'source': source, 'before': existing[source], 'after': target})
    return {
        'status': 'draft',
        'persisted': False,
        'path': catalog['path'],
        'changes': changes,
        'po_entries': '\n\n'.join(
            'msgid ' + json.dumps(change['source'], ensure_ascii=False) + '\n'
            'msgstr ' + json.dumps(change['after'], ensure_ascii=False)
            for change in changes
        ),
        'next_step': 'Review, merge entries into the repository PO catalogue, compile messages, '
                     'test and deploy. This tool does not publish translations.',
    }
