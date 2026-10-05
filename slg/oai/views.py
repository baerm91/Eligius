from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .service import respond


@csrf_exempt  # OAI form POST is read-only and must work for unauthenticated harvesters.
@require_http_methods(['GET', 'POST'])
def oai_endpoint(request):
    query = request.GET if request.method == 'GET' else request.POST.copy()
    if request.method == 'POST':
        # Preserve duplicates across URL and form arguments for strict validation.
        for key, values in request.GET.lists():
            query.setlist(key, query.getlist(key) + values)
        if request.content_type != 'application/x-www-form-urlencoded':
            query['unsupportedContentType'] = request.content_type or 'missing'
    response = HttpResponse(respond(query, request), content_type='text/xml; charset=utf-8')
    # No stale permission decisions or datestamps, including at upstream caches.
    response['Cache-Control'] = 'no-store'
    return response
