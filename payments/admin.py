from django import forms
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.utils.safestring import mark_safe
from django.utils.timezone import localtime
from django.utils.translation import ugettext_lazy as _
from modeltranslation.admin import TranslationAdmin

from payments.utils import get_price_period_display
from resources.models import Resource

from .models import (
    ARCHIVED_AT_NONE, CustomerGroupTimeSlotPrice, Order, OrderCustomerGroupData, OrderLine, OrderLogEntry,
    Product, CustomerGroup, ProductCustomerGroup, TimeSlotPrice
)


def get_datetime_display(dt):
    if not dt:
        return None
    return localtime(dt).strftime('%d %b %Y %H:%M:%S')


class CustomerGroupTimeSlotPriceInline(admin.TabularInline):
    model = CustomerGroupTimeSlotPrice
    fields = ('price', 'customer_group')
    extra = 0
    can_delete = True


class TimeSlotPriceAdmin(admin.ModelAdmin):
    inlines = (CustomerGroupTimeSlotPriceInline, )
    class Meta:
        model = TimeSlotPrice
        fields = '__all__'


class TimeSlotPriceInlineFormSet(BaseInlineFormSet):
    def save_existing_objects(self, commit=True):
        for form in self.initial_forms:
            # time slot price has old archived product here, update product to the new one
            obj = form.instance
            new_product = Product.objects.filter(product_id=obj.product.product_id).get(archived_at=ARCHIVED_AT_NONE)
            obj.product = new_product
            obj.save()
        saved_instances = super(TimeSlotPriceInlineFormSet, self).save_existing_objects(commit)
        return saved_instances


class TimeSlotPriceInline(admin.TabularInline):
    model = TimeSlotPrice
    fields = ('begin', 'end', 'price', 'customer_group_time_slot_prices')
    readonly_fields = ('customer_group_time_slot_prices', )
    extra = 0
    can_delete = True
    show_change_link = True
    formset = TimeSlotPriceInlineFormSet

    def customer_group_time_slot_prices(self, obj):
        cg_time_slot_prices = CustomerGroupTimeSlotPrice.objects.filter(time_slot_price=obj.id)
        return ", ".join([cg_slot.customer_group.name for cg_slot in cg_time_slot_prices])


class CustomerGroupAdmin(TranslationAdmin):
    fields = ('name', )


class ProductCustomerGroupAdmin(admin.ModelAdmin):
    def render_change_form(self, request, context, *args, **kwargs):
        context['adminform'].form.fields['product'].queryset = Product.objects.current()
        return super().render_change_form(request, context, *args, **kwargs)


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['resources'] = forms.ModelMultipleChoiceField(queryset=Resource.objects.order_by('name'))



class ProductCGInlineFormSet(BaseInlineFormSet):
    def save_existing_objects(self, commit=True):
        saved_instances = super(ProductCGInlineFormSet, self).save_existing_objects(commit)
        # product customer group has old archived product here, update product to the new one
        for product_cg in saved_instances:
            new_product = Product.objects.filter(product_id=product_cg.product.product_id).get(archived_at=ARCHIVED_AT_NONE)
            product_cg.product = new_product
            product_cg.save()

        return saved_instances


class ProductCustomerGroupInline(admin.TabularInline):
    model = ProductCustomerGroup
    fields = ('id', 'customer_group', 'price', )
    extra = 0
    can_delete = True
    show_change_link = True
    formset = ProductCGInlineFormSet


