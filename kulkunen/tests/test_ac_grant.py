import pytest
from unittest.mock import MagicMock

@pytest.mark.django_db
def test_notify_access_code(ac_grant):
    reservation = ac_grant.reservation
    reservation.send_access_code_created_mail = MagicMock()
    test_access_code= "1234"
    ac_grant.access_code = test_access_code
    ac_grant.save()
    ac_grant.notify_access_code()
    reservation.refresh_from_db()
    assert reservation.access_code == test_access_code
    reservation.send_access_code_created_mail.assert_called()

@pytest.mark.django_db
def test_save_access_code_to_reservation(ac_grant):
    test_access_code= "1234"
    ac_grant.access_code = test_access_code
    ac_grant.save()
    ac_grant.save_access_code_to_reservation()
    ac_grant.refresh_from_db()
    assert ac_grant.reservation.access_code == test_access_code

@pytest.mark.django_db
def test_reset_reservation_access_code(ac_grant):
    test_access_code= "1234"
    ac_grant.reservation.access_code = test_access_code
    ac_grant.save()
    ac_grant.reset_reservation_access_code()
    ac_grant.refresh_from_db()
    assert ac_grant.reservation.access_code == None

@pytest.mark.django_db
def test_send_notify_email(ac_grant):
    '''mail is sent when reservation access code is not None'''
    test_access_code= "1234"
    reservation = ac_grant.reservation
    reservation.access_code = test_access_code
    reservation.send_access_code_created_mail = MagicMock()
    ac_grant.send_notify_email()
    reservation.send_access_code_created_mail.assert_called()

@pytest.mark.django_db
def test_send_notify_email_access_code_none(ac_grant):
    '''mail is not sent when reservation access code is None'''
    reservation = ac_grant.reservation
    reservation.access_code = None
    reservation.send_access_code_created_mail = MagicMock()
    ac_grant.send_notify_email()
    reservation.send_access_code_created_mail.assert_not_called()
