import pytest
from unittest.mock import MagicMock
from kulkunen.models import AccessControlGrant
from kulkunen.drivers.abloy import AbloyDriver

@pytest.fixture()
def abloy_driver_system_config(ac_grant):
    return {
        "api_url": "http://testurl/someapitest.fi",
        "header_username": "user",
        "header_password": "pass",
        "body_username": "user",
        "body_password": "pass",
        "organization_name": "test-organization",
    }

@pytest.fixture()
def abloy_driver(ac_system, abloy_driver_system_config):
    ac_system.driver_config = abloy_driver_system_config
    ac_system.save()
    return AbloyDriver(ac_system)

@pytest.fixture()
def abloy_grant_resource_config(ac_grant):
    return {
        "access_point_group_name": "test-group-name"
    }

@pytest.fixture()
def abloy_grant(ac_grant, abloy_grant_resource_config):
    ac_grant.resource.driver_config = abloy_grant_resource_config
    ac_grant.resource.resource.access_code_type = ac_grant.resource.resource.ACCESS_CODE_TYPE_PIN4
    ac_grant.save()
    return ac_grant

@pytest.mark.parametrize('grant_status', (
    AccessControlGrant.REQUESTED,
    AccessControlGrant.INSTALLED,
    AccessControlGrant.CANCELLED,
    AccessControlGrant.REMOVING,
    AccessControlGrant.REMOVED
))
@pytest.mark.django_db
def test_install_grant_state_error(abloy_driver, abloy_grant, grant_status):
    '''raises assertion error when grant state is not installing'''
    abloy_grant.state = grant_status
    abloy_grant.save()
    with pytest.raises(AssertionError):
        abloy_driver.install_grant(abloy_grant)

@pytest.mark.django_db
def test_install_grant_success(abloy_driver, abloy_grant):
    '''calls correct functions and sets grant state installed'''
    abloy_grant.state = AccessControlGrant.INSTALLING
    abloy_grant.save()
    abloy_grant.send_notify_email = MagicMock()

    abloy_driver.handle_api_get_person = MagicMock()
    abloy_driver.get_role_validity_times = MagicMock()
    abloy_driver.handle_api_post = MagicMock()

    abloy_driver.install_grant(abloy_grant)

    abloy_driver.handle_api_get_person.assert_called()
    abloy_driver.get_role_validity_times.assert_called()
    abloy_driver.handle_api_post.assert_called()
    assert abloy_grant.state == abloy_grant.INSTALLED
    abloy_grant.send_notify_email.assert_called()


@pytest.mark.django_db
def test_install_grant_fail_api_get_person(abloy_driver, abloy_grant):
    '''calls correct functions'''
    abloy_grant.state = AccessControlGrant.INSTALLING
    abloy_grant.save()
    abloy_grant.reset_reservation_access_code = MagicMock()
    abloy_driver.handle_api_get_person = MagicMock(side_effect=Exception("error"))

    abloy_driver.install_grant(abloy_grant)

    abloy_driver.handle_api_get_person.assert_called()
    abloy_grant.reset_reservation_access_code.assert_called()


@pytest.mark.django_db
def test_install_grant_fail_handle_api_post(abloy_driver, abloy_grant):
    '''calls correct functions'''
    abloy_grant.state = AccessControlGrant.INSTALLING
    abloy_grant.save()
    abloy_grant.reset_reservation_access_code = MagicMock()
    abloy_driver.handle_api_get_person = MagicMock()
    abloy_driver.handle_api_post = MagicMock(side_effect=Exception("error"))

    abloy_driver.install_grant(abloy_grant)

    abloy_driver.handle_api_get_person.assert_called()
    abloy_driver.handle_api_post.assert_called()
    abloy_grant.reset_reservation_access_code.assert_called()
