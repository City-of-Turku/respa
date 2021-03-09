
import pytest
from datetime import  timedelta
from resources.models import Reservation, ResourceType, Resource, Unit, TermsOfUse
from respa_o365.reservation_sync_item import ReservationSyncItem
from respa_o365.sync_operations import ChangeType
from respa_o365.respa_reservation_repository import RespaReservations
from respa_o365.reservation_repository_contract import ReservationRepositoryContract


@pytest.mark.django_db
class TestRespaReservationRepository(ReservationRepositoryContract):
    def test__get_changes_by_ids__returns_deleted__when_reservation_is_cancelled(self, a_repo, a_item):
        # Arrange
        item_id, _ = a_repo.create_item(a_item)
        reservation = Reservation.objects.filter(id=item_id).first()
        reservation.state = Reservation.CANCELLED
        reservation.save()
        # Act
        changes, _ = a_repo.get_changes_by_ids([reservation.id])
        # Assert
        change_type, _ = changes[reservation.id]
        assert change_type == ChangeType.DELETED

    def test__get_changes_by_ids__returns_updated__when_reservation_is_updated(self, a_repo, a_item):
        # Arrange
        item_id, _ = a_repo.create_item(a_item)
        reservation = Reservation.objects.filter(id=item_id).first()
        _, memento = a_repo.get_changes()
        reservation.reserver_name = "Some Body Else"
        reservation.save()
        # Act
        changes, memento = a_repo.get_changes_by_ids([reservation.id], memento)
        # Assert
        change_type, _ = changes[reservation.id]
        assert change_type == ChangeType.UPDATED

    def test__get_changes__returns_updated__when_reservation_is_updated(self, a_repo, a_item):
        # Arrange
        item_id, _ = a_repo.create_item(a_item)
        _, memento = a_repo.get_changes()
        reservation = Reservation.objects.filter(id=item_id).first()
        reservation.reserver_name = "Some Body Else"
        reservation.save()
        # Act
        changes, _ = a_repo.get_changes(memento)
        # Assert
        assert changes[reservation.id] is not None, "Change was not available."
        change_type, _ = changes[reservation.id]
        assert change_type == ChangeType.UPDATED

    def test__get_changes__returns_deleted__when_reservation_is_cancelled(self, a_repo, a_item):
        # Arrange
        item_id, _ = a_repo.create_item(a_item)
        _, memento = a_repo.get_changes()
        reservation = Reservation.objects.filter(id=item_id).first()
        reservation.state = Reservation.CANCELLED
        reservation.save()
        # Act
        changes, memento = a_repo.get_changes(memento)
        # Assert
        assert changes[reservation.id] is not None, "Change was not available."
        change_type, _ = changes[reservation.id]
        assert change_type == ChangeType.DELETED

    @pytest.fixture()
    def a_repo(self, a_resource):
        return RespaReservations(a_resource.id)

    @pytest.fixture
    def a_resource(self, a_resource_type, a_unit, a_generic_terms, a_payment_terms):
        return Resource.objects.create(
            type=a_resource_type,
            authentication="none",
            name="resource in unit",
            unit=a_unit,
            max_reservations_per_user=1,
            max_period=timedelta(hours=2),
            reservable=True,
            generic_terms=a_generic_terms,
            payment_terms=a_payment_terms,
            specific_terms_fi='spesifiset käyttöehdot',
            specific_terms_en='specific terms of use',
            reservation_confirmed_notification_extra_en='this resource rocks'
        )

    @pytest.fixture
    def a_resource_type(self):
        return ResourceType.objects.get_or_create(id="test_space", name="test_space", main_type="space")[0]

    @pytest.fixture
    def a_unit(self):
        return Unit.objects.create(name="unit", time_zone='Europe/Helsinki')

    @pytest.fixture
    def a_generic_terms(self):
        return TermsOfUse.objects.create(
            name_fi='testikäyttöehdot',
            name_en='test terms of use',
            text_fi='kaikki on kielletty',
            text_en='everything is forbidden',
        )

    @pytest.fixture
    def a_payment_terms(self):
        return TermsOfUse.objects.create(
            name_fi='testimaksuehdot',
            name_en='test terms of payment',
            text_fi='kaikki on maksullista',
            text_en='everything is chargeable',
            terms_type=TermsOfUse.TERMS_TYPE_PAYMENT
        )

