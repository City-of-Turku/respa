from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import wraps

from django.utils.translation import ugettext_lazy as _


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

        if order_cg:
            self.product.price = order_cg.product_cg_price
            return func(self)

        self.product.price = self.product_cg_price \
            if prod_cg.exists() and (self.product_cg_price or is_free(self.product_cg_price)) \
            else original.price
        return func(self)
    return wrapped

def is_free(price) -> bool:
    return isinstance(price, Decimal) and price == Decimal('0.00')