from django.db import transaction
from respa_o365.calendar_sync import ensure_notification, perform_sync_to_exchange
from respa_o365.models import OutlookCalendarLink
from typing import Any, Optional
from django.core.management.base import BaseCommand, CommandParser

class Command(BaseCommand):
    'Syncs reservations and opening hours with linked Outlook calendars'
    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument('--resource', help='Only sync the specified resource')

    def handle(self, *args: Any, **options: Any) -> Optional[str]:
        resource_id = options['resource']
        with transaction.atomic():
            calendar_links = OutlookCalendarLink.objects.select_for_update().all()
            if resource_id is not None:
                calendar_links = calendar_links.filter(resource_id=resource_id)
                
            for link in calendar_links:
                #logger.info("Synchronising user %d resource %s", link.user_id, link.resource_id)
                perform_sync_to_exchange(link, lambda sync: sync.sync_all())
                ensure_notification(link)