from base64 import b64decode
from django.conf import settings
from functools import lru_cache, wraps

import string
import random
import json
import time


HEADERS = {
  'User-Agent': 'Respa API',
  'Accept': 'application/json',
  'Content-Type': 'application/json',
  'From': settings.SERVER_EMAIL
}


class Struct:
    items = 0
    def __init__(self, dictionary):
        for key, value in dictionary.items():
            if isinstance(value, (list, tuple)):
                self.items += len(value)
                setattr(self, key, [Struct(x) if isinstance(x, dict) else x for x in value])
            else:
                self.items += 1
                setattr(self, key, Struct(value) if isinstance(value, dict) else value)
    
    def __str__(self):
        return '<Object>'

    def __getitem__(self, key):
        return getattr(self, key, None)
    
    def is_empty(self):
        return self.items == 0



class JWTPayload(Struct):
    pass

def generate_random_string(length):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def get_payload(jwt):
    _, payload, _ = jwt.split('.')
    payload = b64decode(
        f'{payload}{"="*divmod(len(payload),4)[1]}'.encode()
    )
    return JWTPayload(json.loads(payload.decode()))



def has_expired(jwt):
    if not jwt:
        return True
    payload = get_payload(jwt)
    return time.time() > payload.exp



def clear_cache(*, seconds):
    def cache_handler(f):
        def wrapper(*args, **kwargs):
            exp_time = getattr(f, '_exp_time', False)
            if not exp_time:
                setattr(f, '_exp_time', time.time() + seconds)
            elif time.time() > exp_time:
                f.cache_clear()
                setattr(f, '_exp_time', time.time() + seconds)
            return f(*args, **kwargs)
        return wrapper
    return cache_handler
