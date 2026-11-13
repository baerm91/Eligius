from django.apps import AppConfig


class SlgConfig(AppConfig):
    name = 'slg'

    def ready(self):
        import slg.signals  # noqa: F401
        from django.db.models.signals import post_save, post_delete
        from slg.services.authority_display import clear_display_cache
        post_save.connect(clear_display_cache, dispatch_uid='authority_display_save')
        post_delete.connect(clear_display_cache, dispatch_uid='authority_display_delete')
