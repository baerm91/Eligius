"""Browser smoke database on disk so concurrent HTTP requests get separate connections."""
from pathlib import Path
from tempfile import TemporaryDirectory

from .test_settings import *

_browser_database = TemporaryDirectory(prefix='eligius-browser-')
DATABASES['default']['TEST'] = {'NAME': str(Path(_browser_database.name) / 'smoke.sqlite3')}
