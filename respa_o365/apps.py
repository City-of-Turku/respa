from django.apps import AppConfig
from django.db.models.signals import post_save, pre_delete, pre_save




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

        from respa_o365.django_signal_handlers import handle_period_save
        pre_save.connect(
            handle_period_save,
            sender='resources.Period',
            dispatch_uid='respa-o365-period-save'
        )

        pre_delete.connect(
            handle_period_save,
            sender='resources.Period',
            dispatch_uid='respa-o365-period-delete'
        )

        from respa_o365.django_signal_handlers import handle_calendar_link_delete
        pre_delete.connect(
            handle_calendar_link_delete,
            sender='respa_o365.OutlookCalendarLink'
        )

    