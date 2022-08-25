from django.utils.translation import ugettext_lazy as _
from django.db.models import Q
from rest_framework import exceptions, serializers, status
from rest_framework.exceptions import PermissionDenied
from dateutil.parser import parse

from payments.exceptions import (
    DuplicateOrderError, PayloadValidationError, RespaPaymentError, ServiceUnavailableError, UnknownReturnCodeError
)
from payments.utils import is_free
from resources.api.reservation import ReservationSerializer
from resources.models.reservation import RESERVATION_BILLING_FIELDS, Reservation

from ..models import CustomerGroup, OrderCustomerGroupData, OrderLine, Product, ProductCustomerGroup, Order
from ..providers import get_payment_provider
from .base import OrderSerializerBase


MODIFIABLE_FIELDS = (
    'state',
    'begin',
    'end',
)

class ReservationEndpointOrderSerializer(OrderSerializerBase):
    id = serializers.ReadOnlyField(source='order_number')
    return_url = serializers.CharField(write_only=True)
    payment_url = serializers.SerializerMethodField()
    customer_group = serializers.CharField(write_only=True, required=False)

    class Meta(OrderSerializerBase.Meta):
        fields = OrderSerializerBase.Meta.fields + ('id', 'return_url',
            'payment_url', 'customer_group', 'is_requested_order', 'payment_method')

    def create(self, validated_data):
        order_lines_data = validated_data.pop('order_lines', [])
        customer_group = validated_data.pop('customer_group', None)
        return_url = validated_data.pop('return_url', '')
        order = super().create(validated_data)
        try:
            order.customer_group = CustomerGroup.objects.get(id=customer_group)
        except:
            order.customer_group = None
        reservation = validated_data['reservation']

        for order_line_data in order_lines_data:
            product = order_line_data['product']
            order_line = OrderLine.objects.create(order=order, **order_line_data)
            prod_cg = ProductCustomerGroup.objects.filter(product=product, customer_group__id=customer_group)
            ocgd = OrderCustomerGroupData.objects.create(order_line=order_line,
            product_cg_price=prod_cg.get_price_for(order_line.product))
            if prod_cg:
                ocgd.copy_translated_fields(prod_cg.first().customer_group)
                ocgd.price_is_based_on_product_cg = True
            ocgd.save()

        resource = reservation.resource
        request = self.context.get('request')
        has_staff_perms = resource.is_viewer(request.user) or resource.is_manager(request.user) or resource.is_admin(request.user)
        # non staff members i.e. customers don't pay for manually confirmed reservations in creation
        # free manually confirmed orders are handled in the payment provider
        if not has_staff_perms and not is_free(order.get_price()):
            if reservation.state == Reservation.CREATED and resource.need_manual_confirmation:
                order.state = Order.WAITING
                order.save()
                return order

        # staff cash payments
        if has_staff_perms and order.payment_method == Order.CASH and resource.cash_payments_allowed:
            if reservation.state == Reservation.CREATED and resource.need_manual_confirmation:
                if is_free(order.get_price()):
                    order.state = Order.CONFIRMED
                else:
                    order.state = Order.WAITING
                order.save()
                return order

        payments = get_payment_provider(request=self.context['request'],
                                        ui_return_url=return_url)
        try:
            self.context['payment_url'] = payments.initiate_payment(order)
            order.payment_url = self.context['payment_url']
            order.save()
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


    def update(self, instance, validated_data):
        validated_data.pop('order_lines', [])
        validated_data.pop('customer_group', None)
        return_url = validated_data.pop('return_url', '')

        order = super().update(instance, validated_data)
        payments = get_payment_provider(request=self.context['request'],
                                ui_return_url=return_url)
        try:
            self.context['payment_url'] = payments.initiate_payment(order)
            order.payment_url = self.context['payment_url']
            order.save()
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
        request = self.context['request']
        attrs = super().validate(attrs)
        if request.method in ('PUT', 'PATCH'):
            return attrs

        customer_group = attrs.get('customer_group', None)
        resource = self.context.get('resource')
        for product in resource.get_products():
            if product.has_customer_group() and not customer_group:
                raise serializers.ValidationError(_('Order must have customer group id in it.'))

        payment_method = attrs.get('payment_method', None)
        if payment_method and payment_method == Order.CASH and not resource.cash_payments_allowed:
            raise serializers.ValidationError(
                {'payment_method': _('Cash payments are not allowed for this resource')})
        return attrs

    def to_internal_value(self, data):
        resource = self.context.get('resource')
        available_products = resource.get_products() if resource else []
        self.context.update({'available_products': available_products})
        return super().to_internal_value(data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if self.context['view'].action not in ('create', 'update'):
            data.pop('payment_url', None)

        return data


class PaymentsReservationSerializer(ReservationSerializer):
    order = serializers.SlugRelatedField('order_number', read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get('request')
        resource = self.context.get('resource')
        action = self.context['view'].action

        if resource and request:
            order_required = resource.has_rent() and not resource.can_bypass_payment(request.user)
        elif resource:
            order_required = resource.has_rent()
        else:
            order_required = True

        if action == 'create':
            self.fields['order'] = ReservationEndpointOrderSerializer(required=order_required, context=self.context)
        elif action == 'update':
            order_required = not self.instance.can_modify(request.user)
            self.fields['order'] = ReservationEndpointOrderSerializer(required=order_required, context=self.context, instance=self.instance)
        elif 'order_detail' in self.context['includes']:
            self.fields['order'] = ReservationEndpointOrderSerializer(read_only=True, context=self.context)

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
        prefetched_user = self.context.get('prefetched_user', None)
        user = prefetched_user or self.context['request'].user

        if order_data:
            if not reservation.can_add_product_order(self.context['request'].user):
                raise PermissionDenied()

            order_data['reservation'] = reservation
            resource = reservation.resource
            if resource.need_manual_confirmation and not resource.can_bypass_manual_confirmation(user):
                order_data['is_requested_order'] = True

            ReservationEndpointOrderSerializer(context=self.context, instance=reservation).create(validated_data=order_data)

        return reservation

    def update(self, instance, validated_data):
        if instance.has_order() and any(field for field in self._changed_fields if field[0] in ('Begin', 'End')):
            setattr(self, '__old_price', instance.get_order().get_price())

        order_data = validated_data.pop('order', None)
        if order_data and instance.resource.need_manual_confirmation:
            if not instance.can_add_product_order(self.context['request'].user):
                raise PermissionDenied()

            order_data['reservation'] = instance
            ReservationEndpointOrderSerializer(context=self.context, instance=instance).update(instance.get_order(), validated_data=order_data)
        instance = super().update(instance, validated_data)
        if instance.has_order():
            order = instance.get_order()
            modified = '\n'.join([f'{key}: {val}' for key,val in self._changed_fields])
            if hasattr(self, '__old_price') and order.get_price() != getattr(self, '__old_price'):
                modified += f"\nPrice: {getattr(self, '__old_price')} -> {order.get_price()}"
            order.create_log_entry('Order reservation was modified.\n%s' % modified, order.state)
        return super().update(instance, validated_data)


    def validate(self, data):
        order_data = data.pop('order', None)
        data = super().validate(data)
        data['order'] = order_data

        request = self.context['request']
        if request.method in ('PUT', 'PATCH'):
            return self.validate_update(data)
        return data

    def validate_update(self, data):
        self._get_changed_fields(data)
        order = self.instance.get_order()
        if not order:
            return data

        request = self.context['request']
        resource = data['resource']
        required = self.get_required_fields()
        for field in required:
            if field not in data:
                raise serializers.ValidationError({field: _('This field is required.')})

        order_data = data.pop('order', None)
        for key, val in data.items():
            if key in set(RESERVATION_BILLING_FIELDS) | set(MODIFIABLE_FIELDS):
                continue

            attr = getattr(self.instance, key)
            if val != attr and not self.instance.can_modify(request.user):
                raise serializers.ValidationError(_('Cannot change field: %s' % key))
        data['order'] = order_data
        return data


    def _get_changed_fields(self, data):
        self._changed_fields = []
        for key, val in data.items():
            if key not in set(RESERVATION_BILLING_FIELDS) | set(MODIFIABLE_FIELDS):
                continue
            attr = getattr(self.instance, key)
            if val != attr:
                if key in ('begin', 'end'):
                    val = val.strftime('%Y-%m-%d %H:%M:%S')
                    attr = attr.strftime('%Y-%m-%d %H:%M:%S')
                key = key.replace('_',' ').capitalize()
                changed = '%s -> %s' % (attr, val)
                self._changed_fields.append(
                    (key, changed)
                )
