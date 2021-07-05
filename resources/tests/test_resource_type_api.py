# -*- coding: utf-8 -*-
import pytest

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from resources.models import ResourceGroup, ResourceType
from django.urls import reverse

from .utils import assert_response_objects

from django.contrib.auth import get_user_model

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

    content_type = ContentType.objects.get_for_model(ResourceType)
    perm_view = Permission.objects.get(codename='view_resourcetype', content_type=content_type)
    perm_add = Permission.objects.get(codename='add_resourcetype', content_type=content_type)
    perm_change = Permission.objects.get(codename='change_resourcetype', content_type=content_type)
    perm_del = Permission.objects.get(codename='delete_resourcetype', content_type=content_type)
    user.user_permissions.add(perm_view, perm_add, perm_change, perm_del)
    user.save()
    return user


@pytest.fixture
def list_url():
    return reverse('resourcetype-list')


@pytest.mark.django_db
@pytest.fixture
def detail_url(space_resource_type):
    return reverse('resourcetype-detail', kwargs={'pk': space_resource_type.pk})


@pytest.mark.django_db
@pytest.fixture
def resource_type_data():
    return {
        "name": {
            "fi": "työtila",
            "en": "workspace",
            "sv": "arbetsyta"
        },
        "main_type": "space"
    }

@pytest.mark.django_db
def test_resource_type_create_without_model_permissions(api_client, user, list_url, resource_type_data):
    """
    Tests that a user without permissions cannot create a resource type.
    """
    response = api_client.post(list_url, data=resource_type_data)
    assert response.status_code == 401

    api_client.force_authenticate(user=user)
    response = api_client.post(list_url, data=resource_type_data)
    assert response.status_code == 403

@pytest.mark.django_db
def test_resource_type_create_with_model_permissions(api_client, user_with_permissions, list_url, resource_type_data):
    """
    Tests that a user with permissions can create a resource type.
    """
    api_client.force_authenticate(user=user_with_permissions)
    response = api_client.post(list_url, data=resource_type_data)
    assert response.status_code == 201


@pytest.mark.django_db
def test_resource_type_update_without_model_permissions(api_client, user, detail_url, resource_type_data):
    """
    Tests that a user without permissions cannot update a resource type.
    """
    response = api_client.put(detail_url, data=resource_type_data)
    assert response.status_code == 401

    api_client.force_authenticate(user=user)
    response = api_client.put(detail_url, data=resource_type_data)
    assert response.status_code == 403

@pytest.mark.django_db
def test_resource_type_update_with_model_permissions(api_client, user_with_permissions, detail_url, resource_type_data):
    """
    Tests that a user with permissions can update a resource type.
    """
    api_client.force_authenticate(user=user_with_permissions)
    response = api_client.put(detail_url, data=resource_type_data)
    assert response.status_code == 200

@pytest.mark.django_db
def test_resource_group_filter(api_client, resource_in_unit, resource_in_unit2, resource_in_unit3,
                               space_resource_type, list_url):
    type_1 = ResourceType.objects.create(name='test resource type 1')
    resource_in_unit.type = type_1
    resource_in_unit.save()

    type_2 = ResourceType.objects.create(name='test resource type 2')
    resource_in_unit2.type = type_2
    resource_in_unit2.save()

    type_3 = ResourceType.objects.create(name='test resource type 3')
    resource_in_unit3.type = type_3
    resource_in_unit3.save()

    space_resource_type.delete()

    group_1 = ResourceGroup.objects.create(name='test group 1', identifier='test_group_1')
    resource_in_unit.groups.set([group_1])

    group_2 = ResourceGroup.objects.create(name='test group 2', identifier='test_group_2')
    resource_in_unit2.groups.set([group_1, group_2])

    group_3 = ResourceGroup.objects.create(name='test group 3', identifier='test_group_3')
    resource_in_unit3.groups.set([group_3])

    response = api_client.get(list_url)
    assert response.status_code == 200
    assert_response_objects(response, (type_1, type_2, type_3))

    response = api_client.get(list_url + '?' + 'resource_group=' + group_1.identifier)
    assert response.status_code == 200
    assert_response_objects(response, (type_1, type_2))

    response = api_client.get(list_url + '?' + 'resource_group=' + group_2.identifier)
    assert response.status_code == 200
    assert_response_objects(response, type_2)

    response = api_client.get(list_url + '?' + 'resource_group=%s,%s' % (group_2.identifier, group_3.identifier))
    assert response.status_code == 200
    assert_response_objects(response, (type_2, type_3))

    response = api_client.get(list_url + '?' + 'resource_group=foobar')
    assert response.status_code == 200
    assert len(response.data['results']) == 0
