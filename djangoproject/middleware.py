from django.conf import settings


ROBOTS_NOINDEX = 'noindex, nofollow'


class RobotsTagMiddleware:
    """Apply the deployment's indexing policy to all Django responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not settings.ELIGIUS_SEO_INDEXING:
            response['X-Robots-Tag'] = ROBOTS_NOINDEX
        return response
