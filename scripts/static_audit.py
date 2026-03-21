#!/usr/bin/env python3
from pathlib import Path
import re

base = Path('slg/static')
tpls = list(Path('slg/templates').rglob('*.html'))
text = '\n'.join(p.read_text(errors='ignore') for p in tpls)

refs = set(re.findall(r"\{\%\s*static\s+'([^']+)'\s*\%\}", text))
refs |= set(re.findall(r'"/static/([^"]+)"', text))
refs |= set(re.findall(r"'/static/([^']+)'", text))

all_files = [p for p in base.rglob('*') if p.is_file()]
unused = []
for f in all_files:
    rel = f.relative_to(base).as_posix()
    if rel not in refs and ('/' + rel) not in refs:
        unused.append(rel)

print(f'STATIC_FILES={len(all_files)}')
print(f'REFERENCED_PATHS={len(refs)}')
print(f'POTENTIALLY_UNUSED={len(unused)}')
for u in sorted(unused):
    print(u)
