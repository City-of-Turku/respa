from modeltranslation.translator import TranslationOptions, register
from qualitytool.models import ResourceQualityTool



@register(ResourceQualityTool)
class ResourceQualityToolTranslationOptions(TranslationOptions):
    fields = ('name', )
