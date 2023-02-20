# -*- coding: utf-8 -*-
import pytest

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from resources.models import ResourceUniversalField, ResourceUniversalFormOption
from django.urls import reverse

from .utils import assert_response_objects

from django.contrib.auth import get_user_model


LANGUAGES = ['fi', 'sv', 'en']

def list_universal_field_url():
    return reverse('resourceuniversalfield-list')


def list_universal_form_option_url():
    return reverse('resourceuniversalformoption-list')


def get_detail_universal_field_url(universal_field):
    return reverse('resourceuniversalfield-detail',kwargs={'pk': universal_field.pk})


def get_detail_universal_form_option_url(form_option):
    return reverse('resourceuniversalformoption-detail',kwargs={'pk': form_option.pk})


def check_keys_and_values_unchanged(validate_keys = [], initial_data = {}, updated_data = {}):
    """
    Check that values for validate_keys are identical in initial_data and updated_data.
    """
    for x in validate_keys:
        if x in ('description', 'label'):
            for lang in LANGUAGES:
                assert initial_data[x][lang] == updated_data[x][lang]
        else:
            assert initial_data[x] == updated_data[x]


def check_certain_lang_value_changed(initial_data = {}, updated_data = {}, unchanged_keys = [], changed_keys = []):
    """
    Check that values for unchanged_keys haven't changed and that only values for changed_keys have changed.
    """
    for key in unchanged_keys:
        assert initial_data[key] == updated_data[key]

    for key in changed_keys:
        assert initial_data[key] != updated_data[key]


def make_universal_field_data(resource, field_type, identifier):
    return {
        'field_type':{'type': field_type},
        'description': {
            'fi': f'Finnish description {identifier}',
            'sv': f'Swedish description {identifier}',
            'en': f'English description {identifier}'
        },
        'label': {
            'fi': f'Finnish label {identifier}',
            'sv': f'Swedish label {identifier}',
            'en': f'English label {identifier}'
        },
        'resource': resource.id,
        'name': f'Newly added field {identifier}'
        }


@pytest.fixture
def make_form_option_data():
    def _make_form_option_data(universal_field, identifier, sort_order = 0):
        return {
            'text': {
            'fi': f'fi text {identifier}',
            'sv': f'sv text {identifier}',
            'en': f'en text {identifier}'
        },
        'resource_universal_field': universal_field.id,
        'name': f'Option name {identifier}',
        'sort_order': sort_order,
        'resource': universal_field.resource.id
        }
    return _make_form_option_data


@pytest.mark.django_db
@pytest.fixture
def user_with_permissions():
    user = get_user_model().objects.create(
        username='test_permission_user_universal_field_n_option',
        first_name='Test',
        last_name='Tester',
        email='test@tester.com',
        preferred_language='en'
    )

    models = {'resourceuniversalformoption': ResourceUniversalFormOption,'resourceuniversalfield': ResourceUniversalField}
    for k, v in models.items():
        content_type = ContentType.objects.get_for_model(v)
        perm_view = Permission.objects.get(codename=f'view_{k}', content_type=content_type)
        perm_add = Permission.objects.get(codename=f'add_{k}', content_type=content_type)
        perm_change = Permission.objects.get(codename=f'change_{k}', content_type=content_type)
        perm_del = Permission.objects.get(codename=f'delete_{k}', content_type=content_type)
        user.user_permissions.add(perm_view, perm_add, perm_change, perm_del)

    user.save()
    return user


@pytest.mark.django_db
def test_resource_has_no_universal_field_values_by_default(api_client, resource_in_unit):
    response = api_client.get(reverse('resource-detail',kwargs={'pk': resource_in_unit.pk}))
    data = response.data['universal_field']
    assert isinstance(data, list) == True
    assert len(data) == 0

@pytest.mark.django_db
def test_add_universal_field_to_resource(api_client, resource_in_unit, universal_form_field_type, user_with_permissions):
    api_client.force_authenticate(user=user_with_permissions)
    field_details = make_universal_field_data(
        resource=resource_in_unit,
        field_type=universal_form_field_type.type,
        identifier='FIRST'
        )

    # a new universal field was added to resource
    response = api_client.post(list_universal_field_url(), data=field_details)
    assert response.status_code == 201
 
