import logging
from typing import Any, Optional
from django.core.management.base import BaseCommand
from respa_o365.calendar_sync import process_queue

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    'Processes the Outlook sync queue'

    def handle(self, *args: Any, **options: Any) -> Optional[str]:
        logger.info("Processing sync queue.")
        process_queue()
