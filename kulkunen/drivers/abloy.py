import contextlib
import pytz

from .base import AccessControlDriver, RemoteError
from kulkunen.models import AccessControlGrant

import jsonschema
from django.core.exceptions import ValidationError
import requests
from django.conf import settings
from datetime import datetime, timedelta
from django.utils.crypto import get_random_string
from django.utils import timezone

REQUESTS_TIMEOUT = 30  # seconds

class AbloyToken:
    access_token: str
    # refresh_token: str
    expires_at: datetime

    def __init__(self, access_token, expires_at):
        self.access_token = access_token
        # self.refresh_token = refresh_token
        self.expires_at = expires_at

    def has_expired(self):
        now = datetime.now()
        if now > self.expires_at + timedelta(seconds=30):
            return True
        return False

    # refresh by getting a new access token and expiration time
    def refresh(self, access_token, expires_at):
        self.access_token = access_token
        self.expires_at = expires_at

    def serialize(self):
        return dict(access_token=self.access_token, expires_at=self.expires_at.timestamp())

    @classmethod
    def deserialize(cls, data):
        try:
            access_token = data['access_token']
            expires_at = datetime.fromtimestamp(data['expires_at'])
        except Exception:
            return None
        return AbloyToken(access_token=access_token, expires_at=expires_at)

