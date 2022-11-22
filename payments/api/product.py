from payments.models import (
    ARCHIVED_AT_NONE, CustomerGroupTimeSlotPrice, Product, CustomerGroup,
    ProductCustomerGroup, TimeSlotPrice, CustomerGroupLoginMethod
)
from rest_framework import serializers, viewsets
from resources.api.base import TranslatedModelSerializer, register_view
from rest_framework.permissions import DjangoModelPermissions

class CustomerGroupLoginMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerGroupLoginMethod
        fields = ('login_method_id', )

class CustomerGroupSerializer(TranslatedModelSerializer):
    only_for_login_methods = CustomerGroupLoginMethodSerializer(many=True)
    class Meta:
        model = CustomerGroup
        fields = ('id', 'name', 'only_for_login_methods')

class ProductCustomerGroupSerializer(TranslatedModelSerializer):
    customer_group = CustomerGroupSerializer()
    class Meta:
        model = ProductCustomerGroup
        fields = ('id', 'price', 'customer_group')


class CustomerGroupTimeSlotPriceSerializer(TranslatedModelSerializer):
    customer_group = CustomerGroupSerializer()
    class Meta:
        model = CustomerGroupTimeSlotPrice
        fields = ('id', 'price', 'customer_group')


class TimeSlotPriceSerializer(TranslatedModelSerializer):
    customer_group_time_slot_prices = CustomerGroupTimeSlotPriceSerializer(many=True, required=False)
    class Meta:
        model = TimeSlotPrice
        fields = ('id', 'begin', 'end', 'price', 'customer_group_time_slot_prices')


class ProductSerializer(TranslatedModelSerializer):
    name = serializers.DictField(required=False)
    description = serializers.DictField(required=False)
    product_customer_groups = serializers.SerializerMethodField()
    time_slot_prices = TimeSlotPriceSerializer(many=True, required=False)

    class Meta:
        model = Product
        fields = '__all__'
        required_translations = ('name_fi', 'description_fi',)

    def get_product_customer_groups(self, obj):
        prod_groups = ProductCustomerGroup.objects.filter(product=obj)
        serializer = ProductCustomerGroupSerializer(prod_groups, many=True)
        return serializer.data


class ProductPermissions(DjangoModelPermissions):
    view_permissions = ['%(app_label)s.view_%(model_name)s']

    perms_map = {
        'GET': view_permissions,
        'OPTIONS': view_permissions,
        'HEAD': view_permissions,
        'POST': DjangoModelPermissions.perms_map['POST'],
        'PUT': DjangoModelPermissions.perms_map['PUT'],
        'PATCH': DjangoModelPermissions.perms_map['PATCH'],
        'DELETE': DjangoModelPermissions.perms_map['DELETE'],
    }


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.filter(archived_at=ARCHIVED_AT_NONE)
    serializer_class = ProductSerializer
    permission_classes = (ProductPermissions, )

    def update(self, request, *args, **kwargs):
        """
        Updating an existing product will archive/hide the updated product
        and a new product with updated data will be created to replace the old one.
        """
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """
        Updating an existing product will archive/hide the updated product
        and a new product with updated data will be created to replace the old one.
        """
        return super().partial_update(request, *args, **kwargs)

    def get_serializer_context(self):
        context = super(ProductViewSet, self).get_serializer_context()
        return context


register_view(ProductViewSet, 'product')
