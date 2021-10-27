from modeltranslation.translator import TranslationOptions, register

from .models import Product, CustomerGroup


@register(Product)
class ProductTranslationOptions(TranslationOptions):
    fields = ('name', 'description')


@register(CustomerGroup)
class CustomerGroupTranslationOptions(TranslationOptions):
    fields = ('name', )