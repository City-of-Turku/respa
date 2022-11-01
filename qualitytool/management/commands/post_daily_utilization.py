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
        parser.add_argument('--begin', action='store')
        parser.add_argument('--end', action='store')

    def handle(self, *args, **options):
        begin = options.get('begin', None)
        end = options.get('end', None)


        if begin and end:
            begin = datetime.strptime(begin, '%Y-%m-%d')
            end = datetime.strptime(end, '%Y-%m-%d')
        else:
            begin = (timezone.now() - timedelta(days=1)).replace(microsecond=0, hour=0, minute=0, second=0)
            end = timezone.now().replace(microsecond=0, hour=0, minute=0, second=0)

        payload = [
            qt_manager.get_daily_utilization(qualitytool, begin, end) 
            for qualitytool in ResourceQualityTool.objects.all()
        ]
        if not payload:
            return
        return qt_manager.post_utilization(payload)