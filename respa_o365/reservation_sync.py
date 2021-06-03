import logging

from respa_o365.id_mapper import IdMapper
from respa_o365.sync_operations import ChangeType, SyncActionVisitor, TargetSystem, \
    SyncOperations, reservationSyncActions


class SyncItemRepository:
    def create_item(self, item):
        """
        Creates given item. Returns id and change key.
        Id can be used to refer item (set,get,remove_item commands).
        Change key can be used to check, if item has actually changed.
        For example setting item to certain content will change the item and
        it will be returned using get_changes-methods. However item is not actually
        new to the caller who has set its content. This can be seen by comparing
        the change keys.
        """
        pass

    def set_item(self, item_id, item):
        """Sets the content of the given id. Returns change key."""
        pass

    def get_item(self, item_id):
        """Returns the content of the image."""
        pass

    def remove_item(self, item_id):
        """Removes the item."""
        pass

    def get_changes(self, memento):
        """
        Method returns changes after previous method call referenced by memento and new memento.
        Or all changes since starts if memento is missing.
        Changes are dictionary that map item id to (ChangeType, string) -tuplet where string is the change key.

        :param memento: String returned by any previous call or null.
        :return: (dict, memento)-tuplet where dict maps item id to (ChangeType, string) -tuplet for every existing id.
        """
        pass

    def get_changes_by_ids(self, item_ids, memento):
        """
        Returns changes of given ids after previous method call. Memento is interchangeable with get_changes-method.
        Change status is returned even if there has not been change in certain item. Change is not present if
        item does not exist.

        :param item_ids: Array of item ids that are of the interest
        :param memento: String returned by any previous call or null.
        :return: (dict, memento)-tuplet where dict maps item id to (ChangeType, string) -tuplet for every existing id.
        """
        pass


class ChangeKeyWrapper(SyncItemRepository):
    """
    Wraps SyncItemRepository and alters item satuses based on change key information.
    Basically item that has been created or update through this wrapper is not present
    in get_changes -method calls.
    """
    def __init__(self, repo, change_keys={}):
        self.__repo = repo
        self.__last_hash_value = change_keys.copy()

    def create_item(self, item):
        item_id, changeKey = self.__repo.create_item(item)
        self.seen(item_id, changeKey)
        return item_id, changeKey

    def set_item(self, item_id, item):
        change_key = self.__repo.set_item(item_id, item)
        self.seen(item_id, change_key)
        return change_key

    def get_item(self, item_id):
        return self.__repo.get_item(item_id)

    def remove_item(self, item_id):
        self.__last_hash_value.pop(item_id, None)
        self.__repo.remove_item(item_id)

    def get_changes(self, *args):
        result, memento = self.__repo.get_changes(*args)
        return self.filter_seen(result), memento

    def get_changes_by_ids(self, *args):
        result, memento = self.__repo.get_changes_by_ids(*args)
        return self.filter_seen(result), memento

    def seen(self, item_id, change_key):
        last_hash = self.__last_hash_value.get(item_id, 0)
        self.__last_hash_value[item_id] = change_key
        return last_hash == change_key

    def filter_seen(self, changes_with_change_keys):
        filtered = {}
        for item_id, (change_type, change_key) in changes_with_change_keys.items():
            if self.seen(item_id, change_key) and change_type != ChangeType.DELETED:
                filtered[item_id] = ChangeType.NO_CHANGE
            else:
                filtered[item_id] = change_type
        return filtered

    def change_keys(self):
        return self.__last_hash_value.copy()

