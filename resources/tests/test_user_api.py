# -*- coding: utf-8 -*-
import pytest

from django.urls import reverse
from guardian.shortcuts import assign_perm

from users.models import ExtraPrefs

from .utils import check_only_safe_methods_allowed
from resources.tests.test_api import JWTMixin


@pytest.fixture
def list_url():
    return reverse('user-list')


@pytest.mark.django_db
@pytest.fixture
def detail_url(user):
    return reverse('user-detail', kwargs={'pk': user.pk})


@pytest.fixture
def extra_prefs(user, db):
    return ExtraPrefs.objects.create(user=user, admin_resource_order=['res1id', 'res2id', 'res3id'])


@pytest.mark.django_db
def test_disallowed_methods(all_user_types_api_client, list_url, detail_url):
    """
    Tests that only safe methods are allowed to user list and detail endpoints.
    """
    check_only_safe_methods_allowed(all_user_types_api_client, (list_url, detail_url))


@pytest.mark.django_db
def test_user_perms(api_client, list_url, staff_user, user, test_unit):
    api_client.force_authenticate(user=user)
    response = api_client.get(list_url)
    assert response.status_code == 200
    assert response.data['count'] == 1
    user_data = response.data['results'][0]
    assert not user_data['staff_perms']

    api_client.force_authenticate(user=staff_user)
    response = api_client.get(list_url)
    assert response.status_code == 200
    assert response.data['count'] == 1
    user_data = response.data['results'][0]
    assert not user_data['staff_perms']

    assign_perm('unit:can_approve_reservation', staff_user, test_unit)
    response = api_client.get(list_url)
    assert response.status_code == 200
    assert response.data['count'] == 1
    user_data = response.data['results'][0]
    perms = user_data['staff_perms']
    assert list(perms.keys()) == ['unit']
    perms = perms['unit']
    assert list(perms.items()) == [(test_unit.id, ['can_approve_reservation'])]


@pytest.mark.django_db
def test_inactive_user(api_client, detail_url, user, test_unit):
    auth = JWTMixin.get_auth(user)

    response = api_client.get(detail_url, HTTP_AUTHORIZATION=auth)
    assert response.status_code == 200

    user.is_active = False
    user.save()
    response = api_client.get(detail_url, HTTP_AUTHORIZATION=auth)
    assert response.status_code == 401


@pytest.mark.django_db
def test_get_user_without_extra_prefs(api_client, list_url, user):
    api_client.force_authenticate(user=user)
    response = api_client.get(list_url)
    assert response.status_code == 200
    assert response.data['count'] == 1
    user_data = response.data['results'][0]
    assert user_data['extra_prefs'] == None


@pytest.mark.django_db
def test_get_user_with_extra_prefs(api_client, list_url, user, extra_prefs):
    api_client.force_authenticate(user=user)
    response = api_client.get(list_url)
    assert response.status_code == 200
    assert response.data['count'] == 1
    user_data = response.data['results'][0]
    assert user_data['extra_prefs'] == {'admin_resource_order': ['res1id', 'res2id', 'res3id']}


@pytest.mark.django_db
@pytest.mark.parametrize('admin_resource_order, expected', (
    (['res9id', 'res8id', 'res7id'], ['res9id', 'res8id', 'res7id']),
    ([], []),
    ('', []),
))
def test_set_admin_resource_order_for_user_without_extra_prefs(api_client, user, list_url, admin_resource_order, expected):
    url = '%sset_admin_resource_order/' % list_url
    api_client.force_authenticate(user=user)
    response = api_client.post(url, data={'admin_resource_order': admin_resource_order}, format='json')
    assert response.status_code == 200
    extra_prefs = ExtraPrefs.objects.get(user=user)
    assert extra_prefs.admin_resource_order == expected


@pytest.mark.django_db
@pytest.mark.parametrize('admin_resource_order, expected', (
    (['123', '456'], ['123', '456']),
    ([], []),
    ('', []),
))
def test_set_admin_resource_order_for_user_with_extra_prefs(api_client, user, list_url, extra_prefs, admin_resource_order, expected):
    url = '%sset_admin_resource_order/' % list_url
    api_client.force_authenticate(user=user)
    response = api_client.post(url, data={'admin_resource_order': admin_resource_order}, format='json')
    assert response.status_code == 200
    extra_prefs = ExtraPrefs.objects.get(user=user)
    assert extra_prefs.admin_resource_order == expected


@pytest.mark.django_db
def test_set_admin_resource_order_without_data(api_client, user, list_url, extra_prefs):
    url = '%sset_admin_resource_order/' % list_url
    api_client.force_authenticate(user=user)

    response = api_client.post(url, data={'admin_resource_order': None}, format='json')
    assert response.status_code == 400
    extra_prefs = ExtraPrefs.objects.get(user=user)
    assert extra_prefs.admin_resource_order == ['res1id', 'res2id', 'res3id']

    response = api_client.post(url, data={}, format='json')
    assert response.status_code == 400
    extra_prefs = ExtraPrefs.objects.get(user=user)
    assert extra_prefs.admin_resource_order == ['res1id', 'res2id', 'res3id']


@pytest.mark.django_db
def test_set_admin_resource_order_with_invalid_data(api_client, user, list_url, extra_prefs):
    url = '%sset_admin_resource_order/' % list_url
    api_client.force_authenticate(user=user)

    response = api_client.post(url, data={'admin_resource_order': 1}, format='json')
    assert response.status_code == 400
    extra_prefs = ExtraPrefs.objects.get(user=user)
    assert extra_prefs.admin_resource_order == ['res1id', 'res2id', 'res3id']

    response = api_client.post(url, data={'admin_resource_order': {}}, format='json')
    assert response.status_code == 400
    extra_prefs = ExtraPrefs.objects.get(user=user)
    assert extra_prefs.admin_resource_order == ['res1id', 'res2id', 'res3id']
