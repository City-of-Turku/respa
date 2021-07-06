# -*- coding: utf-8 -*-
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from resources.models import Equipment, ResourceGroup, ResourceEquipment
from django.urls import reverse

from .utils import assert_response_objects, check_only_safe_methods_allowed


pytest.mark.django_db
@pytest.fixture
def user_with_permissions():
    user = get_user_model().objects.create(
        username='test_permission_user',
        first_name='Test',
        last_name='Tester',
        email='test@tester.com',
        preferred_language='en'
    )

    content_type = ContentType.objects.get_for_model(Equipment)
    perm_view = Permission.objects.get(codename='view_equipment', content_type=content_type)
    perm_add = Permission.objects.get(codename='add_equipment', content_type=content_type)
    perm_change = Permission.objects.get(codename='change_equipment', content_type=content_type)
    perm_del = Permission.objects.get(codename='delete_equipment', content_type=content_type)
    user.user_permissions.add(perm_view, perm_add, perm_change, perm_del)
    user.save()
    return user


@pytest.fixture
def list_url():
    return reverse('equipment-list')


@pytest.mark.django_db
@pytest.fixture
def detail_url(equipment):
    return reverse('equipment-detail', kwargs={'pk': equipment.pk})


@pytest.mark.django_db
@pytest.fixture
def equipment_data(equipment_category):
    return {
        "name": {
            "fi": "tuoli",
            "en": "chair",
            "sv": "stol"
        },
        "aliases": [
            {
                "name": "istuin",
                "language": "fi"
            }
        ],
        "category": equipment_category.id
    }


def _check_keys_and_values(result):
    """
    Check that given dict represents equipment data in correct form.
    """
    assert len(result) == 4  # id, name, aliases, category
    assert result['id'] != ''
    assert result['name'] == {'fi': 'test equipment'}
    aliases = result['aliases']
    assert len(aliases) == 1
    assert aliases[0]['name'] == 'test equipment alias'
    assert aliases[0]['language'] == 'fi'
    category = result['category']
    assert category['name'] == {'fi': 'test equipment category'}
    assert category['id'] != ''


@pytest.mark.django_db
def test_equipment_create_without_model_permissions(api_client, user, list_url, equipment_data):
    """
    Tests that a user without permissions cannot create an equipment.
    """
    response = api_client.post(list_url, data=equipment_data)
    assert response.status_code == 401

    api_client.force_authenticate(user=user)
    response = api_client.post(list_url, data=equipment_data)
    assert response.status_code == 403


@pytest.mark.django_db
def test_equipment_create_with_model_permissions(api_client, user_with_permissions, list_url, equipment_data):
    """
    Tests that a user with permissions can create an equipment.
    """
    api_client.force_authenticate(user=user_with_permissions)
    response = api_client.post(list_url, data=equipment_data)
    assert response.status_code == 201


@pytest.mark.django_db
def test_equipment_update_without_model_permissions(api_client, user, detail_url, equipment_data):
    """
    Tests that a user without permissions cannot update an equipment.
    """
    response = api_client.put(detail_url, data=equipment_data)
    assert response.status_code == 401

    api_client.force_authenticate(user=user)
    response = api_client.put(detail_url, data=equipment_data)
    assert response.status_code == 403


@pytest.mark.django_db
def test_equipment_update_with_model_permissions(api_client, user_with_permissions, detail_url, equipment_data):
    """
    Tests that a user with permissions can update an equipment.
    """
    api_client.force_authenticate(user=user_with_permissions)
    response = api_client.put(detail_url, data=equipment_data)
    assert response.status_code == 200


@pytest.mark.django_db
def test_get_equipment_list(api_client, list_url, equipment, equipment_alias):
    """
    Tests that equipment list endpoint return equipment data in correct form.
    """
    response = api_client.get(list_url)
    results = response.data['results']
    assert len(results) == 1
    _check_keys_and_values(results[0])


@pytest.mark.django_db
def test_get_equipment_detail(api_client, detail_url, equipment, equipment_alias):
    """
    Tests that equipment detail endpoint returns equipment data in correct form.
    """
    response = api_client.get(detail_url)
    _check_keys_and_values(response.data)


@pytest.mark.django_db
def test_get_equipment_in_resource(api_client, resource_in_unit, resource_equipment):
    """
    Tests that combined resource equipment and equipment data is available via resource endpoint.

    Equipment aliases should not be included.
    """
    response = api_client.get(reverse('resource-detail', kwargs={'pk': resource_in_unit.pk}))
    equipments = response.data['equipment']
    assert len(equipments) == 1
    equipment = equipments[0]
    assert all(key in equipment for key in ('id', 'name', 'data', 'description'))
    assert 'aliases' not in equipment
    assert len(equipment['data']) == 1
    assert equipment['data']['test_key'] == 'test_value'
    assert equipment['description'] == {'fi': 'test resource equipment'}
    assert equipment['name'] == {'fi': 'test equipment'}


@pytest.mark.django_db
def test_resource_group_filter(api_client, equipment_category, resource_in_unit, resource_in_unit2, resource_in_unit3,
                               list_url):
    equipment_1 = Equipment.objects.create(name='test equipment 1', category=equipment_category)
    ResourceEquipment.objects.create(equipment=equipment_1, resource=resource_in_unit)

    equipment_2 = Equipment.objects.create(name='test equipment 2', category=equipment_category)
    ResourceEquipment.objects.create(equipment=equipment_2, resource=resource_in_unit2)

    equipment_3 = Equipment.objects.create(name='test equipment 3', category=equipment_category)
    ResourceEquipment.objects.create(equipment=equipment_3, resource=resource_in_unit3)

    equipment_4 = Equipment.objects.create(name='test equipment 4', category=equipment_category)
    ResourceEquipment.objects.create(equipment=equipment_4, resource=resource_in_unit)
    ResourceEquipment.objects.create(equipment=equipment_4, resource=resource_in_unit2)

    group_1 = ResourceGroup.objects.create(name='test group 1', identifier='test_group_1')
    resource_in_unit.groups.set([group_1])

    group_2 = ResourceGroup.objects.create(name='test group 2', identifier='test_group_2')
    resource_in_unit2.groups.set([group_1, group_2])

    group_3 = ResourceGroup.objects.create(name='test group 3', identifier='test_group_3')
    resource_in_unit3.groups.set([group_3])

    response = api_client.get(list_url)
    assert response.status_code == 200
    assert_response_objects(response, (equipment_1, equipment_2, equipment_3, equipment_4))

    response = api_client.get(list_url + '?' + 'resource_group=' + group_1.identifier)
    assert response.status_code == 200
    assert_response_objects(response, (equipment_1, equipment_2, equipment_4))

    response = api_client.get(list_url + '?' + 'resource_group=' + group_2.identifier)
    assert response.status_code == 200
    assert_response_objects(response, (equipment_2, equipment_4))

    response = api_client.get(list_url + '?' + 'resource_group=%s,%s' % (group_2.identifier, group_3.identifier))
    assert response.status_code == 200
    assert_response_objects(response, (equipment_2, equipment_3, equipment_4))

    response = api_client.get(list_url + '?' + 'resource_group=foobar')
    assert response.status_code == 200
    assert len(response.data['results']) == 0