class ReservationSync:

    def __init__(self, respa, remote, respa_memento=None, remote_memento=None, id_mapper=None, respa_change_keys={}, remote_change_keys={}, 
            sync_actions=None):
        self.__respa = ChangeKeyWrapper(respa, respa_change_keys)
        self.__remote = ChangeKeyWrapper(remote, remote_change_keys)
        self.__id_map = IdMapper() if not id_mapper else id_mapper
        self.__respa_memento = respa_memento
        self.__remote_memento = remote_memento
        if sync_actions is not None:
            self._sync_actions = sync_actions
        else:
            self._sync_actions = reservationSyncActions


    def sync(self, respa_statuses, remote_statuses):
        respa_ids = [i for i in respa_statuses.keys()]
        remote_ids = [i for i in remote_statuses.keys()]
        respa_statuses, _ = self.__respa.get_changes_by_ids(respa_ids, self.__respa_memento)
        remote_statuses, _ = self.__remote.get_changes_by_ids(remote_ids, self.__remote_memento)
        self._sync(respa_statuses, remote_statuses)

    def _sync(self, respa_statuses, remote_statuses):
        def build_status_pair(respa_id, remote_id):
            respa_state = respa_statuses.get(respa_id, None)
            remote_state = remote_statuses.get(remote_id, None)
            respa_item = (respa_id, respa_state) if respa_id and respa_state else None
            remote_item = (remote_id, remote_state) if remote_id and remote_state else None
            return respa_item, remote_item

        def missing_ids(ids, other_ids, mapper):
            mapped_ids = [mapper.get(i, None) for i in ids]
            return [i for i in mapped_ids if i is not None and i not in other_ids]

        ids_missing_from_remote = missing_ids(respa_statuses.keys(), remote_statuses.keys(), self.__id_map)
        missing_changes_from_remote, _ = self.__remote.get_changes_by_ids(ids_missing_from_remote, self.__remote_memento)
        remote_statuses.update(missing_changes_from_remote)

        ids_missing_from_respa = missing_ids(remote_statuses.keys(), respa_statuses.keys(), self.__id_map.reverse)
        missing_changes_from_respa, _ = self.__respa.get_changes_by_ids(ids_missing_from_respa, self.__respa_memento)
        respa_statuses.update(missing_changes_from_respa)

        changes = set()
        for respa_id in respa_statuses:
            remote_id = self.__id_map.get(respa_id, None)
            changes.add(build_status_pair(respa_id, remote_id))

        for remote_id in remote_statuses:
            respa_id = self.__id_map.reverse.get(remote_id, None)
            changes.add(build_status_pair(respa_id, remote_id))

        
        ops = SyncOperations(changes, self._sync_actions).get_sync_operations()

        visitor = OpVisitor(self.__respa, self.__remote, self.__id_map)
        for op in ops:
            op.accept(visitor)

    def sync_all(self):
        respa_statuses, memento_respa = self.__respa.get_changes(self.__respa_memento)
        remote_statuses, memento_remote = self.__remote.get_changes(self.__remote_memento)
        self._sync(respa_statuses, remote_statuses)
        self.__respa_memento = memento_respa
        self.__remote_memento = memento_remote

    def respa_memento(self):
        return self.__respa_memento

    def remote_memento(self):
        return self.__remote_memento

    def respa_change_keys(self):
        return self.__respa.change_keys()

    def remote_change_keys(self):
        return self.__remote.change_keys()

class OpVisitor(SyncActionVisitor):

    def __init__(self, respa, remote, id_map):
        self.__respa = respa
        self.__remote = remote
        self.__id_map = id_map

    def create_event(self, target, source_id):
        source_repo, target_repo = self.get_target_and_source(target)
        item = source_repo.get_item(source_id)
        target_id, _ = target_repo.create_item(item)
        if target == TargetSystem.RESPA:
            self.add_mapping(target_id, source_id)
        else:
            self.add_mapping(source_id, target_id)

    def delete_event(self, target, target_id):
        source_repo, target_repo = self.get_target_and_source(target)
        target_repo.remove_item(target_id)
        if target == TargetSystem.RESPA:
            del self.__id_map[target_id]
        else:
            del self.__id_map.reverse[target_id]

    def update_event(self, target, source_id, target_id):
        source_repo, target_repo = self.get_target_and_source(target)
        item = source_repo.get_item(source_id)
        target_repo.set_item(target_id, item)

    def get_target_and_source(self, target):
        if target == TargetSystem.RESPA:
            return self.__remote, self.__respa
        return self.__respa, self.__remote

    def remove_mapping(self, respa_id, remote_id):
        del self.__id_map[respa_id]

    def add_mapping(self, respa_id, remote_id):
        self.__id_map[respa_id] = remote_id
