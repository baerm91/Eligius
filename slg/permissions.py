"""Berechtigungsklassen für die Eligius-REST-API.

Grundsatz:
* Lesende Zugriffe (GET/HEAD/OPTIONS) bleiben wie bisher geregelt
  (authentifiziert bzw. öffentlich).
* Schreibende Zugriffe (POST/PUT/PATCH/DELETE) erfordern einen aktiven
  Staff-Account *und* die passende Django-Model-Permission
  (``add_*``/``change_*``/``delete_*``), analog zum Django-Admin.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


WRITE_PERMS_MAP = {
    'POST': ['%(app_label)s.add_%(model_name)s'],
    'PUT': ['%(app_label)s.change_%(model_name)s'],
    'PATCH': ['%(app_label)s.change_%(model_name)s'],
    'DELETE': ['%(app_label)s.delete_%(model_name)s'],
}


def is_active_staff(user):
    return bool(
        user
        and getattr(user, 'is_authenticated', False)
        and getattr(user, 'is_active', False)
        and getattr(user, 'is_staff', False)
    )


def _view_model(view):
    queryset = getattr(view, 'queryset', None)
    if queryset is None and hasattr(view, 'get_queryset'):
        try:
            queryset = view.get_queryset()
        except Exception:
            queryset = None
    return getattr(queryset, 'model', None)


def required_write_perms(view, method):
    """Ermittelt die für ``method`` benötigten Permissions.

    Views können ``required_write_permissions`` setzen – entweder als Liste
    (gilt für alle schreibenden Methoden) oder als Dict ``{METHOD: [...]}``.
    Ansonsten wird die Permission aus dem Queryset-Modell abgeleitet.
    Gibt ``None`` zurück, wenn sich nichts ermitteln lässt (=> verweigern).
    """
    explicit = getattr(view, 'required_write_permissions', None)
    if explicit is not None:
        if isinstance(explicit, dict):
            perms = explicit.get(method)
            return list(perms) if perms is not None else None
        return list(explicit)

    model = _view_model(view)
    if model is None or method not in WRITE_PERMS_MAP:
        return None
    kwargs = {'app_label': model._meta.app_label, 'model_name': model._meta.model_name}
    return [perm % kwargs for perm in WRITE_PERMS_MAP[method]]


class _StaffModelWriteMixin:
    allow_anonymous_read = False

    def has_permission(self, request, view):
        user = request.user
        if request.method in SAFE_METHODS:
            if self.allow_anonymous_read:
                return True
            return bool(user and user.is_authenticated)

        if not is_active_staff(user):
            return False
        perms = required_write_perms(view, request.method)
        if perms is None:
            # Keine Permission ableitbar: nur Superuser dürfen schreiben.
            return bool(user.is_superuser)
        return user.has_perms(perms)


class AuthenticatedReadStaffModelWrite(_StaffModelWriteMixin, BasePermission):
    """Lesen: eingeloggt. Schreiben: aktiver Staff + Model-Permission."""


class PublicReadStaffModelWrite(_StaffModelWriteMixin, BasePermission):
    """Lesen: öffentlich. Schreiben: aktiver Staff + Model-Permission."""

    allow_anonymous_read = True


def staff_with_perms(*perms):
    """Permission-Klasse für Views ohne Queryset.

    Beispiel: ``@permission_classes([staff_with_perms('slg.change_muenztyp')])``
    """

    class _StaffWithPerms(BasePermission):
        required = tuple(perms)

        def has_permission(self, request, view):
            user = request.user
            return is_active_staff(user) and user.has_perms(self.required)

    _StaffWithPerms.__name__ = 'StaffWithPerms(%s)' % ','.join(perms)
    return _StaffWithPerms
