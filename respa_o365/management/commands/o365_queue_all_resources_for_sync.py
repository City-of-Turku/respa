import logging
from typing import Any, Optional
from django.db import transaction
from django.core.management.base import BaseCommand, CommandParser
from respa_o365.calendar_sync import add_to_queue, ensure_notification, process_queue
from respa_o365.models import OutlookCalendarLink

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    'Adds every resource to the O365 sync queue, to be processed by the o365_process_sync_queue command'
    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument('--resource', help='Only sync the specified resource')

    def handle(self, *args: Any, **options: Any) -> Optional[str]:

        resource_id = options['resource']

        with transaction.atomic():
            if resource_id is not None:
                calendar_links = OutlookCalendarLink.objects.filter(resource_id=resource_id)
            else:
                calendar_links = OutlookCalendarLink.objects.all()

            for link in calendar_links:
                logger.info("Adding resource %s (%s) to sync queue.", link.resource.name, link.resource_id)
                add_to_queue(link)
                ensure_notification(link)