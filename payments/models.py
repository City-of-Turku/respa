from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction, DatabaseError
from django.db.models import Case, DateTimeField, ExpressionWrapper, F, OuterRef, Q, Subquery, When
from django.utils import translation
from django.utils.formats import localize
from django.utils.functional import cached_property
from django.utils.timezone import now, utc
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from resources.models import Reservation, Resource
from resources.models.base import AutoIdentifiedModel
from resources.models.utils import generate_id, get_translated_fields
from modeltranslation.translator import NotRegistered, translator

from .exceptions import OrderStateTransitionError
from .utils import (
    convert_aftertax_to_pretax, get_fixed_time_slot_price, get_price_period_display,
    is_datetime_range_between_times, rounded, handle_customer_group_pricing, get_price_dict,
    finalize_price_data, get_fixed_time_slot_prices
)

import logging

logger = logging.getLogger()

# The best way for representing non existing archived_at would be using None for it,
# but that would not work with the unique_together constraint, which brings many
# benefits, so we use this sentinel value instead of None.
ARCHIVED_AT_NONE = datetime(9999, 12, 31, tzinfo=utc)

TAX_PERCENTAGES = [Decimal(x) for x in (
    '0.00',
    '10.00',
    '14.00',
    '24.00',
)]

DEFAULT_TAX_PERCENTAGE = Decimal('24.00')

class CustomerGroupTimeSlotPrice(AutoIdentifiedModel):
    price = models.DecimalField(
        verbose_name=_('price including VAT'), max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=_('This will override product price when applicable.')
    )
    price_tax_free = models.DecimalField(
        verbose_name=_('price without VAT'), max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=_('This will override product tax free price when applicable.'),
        default=Decimal('0.00')
    )
    customer_group = models.ForeignKey('payments.CustomerGroup',
        verbose_name=_('Customer group'), related_name='customer_group_time_slot_prices',
        on_delete=models.PROTECT,
    )
    time_slot_price = models.ForeignKey('payments.TimeSlotPrice',
        verbose_name=_('Time slot price'), related_name='customer_group_time_slot_prices',
        on_delete=models.CASCADE,
    )

    class Meta:
        unique_together = ('customer_group', 'time_slot_price')
        verbose_name = _('Customer group time slot price')
        verbose_name_plural = _('Customer group time slot prices')


class TimeSlotPriceQuerySet(models.QuerySet):
    def current(self):
        return self.filter(is_archived=False)


class TimeSlotPrice(AutoIdentifiedModel):
    begin = models.TimeField(verbose_name=_('Time slot begins'))
    end = models.TimeField(verbose_name=_('Time slot ends'))
    price = models.DecimalField(
        verbose_name=_('price including VAT'), max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=_('This will override product price when applicable.')
    )
    price_tax_free = models.DecimalField(
        verbose_name=_('price without VAT'), max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=_('This will override product tax free price when applicable'),
        default=Decimal('0.00')
    )
    product = models.ForeignKey('payments.Product',
        verbose_name=_('Product'), related_name='time_slot_prices',
        on_delete=models.CASCADE
    )
    is_archived = models.BooleanField(default=False, verbose_name=_('Is archived'))

    objects = TimeSlotPriceQuerySet.as_manager()

    def __str__(self) -> str:
        archived_text = f' ({_("Is archived")})' if self.is_archived else ""
        return f'({self.id}) {self.product.name}: {self.begin}-{self.end}{archived_text}'

    def product_tax_percentage(self):
        return self.product.tax_percentage

    def time_slot_overlaps(self):
        if self.is_archived:
            return False
        if self.product.price_type == Product.PRICE_FIXED:
            return TimeSlotPrice.objects.filter(
                product=self.product, begin=self.begin, end=self.end).exclude(
                    is_archived=True).exclude(id=self.id).exists()
        return TimeSlotPrice.objects.filter(
            product=self.product, begin__lt=self.end, end__gt=self.begin).exclude(
                is_archived=True).exclude(id=self.id).exists()

    def clean(self) -> None:
        if self.begin >= self.end:
            raise ValidationError(_('Begin should be before end'))
        if self.time_slot_overlaps():
            raise ValidationError(_('Overlapping time slot prices'))

    def save(self, *args, **kwargs):
        _saved_via_product = kwargs.pop('_saved_via_product', False)
        if not _saved_via_product and not self.is_archived:
            self.product = Product.objects.filter(
                product_id=self.product.product_id).get(archived_at=ARCHIVED_AT_NONE)

        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _('Time slot price')
        verbose_name_plural = _('Time slot prices')
        ordering = ('product', 'begin', 'end')


class OrderCustomerGroupDataQuerySet(models.QuerySet):
    def get_price(self):
        return sum([i.product_cg_price for i in self])

    def get_price_tax_free(self):
        return sum([i.product_cg_price_tax_free for i in self])

