from django.utils.duration import duration_string
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers
from payments.api.product import ProductCustomerGroupSerializer

from resources.api.base import TranslatedModelSerializer

from ..models import Order, OrderLine, Product, ProductCustomerGroup


class ProductSerializer(TranslatedModelSerializer):
    id = serializers.CharField(source='product_id')
    price = serializers.SerializerMethodField()
    product_customer_groups = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            'id', 'type', 'name', 'description', 'price', 'max_quantity', 'product_customer_groups'
        )

    def get_price(self, obj):
        if obj.price_type not in (Product.PRICE_FIXED, Product.PRICE_PER_PERIOD):
            raise ValueError('{} has invalid price type "{}"'.format(obj, obj.price_type))

        ret = {
            'type': obj.price_type,
            'tax_percentage': str(obj.tax_percentage),
            'amount': str(obj.price)
        }
        if obj.price_type == Product.PRICE_PER_PERIOD:
            ret.update({'period': duration_string(obj.price_period)})

        return ret

    def get_product_customer_groups(self, obj):
        product_cgs = ProductCustomerGroup.objects.filter(product=obj)
        serializer = ProductCustomerGroupSerializer(product_cgs, many=True)
        return serializer.data


class OrderLineSerializer(serializers.ModelSerializer):
    product = serializers.SlugRelatedField(queryset=Product.objects.current(), slug_field='product_id')
    price = serializers.CharField(source='get_price', read_only=True)
    unit_price = serializers.CharField(source='get_unit_price', read_only=True)

    class Meta:
        model = OrderLine
        fields = ('product', 'quantity', 'unit_price', 'price')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['product'] = ProductSerializer(instance.product).data
        return data

    def validate(self, order_line):
        if order_line.get('quantity', 1) > order_line['product'].max_quantity:
            raise serializers.ValidationError({'quantity': _('Cannot exceed max product quantity')})
        return order_line

    def validate_product(self, product):
        available_products = self.context['available_products']
        # available_products None means "all".
        # The price check endpoint uses that because available products don't
        # make sense in it's context (because there is no resource),
        if available_products is not None:
            if product not in available_products:
                raise serializers.ValidationError(_("This product isn't available on the resource."))
        return product


class OrderSerializerBase(serializers.ModelSerializer):
    order_lines = OrderLineSerializer(many=True)
    price = serializers.CharField(source='get_price', read_only=True)

    class Meta:
        model = Order
        fields = ('state', 'order_lines', 'price')
