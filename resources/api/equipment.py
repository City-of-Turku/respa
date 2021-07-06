from rest_framework import serializers, viewsets
from rest_framework.permissions import DjangoModelPermissionsOrAnonReadOnly
import django_filters
from rest_framework.relations import PrimaryKeyRelatedField
from .base import TranslatedModelSerializer, register_view
from resources.models import Equipment, EquipmentAlias, EquipmentCategory


class PlainEquipmentSerializer(TranslatedModelSerializer):
    class Meta:
        model = Equipment
        fields = ('name', 'id')


class EquipmentCategorySerializer(TranslatedModelSerializer):
    name = serializers.DictField(required=True)
    equipment = PlainEquipmentSerializer(many=True, read_only=True)

    class Meta:
        model = EquipmentCategory
        fields = ('name', 'id', 'equipment')
        required_translations = ('name_fi', )
        read_only_fields = ('id', )


class PlainEquipmentCategorySerializer(TranslatedModelSerializer):
    class Meta:
        model = EquipmentCategory
        fields = ('name', 'id')


class EquipmentCategoryViewSet(viewsets.ModelViewSet):
    queryset = EquipmentCategory.objects.all()
    serializer_class = EquipmentCategorySerializer
    permission_classes = (DjangoModelPermissionsOrAnonReadOnly, )


register_view(EquipmentCategoryViewSet, 'equipment_category')


class EquipmentAliasSerializer(TranslatedModelSerializer):
    class Meta:
        model = EquipmentAlias
        fields = ('name', 'language')


class EquipmentSerializer(TranslatedModelSerializer):
    name = serializers.DictField(required=True)
    aliases = EquipmentAliasSerializer(
        many=True,
        required=False,
        help_text='Updating aliases will replace all previous aliases with new ones'
    )
    category = PrimaryKeyRelatedField(
        queryset=EquipmentCategory.objects.all(),
        help_text=(
            'To create/update use id of category. '
            'Read response example: "category": {"name": {"fi": "string",..}, "id": "string"}'
        )
    )

    def create(self, validated_data):
        aliases_data = validated_data.pop('aliases', [])
        category = validated_data.pop('category', None)
        if category and isinstance(category, str):
            category = EquipmentCategory.objects.get(pk=category)

        equipment = Equipment.objects.create(category=category, **validated_data)

        for alias_data in aliases_data:
            EquipmentAlias.objects.create(equipment=equipment, **alias_data)

        return equipment

    def update(self, instance, validated_data):
        if 'aliases' in validated_data:
            EquipmentAlias.objects.filter(equipment=instance).delete()
            aliases_data = validated_data.pop('aliases', None)
            for alias_data in aliases_data:
                EquipmentAlias.objects.create(equipment=instance, **alias_data)

        return super().update(instance, validated_data)

    def to_representation(self, obj):
        category_id = obj.category.pk
        ret = super().to_representation(obj)
        category = EquipmentCategory.objects.get(pk=category_id)
        ret['category'] = PlainEquipmentCategorySerializer().to_representation(category)
        return ret

    class Meta:
        model = Equipment
        fields = ('name', 'id', 'aliases', 'category')
        required_translations = ('name_fi', )
        read_only_fields = ('id', )


class EquipmentFilterSet(django_filters.FilterSet):
    resource_group = django_filters.Filter(field_name='resource_equipment__resource__groups__identifier', lookup_expr='in',
                                           widget=django_filters.widgets.CSVWidget, distinct=True)

    class Meta:
        model = Equipment
        fields = ('resource_group',)


class EquipmentViewSet(viewsets.ModelViewSet):
    queryset = Equipment.objects.all()
    serializer_class = EquipmentSerializer
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = EquipmentFilterSet
    permission_classes = (DjangoModelPermissionsOrAnonReadOnly, )


register_view(EquipmentViewSet, 'equipment')