class OrderCustomerGroupData(models.Model):
    customer_group_name = models.CharField(max_length=255)
    product_cg_price = models.DecimalField(
        verbose_name=_('price including VAT'), max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=_('Price of the product at that given time.')
    )
    product_cg_price_tax_free = models.DecimalField(
        verbose_name=_('price without VAT'), max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=_('Tax free price of the product at that given time.'),
        default=Decimal('0.00')
    )
    price_is_based_on_product_cg = models.BooleanField(
        default=False,
        help_text=_("Is price based on product customer group price and not product's own default price"))
    order_line = models.OneToOneField('payments.OrderLine', on_delete=models.PROTECT, null=True)

    objects = OrderCustomerGroupDataQuerySet.as_manager()


    def __str__(self) -> str:
        return 'Order: {0} <{1}> ({2}) [{3}]'.format(self.order_line.order.order_number, self.product_cg_price, self.customer_group_name, self.product_cg_price_tax_free)


    class Meta:
        verbose_name = _('Order customer group')
        verbose_name_plural = _('Order customer groups')
        ordering = ('id',)

    def copy_translated_fields(self, other):
        fields = get_translated_fields(other)
        if not fields:
            return self
        translation_options = translator.get_options_for_model(self.__class__)
        for field_name in translation_options.fields.keys():
            for lang in [x[0] for x in settings.LANGUAGES]:
                val = fields.get(lang, None)
                if not val:
                    continue
                setattr(self, '%s_%s' % (field_name, lang), val)
        return self

class CustomerGroupLoginMethod(AutoIdentifiedModel):
    name = models.CharField(verbose_name=_('Name'), max_length=200)
    login_method_id = models.CharField(
        verbose_name=_('Login method id'),
        help_text=_('Login method id or amr given by authentication service such as Tunnistamo'),
        max_length=200,
        unique=True
    )

    def __str__(self) -> str:
        return f'{self.name} ({self.login_method_id})'

    def is_same_login_method(self, login_method_id: str) -> bool:
        '''Checks whether given login method is same as this login method'''
        return login_method_id == self.login_method_id

    class Meta:
        verbose_name = _('Customer group login method')
        verbose_name_plural = _('Customer group login methods')


class CustomerGroup(AutoIdentifiedModel):
    id = models.CharField(primary_key=True, max_length=50)
    name = models.CharField(verbose_name=_('Name'), max_length=200, unique=True)
    only_for_login_methods = models.ManyToManyField(
        CustomerGroupLoginMethod,
        verbose_name=_('Only for login methods'),
        help_text=_('Having none selected means that all login methods are allowed.'),
        related_name='customer_groups',
        blank=True
    )

    def __str__(self) -> str:
        return self.name

    def has_login_restrictions(self):
        '''Checks whether this cg has any login method restrictions'''
        return self.only_for_login_methods.exists()

    def is_allowed_cg_login_method(self, login_method_id: str) -> bool:
        '''Checks whether given login method is allowed for this cg'''
        if not self.only_for_login_methods.exists():
            # if there are no only_for_login_methods, any login method is ok
            return True
        for login_method in self.only_for_login_methods.all():
            if login_method.is_same_login_method(login_method_id):
                return True

        return False


class ProductCustomerGroupQuerySet(models.QuerySet):
    """
    Filter product customer groups with a customer group (cg) before calling these functions
    """
    def get_price_for(self, product):
        """
        Product customer group (pcg) can only have one product.
        If this pcg is connected to the given product, use this pcg's price.
        If no pcg is found, it means that product has no pcg for a certain cg
        -> use the product's default price instead
        """
        product_cg = self.filter(product=product).first()
        return product_cg.price if product_cg else product.price

    def get_tax_free_price_for(self, product):
        product_cg = self.filter(product=product).first()
        return product_cg.price_tax_free if product_cg else product.price_tax_free

    def get_customer_group_name(self, product):
        product_cg = self.filter(product=product).first()
        return product_cg.customer_group.name if product_cg else None

class ProductCustomerGroup(AutoIdentifiedModel):
    id = models.CharField(primary_key=True, max_length=50)

    customer_group = models.ForeignKey(CustomerGroup,
        verbose_name=_('Customer group'), related_name='customer_group',
        blank=True, on_delete=models.PROTECT
    )
    price = models.DecimalField(
        verbose_name=_('price including VAT'), max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=_('This will override product price field.')
    )

    price_tax_free = models.DecimalField(
        verbose_name=_('price without VAT'), max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=_('This will override product tax free price field.'),
        default=Decimal('0.00')
    )

    product = models.ForeignKey('payments.Product',
        verbose_name=_('Product'), related_name='product_customer_groups',
        blank=True, null=True, on_delete=models.PROTECT
    )

    objects = ProductCustomerGroupQuerySet.as_manager()

    def __str__(self) -> str:
        return '{0} <{1}> ({2}) [{3}]'.format(
            self.product.name, self.price, self.customer_group.name, self.price_tax_free)
    @property
    def product_tax_percentage(self):
        return self.product.tax_percentage


