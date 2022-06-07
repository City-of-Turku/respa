from rest_framework import serializers
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import wraps

from django.utils.translation import ugettext_lazy as _
from django.utils.dateparse import parse_datetime

def price_as_sub_units(price: Decimal) -> int:
    return int(round_price(price) * 100)


def round_price(price: Decimal) -> Decimal:
    return price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def rounded(func):
    """
    Decorator for conditionally rounding function result

    By default the result is rounded to two decimal places, but the rounding
    can be turned off by giving parameter "rounded=False" when calling the
    function.
    """
    @wraps(func)
    def wrapped(*args, **kwargs):
        rounded = kwargs.pop('rounded', True)
        value = func(*args, **kwargs)
        if rounded:
            value = round_price(value)
        return value
    return wrapped


def convert_pretax_to_aftertax(pretax_price: Decimal, tax_percentage: Decimal) -> Decimal:
    return pretax_price * (1 + tax_percentage / 100)


def convert_aftertax_to_pretax(aftertax_price: Decimal, tax_percentage: Decimal) -> Decimal:
    return aftertax_price / (1 + tax_percentage / 100)


def get_price_period_display(price_period):
    if not price_period:
        return None

    hours = Decimal(price_period / timedelta(hours=1)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP).normalize()
    if hours == 1:
        return _('hour')
    else:
        return _('{hours} hours'.format(hours=hours))


def handle_customer_group_pricing(func):
    from payments.models import ProductCustomerGroup, Product, OrderCustomerGroupData

    @wraps(func)
    def wrapped(self, *args, **kwargs):
        original = Product.objects.get(id=self.product.id)
        prod_cg = ProductCustomerGroup.objects.filter(product=self.product)
        order_cg = OrderCustomerGroupData.objects.filter(order_line=self).first()

        if self.order:
            _in_memory_cg = None
            if self.order.customer_group:
                _in_memory_cg = self.order.customer_group.id
            elif hasattr(self.order, '_in_memory_customer_group_id'):
                _in_memory_cg = self.order._in_memory_customer_group_id
            self.product._in_memory_cg = _in_memory_cg

        if order_cg:
            if (self.order and self.order.customer_group
                and order_cg.price_is_based_on_product_cg):
                self.product._orderline_has_stored_pcg_price_for_non_null_cg = True
            self.product.price = order_cg.product_cg_price
            return func(self)

        self.product.price = self.product_cg_price \
            if prod_cg.exists() and (self.product_cg_price or is_free(self.product_cg_price)) \
            else original.price
        return func(self)
    return wrapped

def is_free(price) -> bool:
    return isinstance(price, Decimal) and price == Decimal('0.00')

def get_price(order: dict, begin, end, **kwargs) -> Decimal:
    from payments.models import Product, ProductCustomerGroup, Order
    def handle(order_line):
        if not isinstance(order_line['product'], str):
            raise serializers.ValidationError({'product': _('Expected str, got type %s') % type(order_line['product']).__name__})
        return order_line['product'], order_line.get('quantity', 1)

    if 'id' in order:
        order = Order.objects.filter(order_number=order['id']).first()
        if not order:
            raise serializers.ValidationError({'order': _('Invalid order id.')})
        return order.get_price()

    if not order.get('order_lines', None):
        raise serializers.ValidationError({'order_lines': _('This is field required.')})
    if not isinstance(order['order_lines'], list):
        raise serializers.ValidationError({'order_lines': _('Expected list, got type %s') % type(order['order_lines']).__name__})

    products = [handle(ol) for ol in order['order_lines']]
    customer_group = order.get('customer_group', None)
    price = Decimal()

    for product, quantity in products:
        product_cg = None
        product = Product.objects.filter(product_id=product).current().first()
        product._in_memory_cg = customer_group
        if customer_group:
            product_cg = ProductCustomerGroup.objects.filter(product=product, customer_group__id=customer_group).first()
        price += product.get_price_for_time_range(parse_datetime(begin), parse_datetime(end), product_cg=product_cg) * quantity
    return price


def is_datetime_between_times(time: datetime, begin: time, end: time) -> bool:
    '''Checks if given datetime is between given begin and end times'''
    if begin <= time.time() <= end:
        return True
    return False


def is_datetime_range_between_times(begin_x: datetime, end_x: datetime, begin_y: time, end_y: time) -> bool:
    '''Checks if given begin and end datetimes are both between given begin and end times'''
    if (is_datetime_between_times(time=begin_x, begin=begin_y, end=end_y)
        and is_datetime_between_times(time=end_x, begin=begin_y, end=end_y)):
            return True
    return False


def find_time_slot_with_smallest_duration(time_slots):
    '''Finds and returns the time slot with smallest duration within given queryset'''
    smallest_duration_slot = time_slots.first()
    today = date.today()
    for time_slot in time_slots:
        slot_begin_dt = datetime.combine(today, time_slot.begin)
        slot_end_dt = datetime.combine(today, time_slot.end)
        smallest_begin_dt = datetime.combine(today, smallest_duration_slot.begin)
        smallest_end_dt = datetime.combine(today, smallest_duration_slot.end)
        if slot_end_dt - slot_begin_dt < smallest_end_dt - smallest_begin_dt:
            smallest_duration_slot = time_slot
    return smallest_duration_slot


def get_fixed_time_slot_price(time_slot_prices, begin, end, product, default_price):
    '''Returns correct time slot's price or default price based on given time slots and product'''
    from payments.models import CustomerGroupTimeSlotPrice, ProductCustomerGroup

    # fetch only time slots between given begin and end
    slots_between_begin_and_end = time_slot_prices.filter(begin__lte=begin, end__gte=end)
    time_slot_prices = slots_between_begin_and_end

    # try to find valid time slots by cg first
    cg_data_exists_for_product = (ProductCustomerGroup.objects.filter(
        product=product, customer_group_id=product._in_memory_cg).exists()
        or hasattr(product, '_orderline_has_stored_pcg_price_for_non_null_cg'))
    if product._in_memory_cg:
        time_slots_with_cg = slots_between_begin_and_end.filter(
                customer_group_time_slot_prices__customer_group=product._in_memory_cg)
        if len(time_slots_with_cg) > 0:
            # found time slots with cg -> use them
            time_slot_prices = time_slots_with_cg
        elif cg_data_exists_for_product:
            # no time slots with cg, but product does have the cg -> return default
            return Decimal(default_price)

    time_slot_price = None
    if len(time_slot_prices) == 1:
        # only one time slot found -> use it
        time_slot_price = time_slot_prices.first()
    elif len(time_slot_prices) > 1:
        # multiple time slots found, find the must accurate/smallest duration
        time_slot_price = find_time_slot_with_smallest_duration(time_slot_prices)
    if time_slot_price:
        # select correct price to use for this time slot
        slot_price = time_slot_price.price
        cg_time_slot_price = CustomerGroupTimeSlotPrice.objects.filter(
            time_slot_price=time_slot_price, customer_group_id=product._in_memory_cg).first()
        if cg_time_slot_price:
            # if time slot has the correct customer group, use its price
            slot_price = cg_time_slot_price.price

        return Decimal(slot_price)

    # no valid time slots found, return default price
    return Decimal(default_price)
