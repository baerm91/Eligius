"""Isolated, disposable test database; never connects to the development DB."""
from .settings import *

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
# Legacy MySQL migrations contain platform-specific SQL. Build model fixtures
# directly for portable service tests; verify MySQL separately on Development.
MIGRATION_MODULES = {'slg': None}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
ELIGIUS_PUBLIC_BASE_URL = 'https://example.test'
ELIGIUS_MCP_ENABLED = True
ELIGIUS_EDITOR_MCP_ENABLED = True
ELIGIUS_MCP_ALLOWED_HOSTS = ['testserver', 'localhost:*', '127.0.0.1:*']
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
