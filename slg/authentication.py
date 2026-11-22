from typing import Iterable

from django.conf import settings
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class QueryParamTokenAuthentication(TokenAuthentication):
    """
    Token-Authentifizierung über Header – optional (Legacy) auch per Query-Param.

    Unterstützt werden:
    * ``Authorization: Token <key>`` (Standard)
    * ``X-Auth-Token: <key>`` für Umgebungen, in denen ein Proxy den
      Authorization-Header entfernt
    * ``?auth_token=<key>`` / ``?token=<key>`` **nur**, wenn
      ``ELIGIUS_ALLOW_QUERY_PARAM_TOKEN_AUTH`` aktiv ist. Tokens in URLs landen
      in Logs, Browser-History und Referer-Headern und sind daher standardmäßig
      deaktiviert.
    """

    query_param_names: Iterable[str] = ("auth_token", "token")
    header_name = "HTTP_X_AUTH_TOKEN"

    def authenticate(self, request):
        header_token = (request.META.get(self.header_name) or "").strip()
        if header_token:
            if " " in header_token:
                raise exceptions.AuthenticationFailed("Invalid token header.")
            return self.authenticate_credentials(header_token)

        if getattr(settings, "ELIGIUS_ALLOW_QUERY_PARAM_TOKEN_AUTH", False):
            for param in self.query_param_names:
                token = (request.query_params.get(param) or "").strip()
                if token:
                    return self.authenticate_credentials(token)

        # Fallback to the standard header-based authentication.
        try:
            return super().authenticate(request)
        except AuthenticationFailed:
            # Re-raise to ensure consistent error responses
            raise
