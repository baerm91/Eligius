from django.contrib.admin.apps import AdminConfig


class EligiusAdminConfig(AdminConfig):
    default_site = 'slg.admin_site.EligiusAdminSite'
