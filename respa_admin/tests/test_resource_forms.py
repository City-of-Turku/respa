import pytest
import datetime
from django.test import RequestFactory
from django.utils import translation
from django.urls import reverse
from freezegun import freeze_time

from resources.models import Resource
from ..forms import get_period_formset


NEW_RESOURCE_URL = reverse('respa_admin:new-resource')


@pytest.mark.django_db
def test_period_formset_with_minimal_valid_data(valid_resource_form_data):
    request = RequestFactory().post(NEW_RESOURCE_URL, data=valid_resource_form_data)
    period_formset_with_days = get_period_formset(request)
    assert period_formset_with_days.is_valid()


@pytest.mark.django_db
def test_period_formset_with_invalid_period_data(valid_resource_form_data):
    data = valid_resource_form_data
    data.pop('periods-0-start')
    with translation.override('fi'):
        request = RequestFactory().post(NEW_RESOURCE_URL, data=data)
        period_formset_with_days = get_period_formset(request)
    assert period_formset_with_days.is_valid() is False
    assert period_formset_with_days.errors == [{
        '__all__': ["Aseta 'start' ja 'end'"],
        'start': ['Tämä kenttä vaaditaan.'],
    }]


@pytest.mark.django_db
def test_period_formset_with_invalid_days_data(valid_resource_form_data):
    data = valid_resource_form_data
    data.pop('days-periods-0-0-weekday')
    with translation.override('fi'):
        request = RequestFactory().post(NEW_RESOURCE_URL, data=data)
        period_formset_with_days = get_period_formset(request)
    assert period_formset_with_days.is_valid() is False
    assert period_formset_with_days.errors == [
        {'__all__': ['Tämä kenttä vaaditaan.']}
    ]
    assert period_formset_with_days.forms[0].days.errors == [
        {'weekday': ['Tämä kenttä vaaditaan.']}
    ]


@pytest.mark.django_db
def test_create_resource_with_invalid_data_returns_errors(admin_client, empty_resource_form_data):
    data = empty_resource_form_data
    with translation.override('fi'):
        response = admin_client.post(NEW_RESOURCE_URL, data=data)

    assert response.context['form'].errors == {
        'access_code_type': ['Tämä kenttä vaaditaan.'],
        'authentication': ['Tämä kenttä vaaditaan.'],
        'equipment': ['Valitse oikea vaihtoehto.  ei ole vaihtoehtojen joukossa.'],
        'min_period': ['Tämä kenttä vaaditaan.'],
        'name_fi': ['Tämä kenttä vaaditaan.'],
        'purposes': ['Valitse oikea vaihtoehto.  ei ole vaihtoehtojen joukossa.'],
        'type': ['Tämä kenttä vaaditaan.'],
        'unit': ['Tämä kenttä vaaditaan.'],
        'price_type': ['Tämä kenttä vaaditaan.']
    }
    assert response.context['period_formset_with_days'].errors == [
        {'__all__': ['Tämä kenttä vaaditaan.', 'Aloitus- tai sulkemisaika puuttuu']}
    ]


@pytest.mark.django_db
def test_create_resource_with_invalid_reservation_feedback_url_data(admin_client, valid_resource_form_data):
    data = valid_resource_form_data.copy()
    data['reservation_feedback_url'] = 'bad-url'
    with translation.override('fi'):
        response = admin_client.post(NEW_RESOURCE_URL, data=data)
    assert response.context['form'].errors == {
        'reservation_feedback_url': ['Syötä oikea URL-osoite.'],
    }


@pytest.mark.django_db
def test_create_resource_with_invalid_external_reservation_url_data(admin_client, valid_resource_form_data):
    data = valid_resource_form_data.copy()
    data['external_reservation_url'] = 'not-an-url'
    with translation.override('fi'):
        response = admin_client.post(NEW_RESOURCE_URL, data=data)
    assert response.context['form'].errors == {
        'external_reservation_url': ['Syötä oikea URL-osoite.'],
    }


@pytest.mark.django_db
def test_resource_creation_with_valid_data(admin_client, valid_resource_form_data):
    assert Resource.objects.count() == 0  # No resources in the db
    response = admin_client.post(NEW_RESOURCE_URL, data=valid_resource_form_data, follow=True)
    assert response.status_code == 200
    assert response.context['form'].errors == {}
    assert Resource.objects.count() == 1  # One new resource in db
    new_resource = Resource.objects.first()
    assert new_resource.periods.count() == 1
    assert new_resource.periods.first().days.count() == 1
    assert new_resource.periods.first().days.first().weekday == 1


