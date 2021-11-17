from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import OuterRef, Q, Subquery
from django.utils import translation
from django.utils.formats import localize
from django.utils.functional import cached_property
from django.utils.timezone import now, utc
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers

from resources.models import Reservation, Resource
from resources.models.base import AutoIdentifiedModel
from resources.models.utils import generate_id, get_translated_fields
from modeltranslation.translator import NotRegistered, translator

from .exceptions import OrderStateTransitionError
from .utils import convert_aftertax_to_pretax, get_price_period_display, rounded, handle_customer_group_pricing

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


class OrderCustomerGroupDataQuerySet(models.QuerySet):
    def get_price(self):
        return sum([i.product_cg_price for i in self])

class OrderCustomerGroupData(models.Model):
    customer_group_name = models.CharField(max_length=255)
    product_cg_price = models.DecimalField(
        verbose_name=_('price including VAT'), max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=_('Price of the product at that given time.')
    )
    order_line = models.OneToOneField('payments.OrderLine', on_delete=models.PROTECT, null=True)

    objects = OrderCustomerGroupDataQuerySet.as_manager()


    def __str__(self) -> str:
        return 'Order: {0} <{1}> ({2})'.format(self.order_line.order.order_number, self.product_cg_price, self.customer_group_name)


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

class CustomerGroup(AutoIdentifiedModel):
    id = models.CharField(primary_key=True, max_length=50)
    name = models.CharField(verbose_name=_('Name'), max_length=200, unique=True)

    def __str__(self) -> str:
        return self.name

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

    product = models.ForeignKey('payments.Product',
        verbose_name=_('Product'), related_name='product_customer_groups',
        blank=True, null=True, on_delete=models.PROTECT
    )

    objects = ProductCustomerGroupQuerySet.as_manager()

    def __str__(self) -> str:
        return '{0} <{1}> ({2})'.format(self.product.name, self.price, self.customer_group.name)


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
    sap_unit = models.CharField(max_length=255, verbose_name=_('sap unit'), blank=True, help_text=_('sap profit center'))
    name = models.CharField(max_length=100, verbose_name=_('name'), blank=True)
    description = models.TextField(verbose_name=_('description'), blank=True)

    price = models.DecimalField(
        verbose_name=_('price including VAT'), max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
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
            self.id = None
        else:
            resources = []
            product_groups = []
            self.product_id = generate_id()

        super().save(*args, **kwargs)

        if resources:
            self.resources.set(resources)

        for product_group in product_groups:
            product_group.product = self
            product_group.save()

    def delete(self, *args, **kwargs):
        Product.objects.filter(id=self.id).update(archived_at=now())

    @rounded
    def get_pretax_price(self) -> Decimal:
        return convert_aftertax_to_pretax(self.price, self.tax_percentage)

    @rounded
    def get_pretax_price_for_time_range(self, begin: datetime, end: datetime) -> Decimal:
        return convert_aftertax_to_pretax(self.get_price_for_time_range(begin, end), self.tax_percentage)

    @rounded
    def get_price_for_time_range(self, begin: datetime, end: datetime, product_cg = None) -> Decimal:
        assert begin < end

        price = self.price if not product_cg else product_cg.price

        if self.price_type == Product.PRICE_FIXED:
            return price
        elif self.price_type == Product.PRICE_PER_PERIOD:
            assert self.price_period, '{} {}'.format(self, self.price_period)
            return price * Decimal((end - begin) / self.price_period)
        else:
            raise NotImplementedError('Cannot calculate price, unknown price type "{}".'.format(self.price_type))

    def get_pretax_price_for_reservation(self, reservation: Reservation, rounded: bool = True) -> Decimal:
        return self.get_pretax_price_for_time_range(reservation.begin, reservation.end, rounded=rounded)

    def get_price_for_reservation(self, reservation: Reservation, rounded: bool = True) -> Decimal:
        return self.get_price_for_time_range(reservation.begin, reservation.end, rounded=rounded)

    def get_tax_price(self) -> Decimal:
        return self.price - self.get_pretax_price()

    def has_customer_group(self):
        return ProductCustomerGroup.objects.filter(product=self).exists()

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
            state=Order.WAITING
        ).annotate(
            created_at=Subquery(
                log_entry_timestamps[:1]
            )
        ).filter(
            created_at__lt=earliest_allowed_timestamp
        )
        for order in too_old_waiting_orders:
            order.set_state(Order.EXPIRED)

        return too_old_waiting_orders.count()


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

    state = models.CharField(max_length=32, verbose_name=_('state'), choices=STATE_CHOICES, default=WAITING)
    order_number = models.CharField(max_length=64, verbose_name=_('order number'), unique=True, default=generate_id)
    reservation = models.OneToOneField(
        Reservation, verbose_name=_('reservation'), related_name='order', on_delete=models.PROTECT
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

    def get_order_lines(self):
        # This allows us to do price calculations using order line objects that
        # don't exist in the db. That is needed in the price check endpoint.
        return self._in_memory_order_lines if hasattr(self, '_in_memory_order_lines') else self.order_lines.all()

    def get_price(self) -> Decimal:
        return sum(order_line.get_price() for order_line in self.get_order_lines())

    def set_state(self, new_state: str, log_message: str = None, save: bool = True) -> None:
        assert new_state in (Order.WAITING, Order.CONFIRMED, Order.REJECTED, Order.EXPIRED, Order.CANCELLED)

        old_state = self.state
        if new_state == old_state:
            return

        valid_state_changes = {
            Order.WAITING: (Order.CONFIRMED, Order.REJECTED, Order.EXPIRED),
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

        if new_state == Order.CONFIRMED:
            self.reservation.set_state(Reservation.CONFIRMED, None)
        elif new_state in (Order.REJECTED, Order.EXPIRED, Order.CANCELLED):
            self.reservation.set_state(Reservation.CANCELLED, None)

        if save:
            self.save()

        self.create_log_entry(state_change=new_state, message=log_message)

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
        product = self.get_order_lines().first().product
        product_cg = ProductCustomerGroup.objects.filter(product=product).first()
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
    def get_price(self) -> Decimal:
        return self.product.get_price_for_reservation(self.order.reservation) * self.quantity

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
        order_cg = OrderCustomerGroupData.objects.filter(order_line=self).first()
        if order_cg:
            return order_cg.product_cg_price

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

    class Meta:
        model = OrderLine
        fields = ('product', 'quantity', 'price', 'unit_price', 'reservation_pretax_price','reservation_tax_price')


class NotificationOrderSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source='order_number')
    created_at = LocalizedSerializerField()
    order_lines = NotificationOrderLineSerializer(many=True)
    price = LocalizedSerializerField(source='get_price')

    class Meta:
        model = Order
        fields = ('id', 'order_lines', 'price', 'created_at')
