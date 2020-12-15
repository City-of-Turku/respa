import pytest
from datetime import timezone, datetime
from respa_o365.reservation_sync_item import ReservationSyncItem
from respa_o365.reservation_sync_operations import ChangeType


class ReservationRepositoryContract:
    """Helper class to test reservation repositories"""
    def test__get_item__returns_none__when_id_is_unknown(self, a_repo):
        item = a_repo.get_item(5)
        assert item is None

    def test__get_item__returns_previously_stored_item(self, a_repo):
        # Arrange
        original_item = ReservationSyncItem()
        original_item.begin = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
        original_item.end = datetime(2020, 1, 1, 13, 0, tzinfo=timezone.utc)
        original_item.reserver_name = "Pekka"
        original_item.reserver_phone_number = "+123124124"
        original_item.reserver_email_address = "abba@silli.fi"
        item_id, change_key = a_repo.create_item(original_item)
        # Act
        item = a_repo.get_item(item_id)
        # Assert
        assert original_item.reserver_name == item.reserver_name
        assert original_item.reserver_email_address == item.reserver_email_address
        assert original_item.reserver_phone_number == item.reserver_phone_number
        assert original_item.begin == item.begin
        assert original_item.end == item.end

    def test__get_changed_items__returns_empty_dict__when_there_are_no_changes_since_last_call(self, a_repo, a_item):
        item_id, change_key = a_repo.create_item(a_item)
        _, memento = a_repo.get_changes()
        changes, _ = a_repo.get_changes(memento)
        assert len(changes) == 0

    def test__get_changed_items__returns_empty_set__when_there_are_no_items(self, a_repo):
        changes, memento = a_repo.get_changes()
        assert len(changes) == 0

    def test__get_changed_items__returns_created__when_item_is_just_created(self, a_repo, a_item):
        item_id, change_key = a_repo.create_item(a_item)
        changes, memento = a_repo.get_changes()
        change_type, _ = changes[item_id]
        assert change_type == ChangeType.CREATED

    def test__get_changes_by_id__returns_no_change__when_reservations_has_not_changed(self, a_repo):
        item = ReservationSyncItem()
        item_id, change_key = a_repo.create_item(item)
        changes, memento = a_repo.get_changes()
        changes, memento = a_repo.get_changes_by_id([item_id], memento)
        change_type, _ = changes[item_id]
        assert change_type == ChangeType.NO_CHANGE

    @pytest.fixture()
    def a_repo(self):
        raise NotImplementedError("Implement in subclasses")

    @pytest.fixture()
    def a_item(self):
        item = ReservationSyncItem()
        return item
