from modeltranslation.translator import TranslationOptions, register
from .models import MaintenanceMessage


@register(MaintenanceMessage)
class MaintenanceMessageTranslationOptions(TranslationOptions):
    fields = ('message', )
    required_languages = ('fi', 'en', 'sv', )
