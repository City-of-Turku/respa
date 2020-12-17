import uuid
import pytest

from respa_o365.id_mapper import IdMapper
from respa_o365.reservation_sync import SyncItemRepository, ReservationSync
from respa_o365.reservation_sync_operations import ChangeType


def test_sync_copies_element_from_first_source_to_second():
    # Arrange
    source1 = MemoryRepository()
    source2 = MemoryRepository()
    source1.create_item("blaah")
    sync = ReservationSync(respa=source1, remote=source2)
    # Act
    sync.sync_all()
    # Assert
    assert len(source2.get_items()) == 1
    assert list(source2.get_items())[0][1] == "blaah"


def test_sync_copies_element_from_second_source_to_first():
    # Arrange
    source1 = MemoryRepository()
    source2 = MemoryRepository()
    source2.create_item("blaah")
    sync = ReservationSync(respa=source1, remote=source2)
    # Act
    sync.sync_all()
    # Assert
    assert len(source1.get_items()) == 1
    assert list(source1.get_items())[0][1] == "blaah"


def test_sync_copies_changes_from_second_source():
    # Arrange
    source1 = MemoryRepository()
    source2 = MemoryRepository()
    id2, _ = source2.create_item("blaah")
    sync = ReservationSync(respa=source1, remote=source2)
    sync.sync_all()
    # Act
    source2.set_item(id2, "jee")
    sync.sync_all()
    # Assert
    assert len(source1.get_items()) == 1
    assert list(source1.get_items())[0][1] == "jee"


def test_sync_copies_elements_to_both_sources():
    # Arrange
    source1 = MemoryRepository()
    source2 = MemoryRepository()
    source1.create_item("blaah1")
    source2.create_item("blaah2")
    sync = ReservationSync(respa=source1, remote=source2)
    # Act
    sync.sync_all()
    # Assert
    assert len(source1.get_items()) == 2
    assert len(source2.get_items()) == 2
    assert sorted(map(lambda v: v[1], source1.get_items())) == ["blaah1", "blaah2"]
    assert sorted(map(lambda v: v[1], source2.get_items())) == ["blaah1", "blaah2"]


def test_sync_copies_changes_between_both_sources():
    # Arrange
    source1 = MemoryRepository()
    source2 = MemoryRepository()
    id1, _ = source1.create_item("blaah1a")
    id2, _ = source2.create_item("blaah2a")
    sync = ReservationSync(respa=source1, remote=source2)
    sync.sync_all()
    # Act
    source1.set_item(id1, "blaah1b")
    source2.set_item(id2, "blaah2b")
    sync.sync_all()
    # Assert
    assert len(source1.get_items()) == 2, str(source1.get_items())
    assert len(source2.get_items()) == 2, str(source2.get_items())
    assert sorted(map(lambda v: v[1], source1.get_items())) == ["blaah1b", "blaah2b"]


def test_sync_removes_item_when_removed_from_first_source():
    # Arrange
    source1 = MemoryRepository()
    source2 = MemoryRepository()
    id1, _ = source1.create_item("blaah1")
    source2.create_item("blaah2")
    sync = ReservationSync(respa=source1, remote=source2)
    sync.sync_all()
    # Act
    source1.remove_item(id1)
    sync.sync_all()
    # Assert
    assert len(source1.get_items()) == 1, str(source1.get_items())
    assert len(source2.get_items()) == 1, str(source2.get_items())
    assert sorted(map(lambda v: v[1], source1.get_items())) == ["blaah2"]


def test_sync_overrides_changes_from_second_source_when_changed():
    # First source is Respa and when synchronising Reservations status in Respa is used when
    # changed conflict.
    # Arrange
    source1 = MemoryRepository()
    source2 = MemoryRepository()
    id1a, _ = source1.create_item("blaah1")
    sync = ReservationSync(respa=source1, remote=source2)
    sync.sync_all()
    id1b = list(source2.get_items())[0][0]
    # Act
    source1.set_item(id1a, "blaah1a")
    source2.set_item(id1b, "blaah2b")
    sync.sync_all()
    # Assert
    assert len(source1.get_items()) == 1, str(source1.get_items())
    assert len(source2.get_items()) == 1, str(source2.get_items())
    assert sorted(map(lambda v: v[1], source2.get_items())) == ["blaah1a"]

def test_sync_ignores_item_in_respa__when_change_key_matches():
    # Arrange
    source1 = MemoryRepository()
    source2 = MemoryRepository()
    id1, change_key1 = source1.create_item("blaah1")
    id2, change_key2 = source2.create_item("blaah2")
    id_mapper = IdMapper({id1: id2})
    sync = ReservationSync(respa=source1, remote=source2, respa_change_keys={id1: change_key1}, remote_change_keys={id2: change_key2}, id_mapper=id_mapper)
    # Act
    sync.sync_all()
    # Assert
    assert len(source1.get_items()) == 1, str(source1.get_items())
    assert len(source2.get_items()) == 1, str(source2.get_items())
    assert sorted(map(lambda v: v[1], source1.get_items())) == ["blaah1"]
    assert sorted(map(lambda v: v[1], source2.get_items())) == ["blaah2"]

def test__respa_change_keys__returns_change_keys():
    # Arrange
    source1, source2 = MemoryRepository(), MemoryRepository()
    id, change_key = source1.create_item("blaah1")
    sync = ReservationSync(respa=source1, remote=source2)
    # Act
    sync.sync_all()
    # Assert
    assert sync.respa_change_keys() == {id: change_key}

def test__remote_change_keys__returns_change_keys():
    # Arrange
    source1, source2 = MemoryRepository(), MemoryRepository()
    id, change_key = source2.create_item("blaah1")
    sync = ReservationSync(respa=source1, remote=source2)
    # Act
    sync.sync_all()
    # Assert
    assert sync.remote_change_keys() == {id: change_key}

class MemoryRepository(SyncItemRepository):
    def __init__(self):
        self.__items = {}
        self.__changes = []

    def create_item(self, item):
        item_id = str(uuid.uuid4())
        self.set_item(item_id, item)
        self.__changes.append((item_id, ChangeType.CREATED))
        return item_id, hash(item)

    def set_item(self, item_id, item):
        self.__items[item_id] = item
        self.__changes.append((item_id, ChangeType.UPDATED))
        return hash(item)

    def get_item(self, item_id):
        return self.__items.get(item_id, None)

    def remove_item(self, item_id):
        self.__items.pop(item_id, None)
        self.__changes.append((item_id, ChangeType.DELETED))

    def get_items(self):
        return self.__items.items()

    def get_changes(self, memento=None):
        start = 0
        try:
            start = int(memento)
        except ValueError:
            pass
        except TypeError:
            pass
        end = len(self.__changes)
        result = {item_id: (state, hash(self.__items.get(item_id, None))) for item_id, state in self.__changes[start:end]}
        return result, str(end)

    def get_changes_by_ids(self, item_ids, memento=None):
        changes, _ = self.get_changes(memento)
        result = {i: changes.get(i, (ChangeType.NO_CHANGE, hash(self.__items.get(i, None)))) for i in item_ids if i in self.__items}
        return result, memento

