# -*- coding: utf-8 -*-
import pytest
import datetime 
from django.utils import timezone
from django.urls import reverse

LIST_URL = reverse('announcements-list')


@pytest.mark.django_db
def test_maintenance_message(client, maintenance_message):
    response = client.get(LIST_URL, HTTP_ACCEPT='text/html')
    assert response.status_code == 200
    results = response.data['results']
    assert 0 < len(results) < 2
    messages = next(iter(results)).get('message', None)
    assert messages is not None
    for lang, message in messages.items():
        assert message == getattr(maintenance_message, 'message_%s' % lang)
    maintenance_message.start = timezone.now() + datetime.timedelta(hours=5)
    maintenance_message.end = timezone.now() + datetime.timedelta(hours=6)
    maintenance_message.save()
    response = client.get(LIST_URL, HTTP_ACCEPT='text/html')
    assert response.status_code == 200
    results = response.data['results']
    assert len(results) == 0

