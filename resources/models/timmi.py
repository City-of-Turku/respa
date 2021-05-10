from django.contrib.gis.db import models
from base64 import b64encode, b64decode
from payments.models import Order
from django.utils.translation import ugettext_lazy as _
from resources.timmi.exceptions import MissingSapCodeError

import json

class TimmiPayload(models.Model):
    order = models.ForeignKey(
        Order, verbose_name=_('Order'), related_name='timmi_payload_orders',
        on_delete=models.CASCADE
    )
    _payload = models.TextField(verbose_name=_('Timmi payload'), null=True, blank=True)

    def save(self, *args, **kwargs):
        payload = json.dumps(kwargs['payload']).encode()
        self._payload = b64encode(payload).decode()
        del kwargs['payload']
        super().save(*args, **kwargs)
    
    @property
    def payload(self):
        payload = b64decode(self._payload.encode())
        return json.loads(payload.decode())

    @property
    def sap_code(self):
        code = self.payload.get('cashProduct', [{}])[0].get('accountingCode', 0)
        if not code:
            raise MissingSapCodeError('Sap code missing from response.')
        return str(code).zfill(18)