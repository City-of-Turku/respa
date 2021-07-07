from payments.models import ARCHIVED_AT_NONE, Product
from rest_framework import serializers, viewsets
from resources.api.base import TranslatedModelSerializer, register_view
from rest_framework.permissions import DjangoModelPermissions


class ProductSerializer(TranslatedModelSerializer):
    name = serializers.DictField(required=False)
    description = serializers.DictField(required=False)

    class Meta:
        model = Product
        fields = '__all__'
        required_translations = ('name_fi', 'description_fi',)


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


register_view(ProductViewSet, 'product')