@pytest.mark.django_db
def test_patch_universal_field_values(api_client,resource_universal_field_no_options, user_with_permissions):
    api_client.force_authenticate(user=user_with_permissions)
    response = api_client.get(get_detail_universal_field_url(resource_universal_field_no_options))
    original_response_data = response.data
    updated_field_values = {
        'description': {
            'fi': 'updated fi desc',
        },
        'label': {
            'sv': 'updated sv label'
        }
    }
    # updated description.fi and label.sv values,
    response = api_client.patch(get_detail_universal_field_url(resource_universal_field_no_options), data=updated_field_values)
    assert response.status_code == 200
    updated_response_data = response.data

    # these values for these keys should not have changed.
    check_keys_and_values_unchanged(
        validate_keys=['id','field_type','resource','name','options'],
        initial_data=original_response_data,
        updated_data=updated_response_data
        )

    # only the 'fi' value has changed,
    check_certain_lang_value_changed(
        initial_data=original_response_data['description'],
        updated_data=updated_response_data['description'],
        unchanged_keys=['en','sv'],
        changed_keys=['fi']
        )

    # only the 'sv' value has changed.
    check_certain_lang_value_changed(
        initial_data=original_response_data['label'],
        updated_data=updated_response_data['label'],
        unchanged_keys=['en','fi'],
        changed_keys=['sv']
        )
    

@pytest.mark.django_db
def test_add_options_to_resource_universal_field(api_client, resource_universal_field_no_options, user_with_permissions, make_form_option_data):
    api_client.force_authenticate(user=user_with_permissions)
    universal_field = resource_universal_field_no_options
    response = api_client.get(get_detail_universal_field_url(resource_universal_field_no_options))
    option_ids = ['FIRST', 'SECOND', 'THIRD']
    # universal field has no options
    assert response.status_code == 200
    assert len(response.data['options']) == 0
    
    # add first option to field
    first_option = make_form_option_data(universal_field, option_ids[0], 1)
    response = api_client.post(list_universal_form_option_url(), data=first_option)
    assert response.status_code == 201

    # universal field has 1 option
    response = api_client.get(get_detail_universal_field_url(resource_universal_field_no_options))
    assert response.status_code == 200
    assert len(response.data['options']) == 1

    # add second option to field
    second_option = make_form_option_data(universal_field, option_ids[1], 0)
    response = api_client.post(list_universal_form_option_url(), data=second_option)
    assert response.status_code == 201

    # universal field has 2 options
    response = api_client.get(get_detail_universal_field_url(resource_universal_field_no_options))
    assert response.status_code == 200
    assert len(response.data['options']) == 2

    # add third option to field
    third_option = make_form_option_data(universal_field, option_ids[2])
    response = api_client.post(list_universal_form_option_url(), data=third_option)
    assert response.status_code == 201

    # universal field has 3 options
    response = api_client.get(get_detail_universal_field_url(resource_universal_field_no_options))
    assert response.status_code == 200
    assert len(response.data['options']) == 3

    # test that each option belonging to the universal field is correct
    for index, value in enumerate(response.data['options']):
        assert option_ids[index] in value['text']['fi']
        assert option_ids[index] in value['text']['en']
        assert option_ids[index] in value['text']['sv']
    
    

@pytest.mark.django_db
def test_remove_options_from_universal_field(api_client, user_with_permissions, resource_universal_field_with_options):
    api_client.force_authenticate(user=user_with_permissions)
    response = api_client.get(get_detail_universal_field_url(resource_universal_field_with_options))
    data = response.data
    original_option_values = [{'id': x['id'], 'text': x['text']} for x in data['options']]

    # universal field has 4 options
    assert len(data['options']) == 4
    # each option has the correct initial values.
    for index, value in enumerate(data['options']):
        assert value['id'] == original_option_values[index]['id']
        assert value['text'] == original_option_values[index]['text']

    # delete the second option
    response = api_client.delete(reverse('resourceuniversalformoption-detail',kwargs={'pk': original_option_values[1]['id']}))
    assert response.status_code == 204
    original_option_values.pop(1)

    # universal field has 3(first,third and fourth) options
    response = api_client.get(get_detail_universal_field_url(resource_universal_field_with_options))
    data = response.data
    assert len(data['options']) == 3
    for index, value in enumerate(data['options']):
        assert value['id'] == original_option_values[index]['id']
        assert value['text'] == original_option_values[index]['text']

    # delete the last option
    response = api_client.delete(reverse('resourceuniversalformoption-detail',kwargs={'pk': original_option_values[2]['id']}))
    assert response.status_code == 204
    original_option_values.pop(2)

    # universal field has 2(first and third) options
    response = api_client.get(get_detail_universal_field_url(resource_universal_field_with_options))
    data = response.data
    assert len(data['options']) == 2
    for index, value in enumerate(data['options']):
        assert value['id'] == original_option_values[index]['id']
        assert value['text'] == original_option_values[index]['text']

    # delete the first option
    response = api_client.delete(reverse('resourceuniversalformoption-detail',kwargs={'pk': original_option_values[0]['id']}))
    assert response.status_code == 204
    original_option_values.pop(0)

    # universal field has 1(third) option
    response = api_client.get(get_detail_universal_field_url(resource_universal_field_with_options))
    data = response.data
    assert len(data['options']) == 1
    for index, value in enumerate(data['options']):
        assert value['id'] == original_option_values[index]['id']
        assert value['text'] == original_option_values[index]['text']