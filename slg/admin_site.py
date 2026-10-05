from django.contrib.admin import AdminSite
from django.urls import reverse
from django.utils.http import urlencode

from .models import Kontaktanfrage, ObjektAenderung


OBJECT_CHANGE_FIELD_LABELS = {
    'titel': 'Titel',
    'avleg': 'Vorderseite Legende',
    'rvleg': 'Rückseite Legende',
    'avbeschr': 'Vorderseite Beschreibung',
    'rvbeschr': 'Rückseite Beschreibung',
    'material': 'Material',
    'gewicht': 'Gewicht',
    'durchmesser': 'Durchmesser',
    'datierung': 'Datierung',
    'sonstiges': 'Sonstiges',
}


class EligiusAdminSite(AdminSite):
    index_template = 'admin/contact_dashboard.html'

    def index(self, request, extra_context=None):
        context = dict(extra_context or {})
        if self.has_permission(request) and request.user.get_username() == 'goffo':
            for model, context_key, filters in (
                (Kontaktanfrage, 'contact_dashboard', {'bearbeitet__exact': '0'}),
                (ObjektAenderung, 'object_change_dashboard', {'status__exact': 'offen'}),
            ):
                model_admin = self._registry.get(model)
                if (
                    model_admin is None
                    or not model_admin.has_module_permission(request)
                    or not model_admin.has_view_or_change_permission(request)
                ):
                    continue

                entries = model_admin.get_queryset(request).filter(**filters)
                latest = entries.order_by('-erstellt_am', '-pk')[:5]
                if model is ObjektAenderung:
                    latest = latest.select_related('objekt')
                    for change in latest:
                        change.field_label = OBJECT_CHANGE_FIELD_LABELS.get(change.feld, change.feld)

                context[context_key] = {
                    'count': entries.count(),
                    'latest': latest,
                    'list_url': '{}?{}'.format(
                        reverse(
                            f'admin:{model._meta.app_label}_{model._meta.model_name}_changelist',
                            current_app=self.name,
                        ),
                        urlencode(filters),
                    ),
                }
        return super().index(request, extra_context=context)
