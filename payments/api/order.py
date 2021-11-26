from django.utils.translation import ugettext_lazy as _
from django.db.models import Q
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from resources.api.base import register_view
from resources.models import Reservation

from ..api.base import OrderLineSerializer, OrderSerializerBase
from ..models import CustomerGroup, Order, OrderCustomerGroupData, OrderLine, Product, ProductCustomerGroup


class PriceEndpointOrderSerializer(OrderSerializerBase):
    # these fields are actually returned from the API as well, but because
    # they are non-model fields, it seems to be easier to mark them as write
    # only and add them manually to returned data in the viewset
    begin = serializers.DateTimeField(write_only=True)
    end = serializers.DateTimeField(write_only=True)
    customer_group = serializers.CharField(write_only=True, required=False)

    class Meta(OrderSerializerBase.Meta):
        fields = ('order_lines', 'price', 'begin', 'end', 'customer_group')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # None means "all", we don't want product availability validation
        self.context['available_products'] = None

    def validate(self, attrs):
        attrs = super().validate(attrs)
        begin = attrs['begin']
        end = attrs['end']
        order_lines = attrs.get('order_lines', [])
        customer_group = attrs.pop('customer_group', None)
        if end < begin:
            raise serializers.ValidationError(_('Begin time must be before end time'), code='invalid_date_range')
        query = Q()
        for order_line in order_lines:
            product = order_line['product']
            query |= Q(product=product, customer_group__id=customer_group)

        if not query:
            raise serializers.ValidationError(_('At least one order line required.'))

        product_cgs = ProductCustomerGroup.objects.filter(query)

        if customer_group and not product_cgs.exists():
            raise serializers.ValidationError({'customer_group': _('Invalid customer group id')}, code='invalid_customer_group')
        else:
            attrs['product_cgs'] = product_cgs
        return attrs


class OrderViewSet(viewsets.ViewSet):
    @action(detail=False, methods=['POST'])
    def check_price(self, request):
        # validate incoming Order and OrderLine data
        write_serializer = PriceEndpointOrderSerializer(data=request.data, context={'request':request})
        write_serializer.is_valid(raise_exception=True)

        # build Order and OrderLine objects in memory only
        order_data = write_serializer.validated_data
        order_lines_data = order_data.pop('order_lines')
        product_cgs = order_data.pop('product_cgs', None)
        begin = order_data.pop('begin')
        end = order_data.pop('end')
        order_data['state'] = 'price_check'
        order = Order(**order_data)
        order_lines = [OrderLine(order=order, **data) for data in order_lines_data]

        # store the OrderLine objects in the Order object so that we can use
        # those when calculating prices
        order._in_memory_order_lines = order_lines
        # order line price calculations need a dummy reservation from which they
        # get begin and end times from
        reservation = Reservation(begin=begin, end=end)
        order.reservation = reservation

        # try to use customer group pricing when customer group is given
        if product_cgs:
            order._in_memory_order_customer_group_data = [OrderCustomerGroupData(order_line=order_line,
                product_cg_price=product_cgs.get_price_for(order_line.product),
                customer_group_name=product_cgs.get_customer_group_name(order_line.product))
                for order_line in order.get_order_lines()
            ]


        # serialize the in-memory objects
        read_serializer = PriceEndpointOrderSerializer(order, context={'request':request})
        order_data = read_serializer.data
        order_data['order_lines'] = [OrderLineSerializer(ol).data for ol in order_lines]
        order_data.update({'begin': begin, 'end': end})

        return Response(order_data, status=200)


register_view(OrderViewSet, 'order', 'order')
