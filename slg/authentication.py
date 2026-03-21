from typing import Iterable

from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class QueryParamTokenAuthentication(TokenAuthentication):
    """
    Allow DRF token authentication via query parameters in addition to the
    standard Authorization header.

    This is useful for deployments where upstream proxies or web servers strip
    the Authorization header, but the client can still append the token to the
    request URL (e.g. ?auth_token=<key>).
    """

    query_param_names: Iterable[str] = ("auth_token", "token")

    def authenticate(self, request):
        for param in self.query_param_names:
            token = request.query_params.get(param)
            if token:
                token = token.strip()
                if not token:
                    continue
                return self.authenticate_credentials(token)

        # Fallback to the standard header-based authentication.
        try:
            return super().authenticate(request)
        except AuthenticationFailed:
            # Re-raise to ensure consistent error responses
            raise
