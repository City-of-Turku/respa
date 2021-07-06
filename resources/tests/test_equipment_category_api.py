# -*- coding: utf-8 -*-
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from resources.models import EquipmentCategory
from django.urls import reverse


@pytest.mark.django_db
@pytest.fixture
def user_with_permissions():
    user = get_user_model().objects.create(
        username='test_permission_user',
        first_name='Test',
        last_name='Tester',
        email='test@tester.com',
        preferred_language='en'
    )

    content_type = ContentType.objects.get_for_model(EquipmentCategory)
    perm_view = Permission.objects.get(codename='view_equipmentcategory', content_type=content_type)
    perm_add = Permission.objects.get(codename='add_equipmentcategory', content_type=content_type)
    perm_change = Permission.objects.get(codename='change_equipmentcategory', content_type=content_type)
    perm_del = Permission.objects.get(codename='delete_equipmentcategory', content_type=content_type)
    user.user_permissions.add(perm_view, perm_add, perm_change, perm_del)
    user.save()
    return user

@pytest.fixture
def list_url():
    return reverse('equipmentcategory-list')


@pytest.mark.django_db
@pytest.fixture
def detail_url(equipment_category):
    return reverse('equipmentcategory-detail', kwargs={'pk': equipment_category.pk})


@pytest.mark.django_db
@pytest.fixture
def equipment_category_data():
    return {
        "name": {
            "fi": "kaluste",
            "en": "furniture",
            "sv": "möbel"
        }
    }


def _check_keys_and_values(result):
    """
    Check that given dict represents equipment data in correct form.
    """
    assert len(result) == 3  # id, name, equipments
    assert result['id'] != ''
    assert result['name'] == {'fi': 'test equipment category'}
    equipments = result['equipment']
    assert len(equipments) == 1
    equipment = equipments[0]
    assert len(equipment) == 2
    assert equipment['name'] == {'fi': 'test equipment'}
    assert equipment['id'] != ''


@pytest.mark.django_db
def test_equipment_category_create_without_model_permissions(api_client, user, list_url, equipment_category_data):
    """
    Tests that a user without permissions cannot create an equipment category.
    """
    response = api_client.post(list_url, data=equipment_category_data)
    assert response.status_code == 401

    api_client.force_authenticate(user=user)
    response = api_client.post(list_url, data=equipment_category_data)
    assert response.status_code == 403


@pytest.mark.django_db
def test_equipment_category_create_with_model_permissions(api_client, user_with_permissions, list_url, equipment_category_data):
    """
    Tests that a user with permissions can create an equipment category.
    """
    api_client.force_authenticate(user=user_with_permissions)
    response = api_client.post(list_url, data=equipment_category_data)
    assert response.status_code == 201


@pytest.mark.django_db
def test_equipment_category_update_without_model_permissions(api_client, user, detail_url, equipment_category_data):
    """
    Tests that a user without permissions cannot update an equipment category.
    """
    response = api_client.put(detail_url, data=equipment_category_data)
    assert response.status_code == 401

    api_client.force_authenticate(user=user)
    response = api_client.put(detail_url, data=equipment_category_data)
    assert response.status_code == 403


@pytest.mark.django_db
def test_equipment_category_update_with_model_permissions(api_client, user_with_permissions, detail_url, equipment_category_data):
    """
    Tests that a user with permissions can update an equipment category.
    """
    api_client.force_authenticate(user=user_with_permissions)
    response = api_client.put(detail_url, data=equipment_category_data)
    assert response.status_code == 200


@pytest.mark.django_db
def test_get_equipment_category_list(api_client, list_url, equipment):
    """
    Tests that equipment category list endpoint returns equipment category data in correct form.
    """
    response = api_client.get(list_url)
    results = response.data['results']
    assert len(results) == 1
    _check_keys_and_values(results[0])


@pytest.mark.django_db
def test_get_equipment_category_detail(api_client, detail_url, equipment):
    """
    Tests that equipment category detail endpoint returns equipment category data in correct form.
    """
    response = api_client.get(detail_url)
    _check_keys_and_values(response.data)
