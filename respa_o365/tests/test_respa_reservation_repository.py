from datetime import timezone, datetime

import pytest
from resources.models import Reservation
from respa_o365.reservation_sync_item import ReservationSyncItem
from respa_o365.reservation_sync_operations import ChangeType
from respa_o365.respa_reservation_repository import RespaReservations


@pytest.mark.django_db
def test_get_changed_items__returns_changes__when_no_memento_is_given(resource_in_unit, reservation):
    repo = RespaReservations(resource_in_unit)
    changes, memento = repo.get_changed_items()
    change_type, _ = changes[reservation.id]
    assert change_type == ChangeType.CREATED

@pytest.mark.django_db
def test_get_changed_items__returns_empty_dict__when_there_are_no_changes_since_last_call(resource_in_unit, reservation):
    repo = RespaReservations(resource_in_unit)
    _, memento = repo.get_changed_items()
    changes, _ = repo.get_changed_items(memento)
    assert len(changes) == 0

@pytest.mark.django_db
def test_get_changes_by_id__returns_no_change__when_reservations_has_not_changed(resource_in_unit, reservation):
    repo = RespaReservations(resource_in_unit)
    changes, memento = repo.get_changed_items()

    changes, memento = repo.get_changes_by_id([reservation.id], memento)
    change_type, _ = changes[reservation.id]
    assert change_type == ChangeType.NO_CHANGE


@pytest.mark.django_db
def test_get_changes_by_id__returns_deleted__when_reservation_is_cancelled(resource_in_unit, reservation):
    repo = RespaReservations(resource_in_unit)
    _, memento = repo.get_changed_items()

    reservation.state = Reservation.CANCELLED
    reservation.save()

    changes, memento = repo.get_changes_by_id([reservation.id], memento)
    change_type, _ = changes[reservation.id]
    assert change_type == ChangeType.DELETED

@pytest.mark.django_db
def test_get_changes_by_id__returns_updated__when_reservation_is_updated(resource_in_unit, reservation):
    repo = RespaReservations(resource_in_unit)
    _, memento = repo.get_changed_items()
    reservation.reserver_name = "Some Body Else"
    reservation.save()

    changes, memento = repo.get_changes_by_id([reservation.id], memento)
    change_type, _ = changes[reservation.id]
    assert change_type == ChangeType.UPDATED

@pytest.mark.django_db
def test_get_changes__returns_updated__when_reservation_is_updated(resource_in_unit, reservation):
    repo = RespaReservations(resource_in_unit)
    _, memento = repo.get_changed_items()
    reservation.reserver_name = "Some Body Else"
    reservation.save()

    changes, memento = repo.get_changed_items(memento)

    assert changes[reservation.id] is not None, "Change was not available."
    change_type, _ = changes[reservation.id]
    assert change_type == ChangeType.UPDATED

@pytest.mark.django_db
def test_get_changes__returns_deleted__when_reservation_is_cancelled(resource_in_unit, reservation):
    repo = RespaReservations(resource_in_unit)
    _, memento = repo.get_changed_items()
    reservation.state = Reservation.CANCELLED
    reservation.save()

    changes, memento = repo.get_changed_items(memento)

    assert changes[reservation.id] is not None, "Change was not available."
    change_type, _ = changes[reservation.id]
    assert change_type == ChangeType.DELETED

@pytest.mark.django_db
def test_get_item__returns_item__when_id_exists(resource_in_unit, reservation):
    repo = RespaReservations(resource_in_unit)
    res = repo.get_item(reservation.id)
    assert res.begin == reservation.begin
    assert res.end == reservation.end
    assert res.reserver_name == reservation.reserver_name
    assert res.reserver_phone_number == reservation.reserver_phone_number
    assert res.reserver_email_address == reservation.reserver_email_address

@pytest.mark.django_db
def test_get_item__returns_none__when_id_is_unknown(resource_in_unit):
    repo = RespaReservations(resource_in_unit)
    res = repo.get_item(5)
    assert res == None

@pytest.mark.django_db
def test_get_item_returns_item_None2(resource_in_unit):
    repo = RespaReservations(resource_in_unit)
    original_item = ReservationSyncItem()
    original_item.begin = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
    original_item.end = datetime(2020, 1, 1, 13, 0, tzinfo=timezone.utc)
    item_id, change_key = repo.create_item(original_item)
    item = repo.get_item(item_id)

    assert original_item.reserver_name == item.reserver_name
    assert original_item.reserver_email_address == item.reserver_email_address
    assert original_item.reserver_phone_number == item.reserver_phone_number
    assert original_item.begin == item.begin
    assert original_item.end == item.end

@pytest.mark.django_db
def test_get_item_returns_item_None3(resource_in_unit):
    repo = RespaReservations(resource_in_unit)
    original_item1 = ReservationSyncItem()
    original_item1.begin = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
    original_item1.end = datetime(2020, 1, 1, 13, 0, tzinfo=timezone.utc)
    item_id, change_key1 = repo.create_item(original_item1)
    original_item = ReservationSyncItem()
    original_item.begin = datetime(2019, 1, 1, 12, 0, tzinfo=timezone.utc)
    original_item.end = datetime(2019, 1, 1, 13, 0, tzinfo=timezone.utc)
    original_item.reserver_name = "Pekka"
    original_item.reserver_phone_number = "+123124124"
    original_item.reserver_email_address = "abba@silli.fi"
    item_id, change_key = repo.create_item(original_item1)
    change_key2 = repo.set_item(item_id, original_item)
    item = repo.get_item(item_id)
    assert original_item.reserver_name == item.reserver_name
    assert original_item.reserver_email_address == item.reserver_email_address
    assert original_item.reserver_phone_number == item.reserver_phone_number
    assert original_item.begin == item.begin
    assert original_item.end == item.end


