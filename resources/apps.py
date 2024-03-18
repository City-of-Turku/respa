from django.apps import AppConfig
from django.utils.translation import gettext_lazy


class ResourceConfig(AppConfig):
    name = 'resources'
    verbose_name = gettext_lazy('Resource app')

    def ready(self):
        import resources.signals