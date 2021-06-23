# -*- coding: utf-8 -*-
import pytest

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from resources.models import Purpose

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

    content_type = ContentType.objects.get_for_model(Purpose)
    perm_view = Permission.objects.get(codename='view_purpose', content_type=content_type)
    perm_add = Permission.objects.get(codename='add_purpose', content_type=content_type)
    perm_change = Permission.objects.get(codename='change_purpose', content_type=content_type)
    perm_del = Permission.objects.get(codename='delete_purpose', content_type=content_type)
    user.user_permissions.add(perm_view, perm_add, perm_change, perm_del)
    user.save()
    return user


@pytest.fixture
def list_url():
    return reverse('purpose-list')


@pytest.mark.django_db
@pytest.fixture
def detail_url(purpose):
    purpose.save()
    return reverse('purpose-detail', kwargs={'pk': purpose.pk})


@pytest.mark.django_db
@pytest.fixture
def purpose_data():
    return {
        "id": "purpose-id",
        "name": {
            "fi": "purpose fi",
            "en": "purpose en",
            "sv": "purpose sv"
        }
    }


@pytest.mark.django_db
def test_purpose_create_without_model_permissions(api_client, user, list_url, purpose_data):
    """
    Tests that a user without permissions cannot create a purpose.
    """
    response = api_client.post(list_url, data=purpose_data)
    assert response.status_code == 401

    api_client.force_authenticate(user=user)
    response = api_client.post(list_url, data=purpose_data)
    assert response.status_code == 403


@pytest.mark.django_db
def test_purpose_create_with_model_permissions(api_client, user_with_permissions, list_url, purpose_data):
    """
    Tests that a user with permissions can create a purpose.
    """
    api_client.force_authenticate(user=user_with_permissions)
    response = api_client.post(list_url, data=purpose_data)
    assert response.status_code == 201


@pytest.mark.django_db
def test_purpose_update_without_model_permissions(api_client, user, detail_url, purpose_data):
    """
    Tests that a user without permissions cannot update a purpose.
    """
    response = api_client.put(detail_url, data=purpose_data)
    assert response.status_code == 401

    api_client.force_authenticate(user=user)
    response = api_client.put(detail_url, data=purpose_data)
    assert response.status_code == 403


@pytest.mark.django_db
def test_purpose_update_with_model_permissions(api_client, user_with_permissions, detail_url, purpose_data):
    """
    Tests that a user with permissions can update a purpose.
    """
    api_client.force_authenticate(user=user_with_permissions)
    response = api_client.put(detail_url, data=purpose_data)
    assert response.status_code == 200


@pytest.mark.django_db
def test_non_public_purpose_visibility(api_client, purpose, user, user_with_permissions, list_url):
    resp = api_client.get(list_url)
    assert resp.status_code == 200
    assert resp.data['count'] == 1

    purpose.public = False
    purpose.save()
    resp = api_client.get(list_url)
    assert resp.status_code == 200
    assert resp.data['count'] == 0

    api_client.force_authenticate(user=user)
    resp = api_client.get(list_url)
    assert resp.status_code == 200
    assert resp.data['count'] == 0

    user.is_general_admin = True
    user.save()
    resp = api_client.get(list_url)
    assert resp.status_code == 200
    assert resp.data['count'] == 1

    user.is_general_admin = False
    user.is_staff = True
    user.save()
    resp = api_client.get(list_url)
    assert resp.status_code == 200
    assert resp.data['count'] == 1

    api_client.force_authenticate(user=user_with_permissions)
    resp = api_client.get(list_url)
    assert resp.status_code == 200
    assert resp.data['count'] == 1
    