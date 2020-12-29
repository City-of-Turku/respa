
class IdMapper:
    """Maps ids of two system between each others. Keeps track of changes."""

    def __init__(self, initial={}):
        parent = self
        self._direct_dict = {}
        self._reverse_dict = {}
        for k, v in initial.items():
            self._direct_dict[k] = v
            self._reverse_dict[v] = k
        self._added = {}
        self._changed = {}
        self._removed = {}


        class Reverse:
            reverse = parent

            def __setitem__(self, key, value):
                parent[value] = key

            def __getitem__(self, key):
                return parent._reverse_dict[key]

            def __delitem__(self, key):
                parent.del_key_value(parent.reverse_get(key), key)

            def get(self, key, *args):
                return parent._reverse_dict.get(key, *args)

        self.reverse = Reverse()

    def __setitem__(self, key, value):
        old_value = self._direct_dict.get(key, None)
        if old_value == value:
            return

        was_present = old_value is not None
        self._direct_dict[key] = value
        self._reverse_dict[value] = key
        removed_value = self._removed.pop(key, None)
        if removed_value == value:
            return
        was_not_added = key not in self._added
        was_removed = removed_value is not None
        is_changed = was_not_added and (was_present or was_removed)
        if is_changed:
            self._changed[key] = value
        else:
            self._added[key] = value

    def __delitem__(self, key):
        value = self._direct_dict[key]
        self.del_key_value(key, value)

    def get(self, key, *args):
        return self._direct_dict.get(key, *args)

    def reverse_get(self, key):
        return self._reverse_dict[key]

    def del_key_value(self, key, value):
        del self._direct_dict[key]
        del self._reverse_dict[value]
        if key not in self._added:
            self._removed[key] = value
        self._added.pop(key, None)
        self._changed.pop(key, None)

    def __getitem__(self, key):
        return self._direct_dict[key]

    def additions(self):
        for k, v in self._added.items():
            yield k, v

    def removals(self):
        for k, v in self._removed.items():
            yield k, v

    def changes(self):
        for k, v in self._changed.items():
            yield k, v

