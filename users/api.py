from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from rest_framework import permissions, serializers, generics, mixins, viewsets, response, status
from rest_framework.decorators import action

from resources.models.utils import build_ical_feed_url
from resources.models import Unit
from users.models import ExtraPrefs


all_views = []


def register_view(klass, name, base_name=None):
    entry = {'class': klass, 'name': name}
    if base_name is not None:
        entry['base_name'] = base_name
    all_views.append(entry)


class ResourceOrderSerializer(serializers.Field):
    def to_representation(self, value):
        if isinstance(value, list):
            return value
        return value.split(',')

    def to_internal_value(self, data):
        if isinstance(data, str):
            if not data:
                return []
            return data.split(',')
        elif isinstance(data, list):
            return data
        else:
            raise ValidationError("Value must be a list or a comma-separated string")


class ExtraPrefsSerializer(serializers.ModelSerializer):
    admin_resource_order = ResourceOrderSerializer(required=False)

    class Meta:
        model = ExtraPrefs
        fields = ['admin_resource_order']


class UserSerializer(serializers.ModelSerializer):
    display_name = serializers.ReadOnlyField(source='get_display_name')
    ical_feed_url = serializers.SerializerMethodField()
    staff_perms = serializers.SerializerMethodField()
    staff_status = serializers.SerializerMethodField()
    is_strong_auth = serializers.SerializerMethodField()

    class Meta:
        fields = [
            'last_login', 'username', 'email', 'date_joined',
            'first_name', 'last_name', 'uuid', 'department_name',
            'is_staff', 'display_name', 'ical_feed_url', 'staff_status',
            'staff_perms', 'favorite_resources', 'preferred_language', 'birthdate',
            'is_strong_auth'
        ]
        model = get_user_model()

    def get_is_strong_auth(self, obj):
        return obj.is_strong_auth

    def get_staff_status(self, obj):
        units = Unit.objects.all()
        staff_perm = {}
        if obj.is_staff:
            staff_perm.update({
                'is_staff':True
            })

        if obj.is_general_admin:
            staff_perm.update({
                'is_general_admin':True
            })
        if obj.is_superuser:
            staff_perm.update({
                'is_superuser':True
            })
        staff_perm.update({
            'is_manager_for': []
        })
        for unit in units:
            if unit.is_manager(obj):
                staff_perm['is_manager_for'].append(unit.id)

        if len(staff_perm['is_manager_for']) == 0:
            del staff_perm['is_manager_for']

        return staff_perm

    def get_ical_feed_url(self, obj):
        return build_ical_feed_url(obj.get_or_create_ical_token(), self.context['request'])

    def get_staff_perms(self, obj):
        perm_objs = obj.userobjectpermission_set.all()
        perms = {}
        # We support only units for now
        for p in perm_objs:
            if p.content_type.model_class() != Unit:
                continue
            obj_perms = perms.setdefault(p.object_pk, [])
            perm_name = p.permission.codename
            if perm_name.startswith('unit:'):
                perm_name = perm_name[5:]
            obj_perms.append(perm_name)
        if not perms:
            return {}
        return {'unit': perms}

    def to_representation(self, instance):
        data = super(UserSerializer, self).to_representation(instance)
        user = self.context['request'].user
        try:
            extra_prefs = ExtraPrefs.objects.get(user=user)
            data['extra_prefs'] = ExtraPrefsSerializer(extra_prefs).data
        except ObjectDoesNotExist:
            data['extra_prefs'] = None

        if user.id != instance.id:
            data.pop('birthdate', None)
            data.pop('oid', None)
        return data


class UserViewSet(viewsets.ReadOnlyModelViewSet):

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return self.queryset
        else:
            return self.queryset.filter(pk=user.pk)

    def get_object(self):
        username = self.kwargs.get('username', None)
        if username:
            qs = self.get_queryset()
            obj = generics.get_object_or_404(qs, username=username)
        else:
            obj = self.request.user
        return obj

    def _set_admin_resource_order(self, request):
        user = self.request.user
        value = request.data.get('admin_resource_order', None)
        if isinstance(value, str):
            value = value.split(',')

        if not isinstance(value, list):
            return response.Response({'detail': 'Invalid input format. Value must be a list of resource IDs'}, status=status.HTTP_400_BAD_REQUEST)

        if value or value == []:
            extra_prefs, created = ExtraPrefs.objects.get_or_create(user=user)

            extra_prefs.admin_resource_order = value
            extra_prefs.save()
            return response.Response(status=status.HTTP_200_OK)

        return response.Response(status=status.HTTP_304_NOT_MODIFIED)

    @action(detail=False, methods=['post'])
    def set_admin_resource_order(self, request, pk=None):
        return self._set_admin_resource_order(request)

    permission_classes = [permissions.IsAuthenticated]
    queryset = get_user_model().objects.all()
    serializer_class = UserSerializer

register_view(UserViewSet, 'user')
