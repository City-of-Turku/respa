from modeltranslation.translator import TranslationOptions, register

from .models import Product, CustomerGroup, ProductCustomerGroup


@register(Product)
class ProductTranslationOptions(TranslationOptions):
    fields = ('name', 'description')


@register(CustomerGroup)
class CustomerGroupTranslationOptions(TranslationOptions):
    fields = ('name', )


@register(ProductCustomerGroup)
class ProductCustomerGroupTranslationOptions(TranslationOptions):
    fields = ('name', )