class ProductQuerySet(models.QuerySet):
    def current(self):
        return self.filter(archived_at=ARCHIVED_AT_NONE)

    def rents(self):
        return self.filter(type=Product.RENT)

class Product(models.Model):
    RENT = 'rent'
    EXTRA = 'extra'
    TYPE_CHOICES = (
        (RENT, _('rent')),
        (EXTRA, _('extra')),
    )

    PRICE_PER_PERIOD = 'per_period'
    PRICE_FIXED = 'fixed'
    PRICE_TYPE_CHOICES = (
        (PRICE_PER_PERIOD, _('per period')),
        (PRICE_FIXED, _('fixed')),
    )

    created_at = models.DateTimeField(verbose_name=_('created at'), auto_now_add=True)

    # This ID is common to all versions of the same product, and is the one
    # used as ID in the API.
    product_id = models.CharField(max_length=100, verbose_name=_('internal product ID'), editable=False, db_index=True)

    # archived_at determines when this version of the product has been either (soft)
    # deleted or replaced by a newer version. Value ARCHIVED_AT_NONE means this is the
    # current version in use.
    archived_at = models.DateTimeField(
        verbose_name=_('archived_at'), db_index=True, editable=False, default=ARCHIVED_AT_NONE
    )

    type = models.CharField(max_length=32, verbose_name=_('type'), choices=TYPE_CHOICES, default=RENT)
    sku = models.CharField(max_length=255, verbose_name=_('SKU'))

    sap_code = models.CharField(max_length=255, verbose_name=_('sap code'), blank=True)
    sap_unit = models.CharField(
        max_length=255, verbose_name=_('sap unit'), blank=True, help_text=_('Equals to sap profit center')
    )
    sap_function_area = models.CharField(max_length=16, verbose_name=_('sap function area'), blank=True)
    sap_office_code = models.CharField(max_length=4, verbose_name=_('sap office code'), blank=True)

    name = models.CharField(max_length=100, verbose_name=_('name'), blank=True)
    description = models.TextField(verbose_name=_('description'), blank=True)

    price = models.DecimalField(
        verbose_name=_('price including VAT'), max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    price_tax_free = models.DecimalField(
        verbose_name=_('price without VAT'), max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))], blank=True, default=Decimal('0.0')
    )
    tax_percentage = models.DecimalField(
        verbose_name=_('tax percentage'), max_digits=5, decimal_places=2, default=DEFAULT_TAX_PERCENTAGE,
        choices=[(tax, str(tax)) for tax in TAX_PERCENTAGES]
    )
    price_type = models.CharField(
        max_length=32, verbose_name=_('price type'), choices=PRICE_TYPE_CHOICES, default=PRICE_PER_PERIOD
    )
    price_period = models.DurationField(
        verbose_name=_('price period'), null=True, blank=True, default=timedelta(hours=1),
    )

    max_quantity = models.PositiveSmallIntegerField(verbose_name=_('max quantity'),
                                                    default=1, validators=[MinValueValidator(1)])

    resources = models.ManyToManyField(Resource, verbose_name=_('resources'), related_name='products', blank=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = _('product')
        verbose_name_plural = _('products')
        ordering = ('product_id',)
        unique_together = ('archived_at', 'product_id')

    def __str__(self):
        return '{} ({})'.format(self.name, self.product_id)

    def clean(self):
        if self.price_type == Product.PRICE_PER_PERIOD:
            if not self.price_period:
                raise ValidationError(
                    {'price_period': _('This field requires a non-zero value when price type is "per period".')}
                )
        else:
            self.price_period = None

    def save(self, *args, **kwargs):
        if self.id:
            resources = self.resources.all()
            Product.objects.filter(id=self.id).update(archived_at=now())
            product_groups = ProductCustomerGroup.objects.filter(product=self)
            time_slot_prices = TimeSlotPrice.objects.filter(product=self, is_archived=False)
            self.id = None
        else:
            resources = []
            product_groups = []
            time_slot_prices = []
            self.product_id = generate_id()

        super().save(*args, **kwargs)

        if resources:
            self.resources.set(resources)

        for product_group in product_groups:
            product_group.product = self
            product_group.save()

        for time_slot_price in time_slot_prices:
            cg_time_slot_prices = CustomerGroupTimeSlotPrice.objects.filter(time_slot_price=time_slot_price)
            time_slot_price.is_archived = True
            time_slot_price.id = None
            time_slot_price.save(_saved_via_product=True)
            for cg_time_slot_price in cg_time_slot_prices:
                cg_time_slot_price.id = None
                cg_time_slot_price.time_slot_price = time_slot_price
                cg_time_slot_price.save()


    def delete(self, *args, **kwargs):
        Product.objects.filter(id=self.id).update(archived_at=now())

    @rounded
    def get_pretax_price(self) -> Decimal:
        return convert_aftertax_to_pretax(self.price, self.tax_percentage)

    @rounded
    def get_pretax_price_context(self, price) -> Decimal:
        return convert_aftertax_to_pretax(price, self.tax_percentage)

    @rounded
    def get_pretax_price_for_time_range(self, begin: datetime, end: datetime) -> Decimal:
        return convert_aftertax_to_pretax(self.get_price_for_time_range(begin, end), self.tax_percentage)

    @rounded
    def get_price_for_time_range(self, begin: datetime, end: datetime, product_cg = None) -> Decimal:
        assert begin < end

        price = self.price if not product_cg else product_cg.price
        time_slot_prices = TimeSlotPrice.objects.filter(product=self)
        tz = self.resources.with_soft_deleted.first().unit.get_tz()
        local_tz_begin = begin.astimezone(tz)
        local_tz_end = end.astimezone(tz)
        if self.price_type == Product.PRICE_FIXED:
            if time_slot_prices:
                return get_fixed_time_slot_price(time_slot_prices, local_tz_begin, local_tz_end, self, price)
            return price
        elif self.price_type == Product.PRICE_PER_PERIOD:
            if time_slot_prices:
                slot_begin = local_tz_begin
                check_interval = timedelta(minutes=5)
                price_sum = 0
                # calculate price for each time chunk and use their sum as final price
                while slot_begin + check_interval <= local_tz_end:
                    price_was_added = False
                    for time_slot_price in time_slot_prices:
                        if is_datetime_range_between_times(begin_x=slot_begin, end_x=slot_begin + check_interval,
                            begin_y=time_slot_price.begin, end_y=time_slot_price.end):
                                cg_time_slot_price = CustomerGroupTimeSlotPrice.objects.filter(
                                    time_slot_price=time_slot_price, customer_group_id=self._in_memory_cg).first()
                                slot_price = time_slot_price.price
                                if cg_time_slot_price:
                                    slot_price = cg_time_slot_price.price
                                elif (ProductCustomerGroup.objects.filter(
                                    product=self, customer_group_id=self._in_memory_cg).exists()
                                    or hasattr(self, '_orderline_has_stored_pcg_price_for_non_null_cg')):
                                    # customer group data exists for product but not for time slot ->
                                    # use default pricing
                                    break

                                interval_price = slot_price * Decimal(check_interval / self.price_period)
                                price_sum += interval_price
                                price_was_added = True
                                break

                    if not price_was_added:
                        # time chunk was not in any priced slot -> use default pricing
                        interval_price = price * Decimal(check_interval / self.price_period)
                        price_sum += interval_price
                    slot_begin += check_interval
                return Decimal(price_sum)

            assert self.price_period, '{} {}'.format(self, self.price_period)
            return price * Decimal((end - begin) / self.price_period)
        else:
            raise NotImplementedError('Cannot calculate price, unknown price type "{}".'.format(self.price_type))

    def get_detailed_price_for_time_range(self, begin: datetime, end: datetime, product_cg = None, quantity = 0):
        '''
        Returns dict containing detailed price data for time range.
        '''
        assert begin < end
        price = self.price if not product_cg else product_cg.price
        price_tax_free = self.price_tax_free if not product_cg else product_cg.price_tax_free
        time_slot_prices = TimeSlotPrice.objects.filter(product=self)
        tz = self.resources.with_soft_deleted.first().unit.get_tz()
        local_tz_begin = begin.astimezone(tz)
        local_tz_end = end.astimezone(tz)
        # dict with keys for each unique price.
        detailed_pricing = {}
        if self.price_type == Product.PRICE_FIXED:
            # fixed price product
            fixed_slot_price = self.price
            fixed_taxfree = self.price_tax_free
            key = 'default_fixed'
            if time_slot_prices:
                # fixed price product with added time slot pricing
                # price with VAT, price without VAT
                fixed_slot_price, fixed_taxfree = get_fixed_time_slot_prices(
                    time_slot_prices=time_slot_prices,
                    begin=local_tz_begin,
                    end=local_tz_end,
                    product=self,
                    default_price=price,
                    default_price_taxfree=price_tax_free
                    )
                key = 'custom_fixed'

            detailed_pricing[key] = get_price_dict(
                count=quantity,
                price=fixed_slot_price,
                pretax=self.get_pretax_price_context(fixed_slot_price, rounded=False),
                fixed=True,
                taxfree_price=fixed_taxfree
            )

            # return detailed pricing for this fixed price product.
            return detailed_pricing
        elif self.price_type == Product.PRICE_PER_PERIOD:
            # per period product
            if time_slot_prices:
                # per period product with added time slot pricing
                slot_begin = local_tz_begin
                check_interval = timedelta(minutes=5)

                # calculate price for each time chunk
                while slot_begin + check_interval <= local_tz_end:
                    price_was_added = False
                    for time_slot_price in time_slot_prices:
                        if is_datetime_range_between_times(begin_x=slot_begin, end_x=slot_begin + check_interval,
                            begin_y=time_slot_price.begin, end_y=time_slot_price.end):
                                cg_time_slot_price = CustomerGroupTimeSlotPrice.objects.filter(
                                    time_slot_price=time_slot_price, customer_group_id=self._in_memory_cg).first()
                                slot_price = time_slot_price.price
                                tax_free_price = time_slot_price.price_tax_free
                                if cg_time_slot_price:
                                    # cg time slot pricing exists -> use its prices.
                                    slot_price = cg_time_slot_price.price
                                    tax_free_price = cg_time_slot_price.price_tax_free
                                elif (ProductCustomerGroup.objects.filter(
                                    product=self, customer_group_id=self._in_memory_cg).exists()
                                    or hasattr(self, '_orderline_has_stored_pcg_price_for_non_null_cg')):
                                    # customer group data exists for product but not for time slot ->
                                    # use default pricing
                                    break

                                if time_slot_price.id in detailed_pricing:
                                    detailed_pricing[time_slot_price.id]['count'] += 1
                                if time_slot_price.id not in detailed_pricing:
                                    detailed_pricing[time_slot_price.id] = get_price_dict(
                                        count=1,
                                        price=slot_price,
                                        pretax=self.get_pretax_price_context(slot_price,rounded=False),
                                        begin=time_slot_price.begin.isoformat('minutes'),
                                        end=time_slot_price.end.isoformat('minutes'),
                                        taxfree_price=tax_free_price
                                    )
                                    if quantity > 1:
                                        # quantity is > 1 if there are multiples of the same product
                                        detailed_pricing[time_slot_price.id]['quantity'] = quantity

                                price_was_added = True
                                break

                    if not price_was_added:
                        # time chunk was not in any priced slot -> use default pricing
                        # default already exists? +1 to count
                        if 'default' in detailed_pricing:
                            detailed_pricing['default']['count'] += 1
                        if 'default' not in detailed_pricing:
                            # first occurrence of default? -> add default to inner_price
                            detailed_pricing['default'] = get_price_dict(
                                count=1,
                                price=price,
                                pretax=self.get_pretax_price_context(price, rounded=False),
                                taxfree_price=price_tax_free
                            )
                            if quantity > 1:
                                # quantity is only defined/>1 if there are multiples of the same product
                                detailed_pricing['default']['quantity'] = quantity

                    slot_begin += check_interval
                # finalize the detailed_pricing so that it contains totals.
                detailed_pricing = finalize_price_data(detailed_pricing, self.price_type, self.price_period)
                # return detailed pricing for this per period product that contains time slot specific pricing.
                return detailed_pricing

            # per period product with no time slot prices -> use default.
            slot_begin = local_tz_begin
            check_interval = timedelta(minutes=5)
            while slot_begin + check_interval <= local_tz_end:
                if 'default' in detailed_pricing:
                    detailed_pricing['default']['count'] += 1
                else:
                    detailed_pricing['default'] = get_price_dict(
                        count=1,
                        price=price,
                        pretax=self.get_pretax_price_context(price, rounded=False),
                        taxfree_price=self.price_tax_free
                    )
                    if quantity > 1:
                        # quantity is only defined/>1 if there are multiples of the same product
                        detailed_pricing['default']['quantity'] = quantity
                slot_begin += check_interval

            detailed_pricing = finalize_price_data(detailed_pricing, self.price_type, self.price_period)
            # return detailed_pricing for this per period product that has no time slot specific pricing.
            return detailed_pricing
        else:
            raise NotImplementedError('Cannot calculate detailed pricing, unknown price type "{}".'.format(self.price_type))

    def get_pretax_price_for_reservation(self, reservation: Reservation, rounded: bool = True) -> Decimal:
        return self.get_pretax_price_for_time_range(reservation.begin, reservation.end, rounded=rounded)

    def get_price_for_reservation(self, reservation: Reservation, rounded: bool = True) -> Decimal:
        return self.get_price_for_time_range(reservation.begin, reservation.end, rounded=rounded)

    def get_detailed_price_structure(self, reservation: Reservation, quantity):
        return self.get_detailed_price_for_time_range(begin=reservation.begin, end=reservation.end, quantity=quantity)

    def get_tax_price(self) -> Decimal:
        return self.price - self.get_pretax_price()

    def has_customer_group(self):
        return ProductCustomerGroup.objects.filter(product=self).exists()

    def is_allowed_login_method(self, login_method_id: str, customer_group_id: str) -> bool:
        '''Checks whether given login method with selected cg is allowed for this product'''
        pcgs = ProductCustomerGroup.objects.filter(product=self, customer_group__id=customer_group_id)
        for pcg in pcgs:
            if not pcg.customer_group.is_allowed_cg_login_method(login_method_id):
                return False
        return True

    def has_only_restricted_customer_groups_for_login_method(self, login_method_id: str) -> bool:
        '''
        Checks whether given login method has no allowed cgs to choose from or at least
        one cg is usable
        '''
        pcgs = ProductCustomerGroup.objects.filter(product=self)
        for pcg in pcgs:
            if pcg.customer_group.is_allowed_cg_login_method(login_method_id):
                return False
        return True


class OrderQuerySet(models.QuerySet):
    def can_view(self, user):
        if not user.is_authenticated:
            return self.none()

        allowed_resources = Resource.objects.with_perm('can_view_reservation_product_orders', user)
        allowed_reservations = Reservation.objects.filter(Q(resource__in=allowed_resources) | Q(user=user))

        return self.filter(reservation__in=allowed_reservations)

    def update_expired(self) -> int:
        earliest_allowed_timestamp = now() - timedelta(minutes=settings.RESPA_PAYMENTS_PAYMENT_WAITING_TIME)
        log_entry_timestamps = OrderLogEntry.objects.filter(order=OuterRef('pk')).order_by('id').values('timestamp')
        too_old_waiting_orders = self.filter(
            state=Order.WAITING,
            is_requested_order=False
        ).annotate(
            created_at=Subquery(
                log_entry_timestamps[:1]
            )
        ).filter(
            created_at__lt=earliest_allowed_timestamp
        )
        for order in too_old_waiting_orders:
            order.set_state(Order.EXPIRED)

        time_now = now()
        earliest_allowed_requested = time_now - timedelta(hours=settings.RESPA_PAYMENTS_PAYMENT_REQUESTED_WAITING_TIME)

        # Set requested orders which customer hasn't tried to pay to expire.
        # Most specific waiting time setting is used to calculate expiration time
        # i.e. in order: resource > unit > global.
        # Waiting time value 0 means that it is not in use.
        too_old_ready_requested_orders = self.filter(
            state=Order.WAITING,
            is_requested_order=True,
            reservation__state=Reservation.READY_FOR_PAYMENT
        ).filter(
            confirmed_by_staff_at__lt=Case(
                When(reservation__resource__payment_requested_waiting_time__gt=0,
                    then=ExpressionWrapper(
                        time_now - timedelta(hours=1) * F('reservation__resource__payment_requested_waiting_time'),
                        output_field=DateTimeField()
                    )),
                When(reservation__resource__unit__payment_requested_waiting_time__gt=0,
                    then=ExpressionWrapper(
                        time_now - timedelta(hours=1) * F('reservation__resource__unit__payment_requested_waiting_time'),
                        output_field=DateTimeField()
                    )),
                default=earliest_allowed_requested
            )
        )

        for order in too_old_ready_requested_orders:
            order.set_state(Order.EXPIRED)

        # set requested orders which customer has tried to pay to expire faster
        too_old_waiting_requested_orders = self.filter(
            state=Order.WAITING,
            is_requested_order=True,
            reservation__state=Reservation.WAITING_FOR_PAYMENT
        ).annotate(
            last_modified_at=Subquery(
                log_entry_timestamps.reverse()[:1]
            )
        ).filter(
            last_modified_at__lt=earliest_allowed_timestamp
        )

        for order in too_old_waiting_requested_orders:
            order.set_state(Order.EXPIRED)

        return too_old_waiting_orders.count() + too_old_ready_requested_orders.count() \
                + too_old_waiting_requested_orders.count()


class Order(models.Model):
    WAITING = 'waiting'
    CONFIRMED = 'confirmed'
    REJECTED = 'rejected'
    EXPIRED = 'expired'
    CANCELLED = 'cancelled'

    STATE_CHOICES = (
        (WAITING, _('waiting')),
        (CONFIRMED, _('confirmed')),
        (REJECTED, _('rejected')),
        (EXPIRED, _('expired')),
        (CANCELLED, _('cancelled')),
    )

    CASH = 'cash'
    ONLINE = 'online'
    PAYMENT_METHOD_CHOICES = (
        ((ONLINE), _('online payment')),
        ((CASH), _('cash payment')),
    )

    state = models.CharField(max_length=32, verbose_name=_('state'), choices=STATE_CHOICES, default=WAITING)
    order_number = models.CharField(max_length=64, verbose_name=_('order number'), unique=True, default=generate_id)
    reservation = models.OneToOneField(
        Reservation, verbose_name=_('reservation'), related_name='order', on_delete=models.PROTECT
    )
    payment_url = models.TextField(verbose_name=_('payment url'), blank=True, default='')
    payment_method = models.CharField(
        max_length=200, verbose_name=_('payment method'),
        choices=PAYMENT_METHOD_CHOICES, default=ONLINE
    )
    is_requested_order = models.BooleanField(verbose_name=_('is requested order'), default=False)
    confirmed_by_staff_at = models.DateTimeField(verbose_name=_('confirmed by staff at'), blank=True, null=True)
    customer_group = models.ForeignKey(CustomerGroup,
        verbose_name=_('Customer group'), related_name='orders',
        blank=True, null=True, on_delete=models.PROTECT
    )

    objects = OrderQuerySet.as_manager()

    class Meta:
        verbose_name = _('order')
        verbose_name_plural = _('orders')
        ordering = ('id',)

    def __str__(self):
        return '({}) {}'.format(self.order_number, self.reservation)

    @cached_property
    def created_at(self):
        first_log_entry = self.log_entries.first()
        return first_log_entry.timestamp if first_log_entry else None

    def save(self, *args, **kwargs):
        is_new = not bool(self.id)
        super().save(*args, **kwargs)

        if is_new:
            self.create_log_entry(state_change=self.state, message='Created.')

    def set_confirmed_by_staff(self):
        self.confirmed_by_staff_at = datetime.now()
        self.save()

    def get_order_lines(self):
        # This allows us to do price calculations using order line objects that
        # don't exist in the db. That is needed in the price check endpoint.
        return self._in_memory_order_lines if hasattr(self, '_in_memory_order_lines') else self.order_lines.all()

    def get_price(self) -> Decimal:
        total_sum = sum(order_line.get_price() for order_line in self.get_order_lines())
        # The final total is rounded, NO ROUNDING BEFORE THIS.
        return Decimal(total_sum).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def set_state(
            self, new_state: str, log_message: str = None,
            save: bool = True, update_reservation_state: bool = True,
            **kwargs
        ) -> None:
        assert new_state in (Order.WAITING, Order.CONFIRMED, Order.REJECTED, Order.EXPIRED, Order.CANCELLED)

        old_state = self.state
        if new_state == old_state:
            logger.debug('Trying to set order state to same as before; skipping all other state change handling...')
            return

        try:
            with transaction.atomic():
                order = Order.objects.filter(id=self.id).select_for_update(nowait=True).get()

                if order.state == new_state:
                    logger.debug('Trying to set order state to same as before; skipping this state change...')
                    return

                valid_state_changes = {
                    Order.WAITING: (Order.CONFIRMED, Order.REJECTED, Order.EXPIRED, Order.CANCELLED, ),
                    Order.CONFIRMED: (Order.CANCELLED,),
                }

                valid_new_states = valid_state_changes.get(old_state, ())

                if new_state not in valid_new_states:
                    raise OrderStateTransitionError(
                        'Cannot set order {} state to "{}", it is in an invalid state "{}".'.format(
                            self.order_number, new_state, old_state
                        )
                    )

                self.state = new_state

                if update_reservation_state:
                    if new_state == Order.CONFIRMED:
                        self.reservation.set_state(Reservation.CONFIRMED, kwargs.get('user', self.reservation.user))
                    elif new_state in (Order.REJECTED, Order.EXPIRED, Order.CANCELLED):
                        self.reservation.set_state(Reservation.CANCELLED, kwargs.get('user', self.reservation.user))

                if save:
                    self.save()

                self.create_log_entry(state_change=new_state, message=log_message)
        except DatabaseError:
            logger.debug('Order set state db error occurred most likely due to a race condition; skip handling this state change...')
            return

    def create_log_entry(self, message: str = None, state_change: str = None) -> None:
        OrderLogEntry.objects.create(order=self, state_change=state_change or '', message=message or '')

    def get_notification_context(self, language_code):
        with translation.override(language_code):
            return NotificationOrderSerializer(self).data

    def get_customer_group_name(self):
        if hasattr(self, '_in_memory_order_customer_group_data'):
            return self._in_memory_order_customer_group_data.customer_group_name
        order_cg = OrderCustomerGroupData.objects.filter(order_line__in=self.get_order_lines()).first()
        return order_cg.customer_group_name if order_cg else None

    def get_customer_group(self):
        if hasattr(self, '_in_memory_order_lines'):
            product = self.get_order_lines()[0].product
        else:
            product = self.get_order_lines().first().product
        product_cg = ProductCustomerGroup.objects.filter(product__product_id=product.product_id).first()
        if not product_cg:
            return
        return product_cg.customer_group

    def get_order_customer_group_data(self):
        return OrderCustomerGroupData.objects.filter(order_line__in=self.get_order_lines()).first()

class OrderLine(models.Model):
    order = models.ForeignKey(Order, verbose_name=_('order'), related_name='order_lines', on_delete=models.CASCADE)
    product = models.ForeignKey(
        Product, verbose_name=_('product'), related_name='order_lines', on_delete=models.PROTECT
    )

    quantity = models.PositiveIntegerField(verbose_name=_('quantity'), default=1)

    class Meta:
        verbose_name = _('order line')
        verbose_name_plural = _('order lines')
        ordering = ('id',)

    def __str__(self):
        return str(self.product)

    @handle_customer_group_pricing
    def get_unit_price(self) -> Decimal:
        return self.product.get_price_for_reservation(self.order.reservation)

    @handle_customer_group_pricing
    def get_price(self, rounded: bool = False) -> Decimal:
        return self.product.get_price_for_reservation(self.order.reservation, rounded=rounded) * self.quantity

    @handle_customer_group_pricing
    def get_detailed_price(self):
        return self.product.get_detailed_price_structure(self.order.reservation, self.quantity)

    @handle_customer_group_pricing
    def get_pretax_price_for_reservation(self):
        return self.product.get_pretax_price_for_reservation(self.order.reservation)

    def get_tax_price_for_reservation(self):
        return self.get_unit_price() - self.get_pretax_price_for_reservation()

    @property
    def product_cg_price(self):
        if hasattr(self.order, '_in_memory_order_customer_group_data'):
            order_cg = next(iter([order_cg for order_cg in self.order._in_memory_order_customer_group_data if order_cg.order_line == self]))
            return order_cg.product_cg_price
        order_cg = OrderCustomerGroupData.objects.filter(order_line=self)
        if order_cg.exists():
            return order_cg.first().product_cg_price

    @property
    def product_cg_price_tax_free(self):
        if hasattr(self.order, '_in_memory_order_customer_group_data'):
            order_cg = next(iter([order_cg for order_cg in self.order._in_memory_order_customer_group_data if order_cg.order_line == self]))
            return order_cg.product_cg_price_tax_free
        order_cg = OrderCustomerGroupData.objects.filter(order_line=self)
        if order_cg.exists():
            return order_cg.first().product_cg_price_tax_free

    @handle_customer_group_pricing
    def handle_customer_group_pricing(self):
        pass

class OrderLogEntry(models.Model):
    order = models.ForeignKey(
        Order, verbose_name=_('order log entry'), related_name='log_entries', on_delete=models.CASCADE
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    state_change = models.CharField(
        max_length=32, verbose_name=_('state change'), choices=Order.STATE_CHOICES, blank=True
    )
    message = models.TextField(blank=True)

    class Meta:
        verbose_name = _('order log entry')
        verbose_name_plural = _('order log entries')
        ordering = ('id',)

    def __str__(self):
        return '{} order {} state change {} message {}'.format(
            self.timestamp, self.order_id, self.state_change or None, self.message or None
        )


class LocalizedSerializerField(serializers.Field):
    def __init__(self, *args, **kwargs):
        kwargs['read_only'] = True
        super().__init__(*args, **kwargs)

    def to_representation(self, value):
        return localize(value)


class NotificationProductSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source='product_id')
    tax_percentage = LocalizedSerializerField()
    price = LocalizedSerializerField()
    type_display = serializers.ReadOnlyField(source='get_type_display')
    price_type_display = serializers.ReadOnlyField(source='get_price_type_display')
    price_period_display = serializers.SerializerMethodField()
    pretax_price = LocalizedSerializerField(source='get_pretax_price')
    tax_price = LocalizedSerializerField(source='get_tax_price')

    def get_price_period_display(self, obj):
        return get_price_period_display(obj.price_period)

    class Meta:
        model = Product
        fields = ('id', 'name', 'description', 'type', 'type_display', 'price_type', 'price_type_display',
                  'tax_percentage', 'price', 'price_period', 'price_period_display', 'pretax_price', 'tax_price')


class NotificationOrderLineSerializer(serializers.ModelSerializer):
    product = NotificationProductSerializer()
    price = LocalizedSerializerField(source='get_price')
    unit_price = LocalizedSerializerField(source='get_unit_price')
    reservation_pretax_price = serializers.ReadOnlyField(source='get_pretax_price_for_reservation')
    reservation_tax_price = serializers.ReadOnlyField(source='get_tax_price_for_reservation')
    detailed_price = LocalizedSerializerField(source='get_detailed_price')

    class Meta:
        model = OrderLine
        fields = ('product', 'quantity', 'price', 'unit_price', 'reservation_pretax_price','reservation_tax_price', 'detailed_price')


class NotificationOrderSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source='order_number')
    created_at = LocalizedSerializerField()
    order_lines = NotificationOrderLineSerializer(many=True)
    price = LocalizedSerializerField(source='get_price')
    payment_method = LocalizedSerializerField()

    class Meta:
        model = Order
        fields = ('id', 'order_lines', 'price', 'created_at', 'payment_method')
