from modeltranslation.translator import TranslationOptions, register
from accessibility.models import (
    ServicePoint,
    ServiceShortage,
    ServiceRequirement,
    ServiceEntrance,
    ServiceSentence,
    SentenceGroup,
    Sentence
)



@register(ServicePoint)
class ServicePointTranslationOptions(TranslationOptions):
    fields = ('name', )

@register(ServiceShortage)
class ServiceShortageTranslationOptions(TranslationOptions):
    fields = ('shortage', )

@register(ServiceRequirement)
class ServiceRequirementTranslationOptions(TranslationOptions):
    fields = ('text', )

@register(ServiceEntrance)
class ServiceEntranceTranslationOptions(TranslationOptions):
    fields = ('name', )

@register(ServiceSentence)
class ServiceSentenceTranslationOptions(TranslationOptions):
    fields = ('sentence_order_text', )

@register(SentenceGroup)
class SentenceGroupTranslationOptions(TranslationOptions):
    fields = ('name', )

@register(Sentence)
class SentenceTranslationOptions(TranslationOptions):
    fields = ('sentence', )