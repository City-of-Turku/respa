from modeltranslation.translator import TranslationOptions, register

from .models import Product, CustomerGroup, OrderCustomerGroupData


@register(Product)
class ProductTranslationOptions(TranslationOptions):
    fields = ('name', 'description')


@register(CustomerGroup)
class CustomerGroupTranslationOptions(TranslationOptions):
    fields = ('name', )

@register(OrderCustomerGroupData)
class OrderCustomerGroupDataTranslationOptions(TranslationOptions):
    fields = ('customer_group_name', )