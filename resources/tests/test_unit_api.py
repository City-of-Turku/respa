# -*- coding: utf-8 -*-
import datetime
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
import pytest

from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time

from resources.models import Unit, ResourceGroup
from .utils import assert_response_objects, MAX_QUERIES


@pytest.fixture
def list_url():
    return reverse('unit-list')


@pytest.mark.django_db
@pytest.fixture
def detail_url(test_unit):
    return reverse('unit-detail', kwargs={'pk': test_unit.pk})

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

    content_type = ContentType.objects.get_for_model(Unit)
    perm_view = Permission.objects.get(codename='view_unit', content_type=content_type)
    perm_add = Permission.objects.get(codename='add_unit', content_type=content_type)
    perm_change = Permission.objects.get(codename='change_unit', content_type=content_type)
    perm_del = Permission.objects.get(codename='delete_unit', content_type=content_type)
    user.user_permissions.add(perm_view, perm_add, perm_change, perm_del)
    user.save()
    return user
    

@pytest.mark.django_db
@pytest.fixture
def unit_data():
    return {
        "id": "unit-id",
        "name": {
            "fi": "unit fi",
            "en": "unit en",
            "sv": "unit sv"
        },
        "street_address": {
            "fi": "street fi"
        }
    }


@pytest.mark.django_db
def test_unit_create_without_model_permissions(api_client, user, list_url, unit_data):
    """
    Tests that a user without permissions cannot create a unit.
    """
    response = api_client.post(list_url, data=unit_data)
    assert response.status_code == 401

    api_client.force_authenticate(user=user)
    response = api_client.post(list_url, data=unit_data)
    assert response.status_code == 403


@pytest.mark.django_db
def test_unit_create_with_model_permissions(api_client, user_with_permissions, list_url, unit_data):
    """
    Tests that a user with permissions can create a unit.
    """
    api_client.force_authenticate(user=user_with_permissions)
    response = api_client.post(list_url, data=unit_data)
    assert response.status_code == 201


@pytest.mark.django_db
def test_unit_update_without_model_permissions(api_client, user, detail_url, unit_data):
    """
    Tests that a user without permissions cannot update a unit.
    """
    response = api_client.put(detail_url, data=unit_data)
    assert response.status_code == 401

    api_client.force_authenticate(user=user)
    response = api_client.put(detail_url, data=unit_data)
    assert response.status_code == 403


@pytest.mark.django_db
def test_unit_update_with_model_permissions(api_client, user_with_permissions, detail_url, unit_data):
    """
    Tests that a user with permissions can update a unit.
    """
    api_client.force_authenticate(user=user_with_permissions)
    response = api_client.put(detail_url, data=unit_data)
    assert response.status_code == 200


@freeze_time('2016-10-25')
@pytest.mark.django_db
def test_reservable_in_advance_fields(api_client, test_unit, detail_url):
    response = api_client.get(detail_url)
    assert response.status_code == 200

    assert response.data['reservable_max_days_in_advance'] is None
    assert response.data['reservable_before'] is None

    test_unit.reservable_max_days_in_advance = 6
    test_unit.save()

    response = api_client.get(detail_url)
    assert response.status_code == 200

    assert response.data['reservable_max_days_in_advance'] == 6
    before = timezone.localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=6)
    assert response.data['reservable_before'] == before


@pytest.mark.django_db
def test_resource_group_filter(api_client, test_unit, test_unit2, test_unit3, resource_in_unit, resource_in_unit2,
                               resource_in_unit3, list_url):
    # test_unit has 2 resources, test_unit3 none
    resource_in_unit3.unit = test_unit
    resource_in_unit3.save()

    group_1 = ResourceGroup.objects.create(name='test group 1', identifier='test_group_1')
    resource_in_unit.groups.set([group_1])
    resource_in_unit3.groups.set([group_1])

    group_2 = ResourceGroup.objects.create(name='test group 2', identifier='test_group_2')
    resource_in_unit2.groups.set([group_1, group_2])

    response = api_client.get(list_url)
    assert response.status_code == 200
    assert_response_objects(response, (test_unit, test_unit2, test_unit3))

    response = api_client.get(list_url + '?' + 'resource_group=' + group_1.identifier)
    assert response.status_code == 200
    assert_response_objects(response, (test_unit, test_unit2))

    response = api_client.get(list_url + '?' + 'resource_group=' + group_2.identifier)
    assert response.status_code == 200
    assert_response_objects(response, test_unit2)

    response = api_client.get(list_url + '?' + 'resource_group=%s,%s' % (group_1.identifier, group_2.identifier))
    assert response.status_code == 200
    assert_response_objects(response, (test_unit, test_unit2))

    response = api_client.get(list_url + '?' + 'resource_group=foobar')
    assert response.status_code == 200
    assert len(response.data['results']) == 0


@pytest.mark.django_db
def test_unit_has_resource_filter(api_client, test_unit,
                               resource_in_unit2, list_url):

    response = api_client.get(list_url + '?' + 'unit_has_resource=True')
    assert response.status_code == 200
    assert_response_objects(response, (resource_in_unit2.unit))

    response = api_client.get(list_url + '?' + 'unit_has_resource=False')
    assert response.status_code == 200
    assert_response_objects(response, (test_unit))


@pytest.mark.django_db
def test_query_counts(user_api_client, staff_api_client, list_url, django_assert_max_num_queries):
    """
    Test that DB query count is less than allowed
    """
    with django_assert_max_num_queries(MAX_QUERIES):
        user_api_client.get(list_url)

    with django_assert_max_num_queries(MAX_QUERIES):
        staff_api_client.get(list_url)