class ProductAdmin(TranslationAdmin):
    inlines = (
        TimeSlotPriceInline,
        ProductCustomerGroupInline,
    )

    list_display = (
        'product_id', 'sku', 'sap_code', 'sap_unit', 'name', 'type', 'price', 'price_type', 'get_price_period', 'tax_percentage',
        'max_quantity', 'get_resources', 'get_created_at', 'get_modified_at'
    )
    readonly_fields = ('product_id',)
    fieldsets = (
        (None, {
            'fields': ('sku', 'type', 'name', 'description', 'max_quantity')
        }),
        ('SAP', {
            'fields': ('sap_code', 'sap_unit'),
        }),
        (_('price').capitalize(), {
            'fields': ('price', 'price_type', 'price_period', 'tax_percentage', ),
        }),
        (_('resources').capitalize(), {
            'fields': ('resources',)
        }),
    )
    ordering = ('-product_id',)
    form = ProductForm

    def get_resources(self, obj):
        return mark_safe('<br>'.join([str(r) for r in obj.resources.all()]))

    get_resources.short_description = _('resources')

    def get_created_at(self, obj):
        return Product.objects.filter(product_id=obj.product_id).first().created_at

    get_created_at.short_description = _('created at')

    def get_modified_at(self, obj):
        return obj.created_at

    get_modified_at.short_description = _('modified at')

    def get_queryset(self, request):
        return super().get_queryset(request).current()

    def change_view(self, request, object_id, form_url='', extra_context=None):
        # disable "save and continue editing" button since it does not work
        # because of the Product versioning stuff
        extra_context = extra_context or {}
        extra_context['show_save_and_continue'] = False
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def get_price_period(self, obj):
        return get_price_period_display(obj.price_period)

    get_price_period.short_description = _('price period')


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    fields = ('product', 'product_type', 'unit_price', 'quantity', 'price', 'tax_percentage', 'customer_group')
    extra = 0
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj):
        return False

    def product_type(self, obj):
        return obj.product.type

    product_type.short_description = _('product type')

    def price(self, obj):
        return obj.get_price()

    price.short_description = _('price including VAT')

    def unit_price(self, obj):
        return obj.get_unit_price()

    unit_price.short_description = _('unit price')

    def tax_percentage(self, obj):
        return obj.product.tax_percentage

    tax_percentage.short_description = _('tax percentage')

    def customer_group(self, obj):
        order_cg = OrderCustomerGroupData.objects.filter(order_line=obj).first()
        return order_cg.customer_group_name if order_cg and order_cg.customer_group_name else _('None')

    customer_group.short_description = _('selected customer group')


class OrderLogEntryInline(admin.TabularInline):
    model = OrderLogEntry
    extra = 0
    readonly_fields = ('timestamp_with_seconds', 'state_change', 'message')
    can_delete = False

    def has_add_permission(self, request, obj):
        return False

    def timestamp_with_seconds(self, obj):
        return get_datetime_display(obj.timestamp)

    timestamp_with_seconds.short_description = _('timestamp')

class OrderCustomerGroupDataInline(admin.TabularInline):
    model = OrderCustomerGroupData
    extra = 1
    fields = ('customer_group_name', 'product_cg_price', )
    readonly_fields = fields
    can_delete = False
    verbose_name = "Selected customer group"
    verbose_name_plural = "Selected customer group"
    max_num = 0

    def has_add_permission(self, request, obj):
        return False

    def customer_group_name(self, obj):
        return obj.customer_group_name
    customer_group_name.short_description = _('customer group')

    def product_cg_price(self, obj):
        return obj.product_cg_price
    product_cg_price.short_description = _('product price')

class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'user', 'created_at', 'state', 'reservation', 'price', 'customer_group')

    fields = ('order_number', 'created_at', 'state', 'reservation', 'user', 'price', 'customer_group')

    raw_id_fields = ('reservation',)
    inlines = (OrderLineInline, OrderLogEntryInline, )
    ordering = ('-id',)
    search_fields = ('order_number',)
    list_filter = ('state',)

    actions = None

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields if f.name != 'id'] + [
            'user', 'created_at', 'price', 'tax_amount', 'pretax_price'
        ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        if obj and obj.state == Order.CONFIRMED:
            return True
        return False

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_save_and_continue'] = False
        extra_context['show_save'] = False
        return super().changeform_view(request, object_id, extra_context=extra_context)

    def delete_model(self, request, obj):
        obj.set_state(Order.CANCELLED, log_message='Cancelled using the Django admin UI.')

    def user(self, obj):
        return obj.reservation.user

    user.short_description = _('user')

    def price(self, obj):
        return obj.get_price()

    price.short_description = _('price including VAT')

    def created_at(self, obj):
        return get_datetime_display(obj.created_at)

    created_at.short_description = _('created at')


if settings.RESPA_PAYMENTS_ENABLED:
    admin.site.register(Product, ProductAdmin)
    admin.site.register(Order, OrderAdmin)
    admin.site.register(CustomerGroup, CustomerGroupAdmin)
    admin.site.register(ProductCustomerGroup, ProductCustomerGroupAdmin)
    admin.site.register(TimeSlotPrice, TimeSlotPriceAdmin)