class AbloyDriver(AccessControlDriver):
    token: AbloyToken

    SYSTEM_CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "api_url": {
                "type": "string",
                "format": "uri",
                "pattern": "^https?://",
            },
            "header_username": {
                "type": "string",
            },
            "header_password": {
                "type": "string",
            },
            "body_username": {
                "type": "string",
            },
            "body_password": {
                "type": "string",
            },
            "organization_name": {
                "type": "string",
            }
        },
        "required": [
            "api_url", "header_username", "header_password", "body_username", "body_password",
        ],
    }
    RESOURCE_CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "access_point_group_name": { # resource and its doors to be accessed
                "type": "string",
            },
        },
        "required": [
            "access_point_group_name"
        ]
    }

    DEFAULT_CONFIG = {
        "client_id": "kulkunen",
    }

    def get_system_config_schema(self):
        return self.SYSTEM_CONFIG_SCHEMA

    def get_resource_config_schema(self):
        return self.RESOURCE_CONFIG_SCHEMA

    def get_resource_identifier(self, resource):
        config = resource.driver_config or {}
        return config.get('access_point_group_name', '')

    def validate_system_config(self, config):
        try:
            jsonschema.validate(config, self.SYSTEM_CONFIG_SCHEMA)
        except jsonschema.exceptions.ValidationError as e:
            raise ValidationError(e.message)

    def validate_resource_config(self, resource, config):
        try:
            jsonschema.validate(config, self.RESOURCE_CONFIG_SCHEMA)
        except jsonschema.exceptions.ValidationError as e:
            raise ValidationError(e.message)

    def _save_token(self, token):
        self.update_driver_data(dict(token=token.serialize()))

    def _load_token(self):
        data = self.get_driver_data().get('token')
        return AbloyToken.deserialize(data)

    def api_get_token(self):
        body_username = self.get_setting('body_username')
        body_password = self.get_setting('body_password')
        header_username = self.get_setting('header_username')
        header_password = self.get_setting('header_password')

        path = "oauth/token"
        url = '%s/%s' % (self.get_setting('api_url'), path)
        method = 'POST'
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Authorization": "Basic Auth"}
        args = dict(headers=headers)
        data = dict(username=body_username, password=body_password, grant_type="password")
        args['data'] = data

        resp = requests.request(method, url, timeout=REQUESTS_TIMEOUT,
            auth=(header_username, header_password), **args)

        response_data = resp.json()
        if not response_data['access_token']:
            raise Exception("Getting access_token failed!")
        access_token = response_data["access_token"]

        expires_at = datetime.now() + timedelta(seconds=(response_data["expires_in"]))
        token = AbloyToken(access_token=access_token, expires_at=expires_at)

        return token

    @contextlib.contextmanager
    def ensure_token(self):
        driver_data = self.get_driver_data()

        token = self._load_token()
        if not token or token.has_expired():
            token = self.api_get_token()

        self._save_token(token)

        try:
            yield token
        except Exception as e:
            raise

    def prepare_install_grant(self, grant):
        # limit amount of pin codes by installing grants only a day before reservation
        grant.install_at = grant.starts_at - timedelta(days=1)
        grant.save(update_fields=['install_at'])

    def install_grant(self, grant):
        assert grant.state == grant.INSTALLING

        user = self.create_access_user(grant)
        user.save()
        grant.access_code = user.identifier
        grant.user = user
        grant.save_access_code_to_reservation()
        grant.remove_at = grant.ends_at

        tz = pytz.timezone('Europe/Helsinki')
        starts_at = grant.starts_at.astimezone(tz).replace(tzinfo=None)
        ends_at = grant.ends_at.astimezone(tz).replace(tzinfo=None)

        # get person data and generate new role validity times based on previous role
        # validity times if they exist.
        person_data = {}
        try:
            person_data = self.handle_api_get_person({"ssn": str(grant.reservation.user.uuid)},)
        except:
            self.logger.info('Getting person data failed. Resetting reservation access code')
            grant.reset_reservation_access_code()
        person_roles = {}
        if 'roles' in person_data:
            person_roles = self.convert_validity_times_from_timestamp(person_data['roles'])

        role_validities = self.get_role_validity_times(person_roles, grant.resource.driver_config.get("access_point_group_name"))
        role_validities.append({"start": str(starts_at), "end": str(ends_at)})

        data = {
            "person": {
                "firstname": grant.reservation.user.first_name,
                "lastname": grant.reservation.user.last_name,
                "validityStart": None,
                "validityEnd": None,
                "ssn": str(grant.reservation.user.uuid)
            },
            "organizations": [{
                "name": self.get_setting("organization_name") or "Respa",
                "type": "company",
                "person_belongs": "true",
            }],
            "tokens": [{
                "surfaceMarking": "PIN-" + grant.access_code,
                "code": self.convert_token_code_to_hex(grant.access_code),
                "tokenType": "default",
                "validityStart": str(starts_at),
                "validityEnd": str(ends_at),
            }],
            "roles": [
                {
                    "name": grant.resource.driver_config.get("access_point_group_name"),
                    "validities": role_validities
                }
            ],
            "options": {
                "mode_organizations": "replace",
                "mode_roles": "add",
                "mode_tokens": "add",
                "mode_qualifications": None,
                "mode_identification": "ssn"
            }
        }

        path = "api/v1/persons-setup"
        try:
            self.handle_api_post(data, path)
        except:
            self.logger.info('Posting person data failed. Resetting reservation access code')
            grant.reset_reservation_access_code()

        grant.state = grant.INSTALLED
        grant.save()
        grant.send_notify_email()

    def remove_grant(self, grant):
        assert grant.state == grant.REMOVING

        tz = pytz.timezone('Europe/Helsinki')
        starts_at = grant.starts_at.astimezone(tz).replace(tzinfo=None)
        ends_at = grant.ends_at.astimezone(tz).replace(tzinfo=None)

        # if previous call failed with 422, it's possible the person data is not accurate...
        person_data = self.handle_api_get_person({"ssn": str(grant.reservation.user.uuid)},)

        # handle updating tokens
        person_tokens = self.convert_validity_times_from_timestamp(person_data["tokens"])
        person_tokens = self.add_token_types_and_surface_markings(person_tokens)

        person_tokens = self.remove_token_from_person(person_tokens, grant.access_code)
        person_tokens = self.convert_person_token_codes_to_hex(person_tokens)

        # handle updating roles
        person_roles = self.convert_validity_times_from_timestamp(person_data["roles"])
        person_roles = self.remove_role_from_person(person_roles,
            grant.resource.driver_config.get("access_point_group_name"), starts_at, ends_at)

        data = {
            "person": {
                "firstname": grant.reservation.user.first_name,
                "lastname": grant.reservation.user.last_name,
                "validityStart": None,
                "validityEnd": None,
                "ssn": str(grant.reservation.user.uuid)
            },
            "organizations": [{
                "name": self.get_setting("organization_name") or "Respa",
                "type": "company",
                "person_belongs": "true"
            }],
            "options": {
                "mode_organizations": None,
                "mode_roles": "replace",
                "mode_tokens": "replace",
                "mode_qualifications": None,
                "mode_identification": "ssn"
            }
        }

        data.update({"roles": person_roles})
        data.update({"tokens": person_tokens})

        path = "api/v1/persons-setup"

        # send post to remove reservation data
        self.handle_api_post(data, path)

        # update and save user data
        user = grant.user
        user.state = user.REMOVED
        user.removed_at = timezone.now()
        user.save(update_fields=['state', 'removed_at'])

        # update and save grant data
        grant.state = grant.REMOVED
        grant.removed_at = user.removed_at
        grant.save(update_fields=['state', 'removed_at'])

    def handle_api_post(self, data, path):
        with self.ensure_token() as token:
            # build POST request
            url = '%s/%s' % (self.get_setting('api_url'), path)
            method = 'POST'
            headers = {"Accept": "application/json", "Authorization": "Bearer "+ token.access_token,}
            args = dict(headers=headers)
            args['json'] = data

            # send request and handle its response
            resp = requests.request(method, url, timeout=REQUESTS_TIMEOUT, **args)

            if resp.status_code not in (200, 201, 204):
                if resp.content:
                    try:
                        data = resp.json()
                        err_code = data.get('error')
                        err_str = data.get('message')
                    except Exception:
                        err_code = ''
                        err_str = ''
                    status_code = resp.status_code
                    self.logger.error(f"Abloy API error [HTTP {status_code}] [{err_code}] {err_str}")
                    raise Exception(f"Abloy API error [HTTP {status_code}] [{err_code}] {err_str}")

            if not resp.content:
                self.logger.error(f"api response is missing content")

    # Handles getting given person's data and returns the data json
    # if person exists, otherwise returns None
    def handle_api_get_person(self, data):
        with self.ensure_token() as token:
            # build GET request
            path = "api/v1/persons"
            url = '%s/%s' % (self.get_setting('api_url'), path)
            method = 'GET'
            headers = {"Accept": "application/json", "Authorization": "Bearer "+ token.access_token,}
            args = dict(headers=headers)
            args['params'] = data

            # send request and handle its response
            resp = requests.request(method, url, timeout=REQUESTS_TIMEOUT, **args)

            # allow 404 because new user is created when user is not found
            if resp.status_code not in (200, 201, 204, 404):
                if resp.content:
                    try:
                        data = resp.json()
                        err_code = data.get('error')
                        err_str = data.get('message')
                    except Exception:
                        err_code = ''
                        err_str = ''
                    status_code = resp.status_code
                    self.logger.error(f"Abloy API error [HTTP {status_code}] [{err_code}] {err_str}")
                    raise Exception(f"Abloy API error [HTTP {status_code}] [{err_code}] {err_str}")

            if not resp.content:
                return None
            else:
                return resp.json()


    def create_access_user(self, grant):
        user = grant.reservation.user
        first_name = user.first_name or 'Kulkunen'
        last_name = user.last_name or 'Kulkunen'

        grant.resource

        # We lock the access control instance through the database to protect
        # against race conditions.
        with self.system_lock():
            # set how many pin digits are used based on resource access code type
            pin_digits = 0
            if grant.reservation.resource.access_code_type == grant.reservation.resource.ACCESS_CODE_TYPE_PIN4:
                pin_digits = 4
            elif grant.reservation.resource.access_code_type == grant.reservation.resource.ACCESS_CODE_TYPE_PIN6:
                pin_digits = 6
            else:
                raise RemoteError("Unable to create PIN code for grant. Resource has not set access code type!")

            # try to find an unused PIN code to use before trying to generate a new code
            pin = self.get_free_removed_access_code(pin_digits)

            if not pin:
                # Try at most 20 times to generate an unused PIN,
                # and if that fails, we probably have other problems. Upper layers
                # will take care of retrying later in case the unlikely false positive
                # happens.
                i = 1
                while i < 20:
                    pin = get_random_string(1, '123456789') + get_random_string(pin_digits-1, '0123456789')
                    if not self.system.users.active().filter(identifier=pin).exists():
                        break
                    i += 1
                else:
                    raise RemoteError("Unable to find a PIN code for grant")

            user_attrs = dict(identifier=pin, first_name=first_name, last_name=last_name, user=user)
            user = self.system.users.create(**user_attrs)

        return user

    # Returns an already used/removed pin code that is currently not in use
    def get_free_removed_access_code(self, pin_digits):
        # Search for a unique removed code that is not in use now and return it
        # Make sure the code has correct amount of digits
        system_grants = AccessControlGrant.objects.filter(resource__system=self.system).distinct()
        removed_state = AccessControlGrant.REMOVED
        non_removed_states = (AccessControlGrant.INSTALLED,AccessControlGrant.INSTALLING,
            AccessControlGrant.CANCELLED, AccessControlGrant.REMOVING)

        removed_grant_codes = system_grants.filter(state__exact=removed_state).values('access_code').distinct()
        non_removed_grant_codes = system_grants.filter(state__in=non_removed_states).values('access_code').distinct()
        for code in removed_grant_codes:
            if isinstance(code['access_code'], str) and len(code['access_code']) == pin_digits:
                if not code in non_removed_grant_codes:
                    return code['access_code']

        return None


    # Removes grant token from person.
    def remove_token_from_person(self, tokens, token):
        # make a copy of tokens and return the new copy instead of modifying the given one
        new_tokens = tokens.copy()

        for i in range(len(new_tokens)):
            if new_tokens[i]['code'] == token:
                del new_tokens[i]
                break

        return new_tokens

    # Removes grant role from person's roles list.
    # If role with correct name, start time and end time is found
    # remove the found role from roles list.
    def remove_role_from_person(self, roles, role_name, start, end):
        new_roles = roles.copy()
        for i in range(len(new_roles)):
            if new_roles[i]['name'] == role_name:
                if new_roles[i]['validityStart'] == str(start) and new_roles[i]['validityEnd'] == str(end):
                    del new_roles[i]
                    break

        return new_roles


    # Converts validity times from unix timestamp to human readable form
    # e.g. "2020-02-12 10:05:00". List with times is expected to contain
    # validityStart and validityEnd key value pairs. Returns a new list
    # containing the converted times.
    def convert_validity_times_from_timestamp(self, list_with_times):
        tz = pytz.timezone('Europe/Helsinki')
        new_list = list_with_times.copy()
        for i in range(len(new_list)):
            if new_list[i]['validityStart']:
                new_list[i]['validityStart'] = str(datetime.fromtimestamp(new_list[i]['validityStart']/1000, tz).replace(tzinfo=None))
            if new_list[i]['validityEnd']:
                new_list[i]['validityEnd'] = str(datetime.fromtimestamp(new_list[i]['validityEnd']/1000, tz).replace(tzinfo=None))

        return new_list

    # Converts pin code e.g. 1234 to hex "000004D2"
    def convert_token_code_to_hex(self, token_code):
        hex_token = (int(token_code)).to_bytes(4, byteorder='big').hex()
        # hex needs to be in upper case
        return hex_token.upper()

    # Converts all person's pin codes to hex and returns new list
    # of tokens with converted pin codes.
    def convert_person_token_codes_to_hex(self, tokens):
        new_tokens = tokens.copy()
        for i in range(len(new_tokens)):
            new_tokens[i]['code'] = self.convert_token_code_to_hex(new_tokens[i]['code'])

        return new_tokens

    # Adds API required token types ("default") and surface markings to person tokens
    # and returns a new token list containing updated person tokens.
    def add_token_types_and_surface_markings(self, tokens):
        new_tokens = tokens.copy()
        for i in range(len(new_tokens)):
            new_tokens[i]['tokenType'] = "default"
            new_tokens[i]['surfaceMarking'] = "PIN-" + str(new_tokens[i]['code'])

        return new_tokens

    # Gets a list of validity times from a list of roles with given name.
    # Expects roles list single roles to contain validity times in
    # validityStart and validityEnd key value pairs.
    def get_role_validity_times(self, roles, role_name):
        validities = []
        for i in range(len(roles)):
            if roles[i]['name'] == role_name:
                validities.append({"start": roles[i]['validityStart'], "end": roles[i]['validityEnd']})

        return validities


    def save_respa_resource(self, resource, respa_resource):
        # Abloy driver generates access codes by itself, so we need to
        # make sure Respa doesn't generate them.
        if not respa_resource.generate_access_codes:
            return
        respa_resource.generate_access_codes = False

    def save_resource(self, resource):
        # Abloy driver generates access codes by itself, so we need to
        # make sure Respa doesn't generate them.
        respa_resource = resource.resource
        if not respa_resource.generate_access_codes:
            return
        respa_resource.generate_access_codes = False
        respa_resource.save(update_fields=['generate_access_codes'])
