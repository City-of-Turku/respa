
from respa_o365.sync_operations import ChangeType, SyncOperations, reservationSyncActions


def test_reservation_sync():

    # Set up the expectations for every state combination
    XX = "Not possible situation. Skipped."
    NN = ""
    CR = "Create 'a' to RESPA."
    CO = "Create '1' to REMOTE."
    DR = "Delete '1' from RESPA."
    DO = "Delete 'a' from REMOTE."
    UR = "Update '1' in RESPA. Source id 'a'."
    UO = "Update 'a' in REMOTE. Source id '1'."
    RM = "Remove mapping '1' and 'a'."
    expectations = [
    # Outlook/Other:
    # t   e
    # s   g
    # i   n   d   d   d
    # x   a   e   e   e
    # e   h   t   t   t
    #     c   a   a   e
    # t       e   d   l
    # o   o   r   p   e
    # N   N   C   U   D    # Respa:
    [XX, CR, CR, CR, NN],  # Not exists
    [CO, NN, UR, UR, DR],  # No change
    [CO, UO, UO, UO, CO],  # Created
    [CO, UO, UO, UO, CO],  # Updated
    [NN, DO, DO, DO, RM],  # Deleted
    ]

    statuses = [
        None,
        ChangeType.NO_CHANGE,
        ChangeType.CREATED,
        ChangeType.UPDATED,
        ChangeType.DELETED,
    ]
    print()
    print("{:9} {:9}".format("Respa", "Outlook"))
    failures = ""
    for i, respa_state in enumerate(statuses):
        for j, outlook_state in enumerate(statuses):
            expectation = expectations[i][j]
            if XX == expectation:
                continue

            # Arrange
            item1 = ("1", respa_state) if respa_state else None
            item2 = ("a", outlook_state) if outlook_state else None
            state1 = respa_state.name if respa_state else "None"
            state2 = outlook_state.name if outlook_state else "None"
            # Act
            ops = SyncOperations([(item1, item2)], reservationSyncActions).get_sync_operations()
            # Assert
            try:
                w = OperationWriter()
                for op in ops:
                    op.accept(w)
                actual = w.text()
                assert expectation == actual
                print("{:9} vs {:>9}      OK.".format(state1, state2))
            except AssertionError as e:
                print("{:9} vs {:>9}  FAILED! Expected {} Got {}".format(state1, state2, expectation, actual))
                if len(failures) > 0:
                    failures += "\n"
                failures += " - {} ( {} vs {} expected {} )".format(e, state1, state2, expectation)
    if len(failures):
        raise AssertionError("Errors were:\n" + failures)


class OperationWriter:
    def __init__(self):
        self.__text = ""

    def create_event(self, target, source_id):
        self._append("Create '{}' to {}.".format(source_id, target.name))

    def delete_event(self, target, target_id):
        self._append("Delete '{}' from {}.".format(target_id, target.name))
        pass

    def update_event(self, target, source_id, target_id):
        self._append("Update '{}' in {}. Source id '{}'.".format(target_id, target.name, source_id))

    def remove_mapping(self, respa_id, remote_id):
        self._append("Remove mapping '{}' and '{}'.".format(respa_id, remote_id))

    def _append(self, text):
        if len(self.__text) > 0:
            self.__text += "\n"
        self.__text += text

    def text(self):
        return self.__text
