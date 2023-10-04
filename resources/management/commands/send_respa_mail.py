from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives

import logging


logger = logging.getLogger('respa.notifications')

class Command(BaseCommand):
    help = 'Send test email through Django default backend'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='Email address to send test email to.')
        parser.add_argument('subject', type=str, help='Email subject of the test email.')
        parser.add_argument('content', type=str, help='Email content of the test email.')

    def handle(self, *args, **options):
        assert settings.EMAIL_HOST_USER is not None
        _from = settings.EMAIL_HOST_USER

        text_content = options['content'].strip()
        msg = EmailMultiAlternatives(options['subject'].strip(), text_content, _from, [options['email'].strip()])
        logger.info('[%s:%s] (%s) :: Sending email -=> (%s) "%s": %s' % (settings.EMAIL_HOST, settings.EMAIL_PORT, _from, options['email'].strip(), options['subject'].strip(), options['content'].strip()))
        msg.send()
