from django.apps import AppConfig


class SlgConfig(AppConfig):
    name = 'slg'

    def ready(self):
        import slg.signals  # noqa: F401
