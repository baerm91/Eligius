"""Language preference without reversing or translating existing URLs."""
from django.conf import settings
from django.http import HttpResponseBadRequest
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.i18n import set_language


@require_POST
def switch_language(request):
    if request.POST.get('language') not in dict(settings.LANGUAGES):
        return HttpResponseBadRequest('Unsupported language')
    target = request.POST.get('next') or request.headers.get('Referer') or '/'
    if not url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        target = '/'
    # Delegate language validation and cookie policy to Django. Its translate_url()
    # can reverse duplicate route names to /api/; preserve the supplied path verbatim.
    response = set_language(request)
    response.status_code = 302
    response['Location'] = target
    return response