@freeze_time('2018-06-12')
@pytest.mark.django_db
def test_resource_creation_sets_opening_hours(admin_client, valid_resource_form_data):
    """
    valid_resource_form_data sets the opening hours starting from 2018-06-06 only for Tuesdays.
    Time is frozen to 2018-06-12 which is the first Tuesday after that to test opening hours.
    """
    data = valid_resource_form_data.copy()
    data['days-periods-0-0-closes'] = '14:00'
    admin_client.post(NEW_RESOURCE_URL, data=data, follow=True)
    new_resource = Resource.objects.first()
    opening_hours = new_resource.get_opening_hours()
    date = datetime.date.today()
    assert date in opening_hours
    closing_time = opening_hours[date][0]['closes']
    assert closing_time is not None, 'Closing time for today should be 14:00, instead it is None'
    assert closing_time.hour == 14
    assert closing_time.minute == 0


@pytest.mark.django_db
def test_resource_creation_with_empty_hours(admin_client, valid_resource_form_data):
    resource_count = Resource.objects.count()
    data = valid_resource_form_data.copy()
    data['days-periods-0-0-opens'] = ''
    data['days-periods-0-0-closes'] = ''
    data['days-periods-0-0-closed'] = ''
    response = admin_client.post(NEW_RESOURCE_URL, data=data, follow=True)
    assert response.status_code == 200
    assert Resource.objects.count() == resource_count, 'No new resource should be created with invalid data'


@pytest.mark.django_db
def test_resource_creation_with_empty_hours_on_closed_day(admin_client, valid_resource_form_data):
    resource_count = Resource.objects.count()
    data = valid_resource_form_data.copy()
    data['days-periods-0-0-opens'] = ''
    data['days-periods-0-0-closes'] = ''
    data['days-periods-0-0-closed'] = 'on'
    response = admin_client.post(NEW_RESOURCE_URL, data=data, follow=True)
    assert response.status_code == 200
    assert Resource.objects.count() == resource_count + 1, 'Closed day should allow empty hours'


@pytest.mark.django_db
def test_editing_resource_via_form_view(admin_client, valid_resource_form_data):
    assert Resource.objects.all().exists() is False
    data = valid_resource_form_data.copy()
    # Create a resource via the form view
    data.update({
        'name_sv': 'swedish name when created'
    })
    response = admin_client.post(NEW_RESOURCE_URL, data=data, follow=True)
    assert response.status_code == 200
    resource = Resource.objects.first()

    # Edit the resource
    data.update({
        'name_fi': 'Edited name',
        'name_sv': 'Updated swedish name'
    })
    response = admin_client.post(
        reverse('respa_admin:edit-resource', kwargs={'resource_id': resource.id}),
        data=data,
        follow=True
    )
    assert response.status_code == 200
    assert Resource.objects.count() == 1  # Still only 1 resource in db

    # Validate that the changes did happen
    edited_resource = Resource.objects.first()
    assert edited_resource.name_sv == 'Updated swedish name'
    assert resource.name_sv != edited_resource.name_sv
    assert edited_resource.name_fi == 'Edited name'
    assert resource.name_fi != edited_resource.name_fi


@pytest.mark.django_db
def test_editing_existing_resource_via_form_view(admin_client, resource_in_unit_form_data, resource_in_unit):
    url = reverse('respa_admin:edit-resource', kwargs={'resource_id': resource_in_unit.pk})
    assert Resource.objects.count() == 1
    form_data = resource_in_unit_form_data
    # delete equipment key, for some reason it causes validations errors when empty.
    del form_data['equipment']
    # add missing resource data.
    form_data.update({
        'periods-0-name': 'Kesäkausi',
        'periods-0-start': '2018-06-06',
        'periods-0-end': '2032-08-01',
        'days-periods-0-0-opens': '08:00',
        'days-periods-0-0-closes': '12:00',
        'days-periods-0-0-weekday': '1',
        'min_period': '01:00:00',
        'slot_size': '00:30:00',
        'price_type': 'hourly',
        'access_code_type': 'none',
    })
    # update name value
    form_data.update({
        'name_fi': 'updated name value',
    })
    response = admin_client.post(
        url,
        data=form_data,
        follow=True
    )
    assert response.status_code == 200
    assert Resource.objects.count() == 1  # Still only 1 resource in db
    edited_resource = Resource.objects.get(pk=resource_in_unit.pk)
    assert edited_resource.name_fi == 'updated name value'
