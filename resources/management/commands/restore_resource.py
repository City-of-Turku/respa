from django.core.management.base import BaseCommand
from resources.models.resource import Resource

import logging

logger = logging.getLogger()

class Command(BaseCommand):
    help = 'Restore soft deleted resources'

    def add_arguments(self, parser):
        parser.add_argument('pk', type=str, nargs='+', help='Resources pk')

    def handle(self, *args, **options):
        pks = options['pk']
        resources = Resource.objects.with_soft_deleted.filter(pk__in=pks)
        if not resources.exists():
            logger.error('No resources found with given pks.')
            return
        logger.info('Restoring %u resources', resources.count())
        resources.restore()
