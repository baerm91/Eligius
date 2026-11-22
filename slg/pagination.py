from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination


class OptInPageNumberPagination(PageNumberPagination):
    """Keep the existing array response unless the client requests a page."""

    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 500
    template = None

    def paginate_queryset(self, queryset, request, view=None):
        params = request.query_params
        if self.page_query_param not in params and self.page_size_query_param not in params:
            return None

        # A unique order prevents ties from shifting between pages.
        return super().paginate_queryset(queryset.order_by('pk'), request, view)

    def get_page_size(self, request):
        value = request.query_params.get(self.page_size_query_param)
        if value is None:
            return self.page_size
        try:
            size = int(value)
        except ValueError:
            size = 0
        if size < 1:
            raise ValidationError({self.page_size_query_param: 'Enter a positive integer.'})
        return min(size, self.max_page_size)
