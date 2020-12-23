from django.apps import AppConfig
from django.db.models.signals import post_save, pre_delete




class RespaO365Config(AppConfig):
    name = 'respa_o365'

    def ready(self):
        """
        Wire up the signals for uploading reservations.
        """
        from respa_o365.django_signal_handlers import handle_reservation_save
        post_save.connect(
            handle_reservation_save,
            sender='resources.Reservation',
            dispatch_uid='respa-o365-save'
        )
