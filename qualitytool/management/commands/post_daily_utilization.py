from django.core.management.base import BaseCommand
from django.utils import timezone
from qualitytool.models import ResourceQualityTool
from qualitytool.manager import qt_manager
import logging

logger = logging.getLogger()

from datetime import datetime, timedelta

class Command(BaseCommand):
    help = "Sends daily utilization to Suomi.fi qualitytool target"

    def add_arguments(self, parser):
        parser.add_argument('--date', action='store')

    def handle(self, *args, **options):
        date = options.get('date', None)


        if date:
            date = timezone.make_aware(datetime.strptime(date, '%Y-%m-%d'))
        else:
            date = timezone.now()
    
        payload = [
            qt_manager.get_daily_utilization(qualitytool, date) 
            for qualitytool in ResourceQualityTool.objects.all()
        ]

        if not payload:
            return
        return qt_manager.post_utilization(payload)