from django.core.management.base import BaseCommand
from qualitytool.models import ResourceQualityTool
from qualitytool.manager import qt_manager
import logging

logger = logging.getLogger()


class Command(BaseCommand):
    help = "Sends daily utilization to Suomi.fi qualitytool target"

    def handle(self, *args, **options):
        payload = [
            qt_manager.get_daily_utilization(qualitytool) 
            for qualitytool in ResourceQualityTool.objects.all()
        ]
        if not payload:
            return
        return qt_manager.post_utilization(payload)