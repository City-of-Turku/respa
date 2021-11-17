from django.utils.translation import ugettext_lazy as _
from django.db.models import Q
from rest_framework import exceptions, serializers, status
from rest_framework.exceptions import PermissionDenied

from payments.exceptions import (
    DuplicateOrderError, PayloadValidationError, RespaPaymentError, ServiceUnavailableError, UnknownReturnCodeError
)
from resources.api.reservation import ReservationSerializer

from ..models import CustomerGroup, OrderCustomerGroupData, OrderLine, Product, ProductCustomerGroup
from ..providers import get_payment_provider
from .base import OrderSerializerBase


class ReservationEndpointOrderSerializer(OrderSerializerBase):
    id = serializers.ReadOnlyField(source='order_number')
    return_url = serializers.CharField(write_only=True)
    payment_url = serializers.SerializerMethodField()
    customer_group = serializers.CharField(write_only=True, required=False)

    class Meta(OrderSerializerBase.Meta):
        fields = OrderSerializerBase.Meta.fields + ('id', 'return_url', 'payment_url', 'customer_group')

    def create(self, validated_data):
        order_lines_data = validated_data.pop('order_lines', [])
        customer_group = validated_data.pop('customer_group', None)
        return_url = validated_data.pop('return_url', '')
        order = super().create(validated_data)

        for order_line_data in order_lines_data:
            product = order_line_data['product']
            order_line = OrderLine.objects.create(order=order, **order_line_data)
            prod_cg = ProductCustomerGroup.objects.filter(product=product, customer_group__id=customer_group)
            if prod_cg.exists():
                ocgd = OrderCustomerGroupData.objects.create(order_line=order_line,
                product_cg_price=prod_cg.get_price_for(order_line.product))
                ocgd.copy_translated_fields(prod_cg.first().customer_group)
                ocgd.save()


        payments = get_payment_provider(request=self.context['request'],
                                        ui_return_url=return_url)
        try:
            self.context['payment_url'] = payments.initiate_payment(order)
        except DuplicateOrderError as doe:
            raise exceptions.APIException(detail=str(doe),
                                          code=status.HTTP_409_CONFLICT)
        except (PayloadValidationError, UnknownReturnCodeError) as e:
            raise exceptions.APIException(detail=str(e),
                                          code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except ServiceUnavailableError as sue:
            raise exceptions.APIException(detail=str(sue),
                                          code=status.HTTP_503_SERVICE_UNAVAILABLE)
        except RespaPaymentError as pe:
            raise exceptions.APIException(detail=str(pe),
                                          code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return order

    def get_payment_url(self, obj):
        return self.context.get('payment_url', '')

    def validate_order_lines(self, order_lines):
        # Check order contains order lines
        if not order_lines:
            raise serializers.ValidationError(_('At least one order line required.'))

        # Check products in order lines are unique
        product_ids = [ol['product'].product_id for ol in order_lines]
        if len(product_ids) > len(set(product_ids)):
            raise serializers.ValidationError(_('Order lines cannot contain duplicate products.'))

        resource = self.context.get('resource')
        request = self.context.get('request')
        if resource and resource.has_rent() and not resource.can_bypass_payment(request.user):
            if not any(ol['product'].type == Product.RENT for ol in order_lines):
                raise serializers.ValidationError(_('The order must contain at least one product of type "rent".'))

        return order_lines

    def validate_customer_group(self, customer_group):
        if not CustomerGroup.objects.filter(id=customer_group).first():
            raise serializers.ValidationError({'customer_group': _('Invalid customer group id')}, code='invalid_customer_group')
        return customer_group

    def validate(self, attrs):
        attrs = super().validate(attrs)
        customer_group = attrs.get('customer_group', None)
        resource = self.context.get('resource')
        for product in resource.get_products():
            if product.has_customer_group() and not customer_group:
                raise serializers.ValidationError(_('Order must have customer group id in it.'))
        return attrs

    def to_internal_value(self, data):
        resource = self.context.get('resource')
        available_products = resource.get_products() if resource else []
        self.context.update({'available_products': available_products})
        return super().to_internal_value(data)

    def to_representation(self, instance):
        data = super().to_representation(instance)

        if self.context['view'].action != 'create':
            data.pop('payment_url', None)

        return data


class PaymentsReservationSerializer(ReservationSerializer):
    order = serializers.SlugRelatedField('order_number', read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.context['view'].action == 'create':
            request = self.context.get('request')
            resource = self.context.get('resource')

            if resource and request:
                order_required = resource.has_rent() and not resource.can_bypass_payment(request.user)
            elif resource:
                order_required = resource.has_rent()
            else:
                order_required = True

            self.fields['order'] = ReservationEndpointOrderSerializer(required=order_required)
        elif 'order_detail' in self.context['includes']:
            self.fields['order'] = ReservationEndpointOrderSerializer(read_only=True)

    class Meta(ReservationSerializer.Meta):
        fields = ReservationSerializer.Meta.fields + ['order']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        prefetched_user = self.context.get('prefetched_user', None)
        user = prefetched_user or self.context['request'].user

        if not instance.can_view_product_orders(user):
            data.pop('order', None)
        return data

    def create(self, validated_data):
        order_data = validated_data.pop('order', None)
        reservation = super().create(validated_data)

        if order_data:
            if not reservation.can_add_product_order(self.context['request'].user):
                raise PermissionDenied()

            order_data['reservation'] = reservation
            ReservationEndpointOrderSerializer(context=self.context).create(validated_data=order_data)

        return reservation

    def validate(self, data):
        order_data = data.pop('order', None)
        data = super().validate(data)
        data['order'] = order_data
        return data
