[![Travis CI](https://travis-ci.com/codepointtku/respaTku.svg?branch=master)](https://travis-ci.com/codepointtku/respa)
[![GitHub Actions](https://github.com/codepointtku/respa/actions/workflows/respa.yml/badge.svg?branch=develop)](https://github.com/codepointtku/respa/actions/workflows/respa.yml)
[![codecov](https://codecov.io/gh/codepointtku/respa/branch/develop/graph/badge.svg)](https://codecov.io/gh/codepointtku/respa)
[![Requirements Status](https://requires.io/github/codepointtku/respa/requirements.svg?branch=develop)](https://requires.io/github/codepointtku/respa/requirements/?branch=develop)

Respa – Resource reservation and management service
===================
Respa is a backend service for reserving and managing resources (e.g. meeting rooms, equipment, personnel). The open two-way REST API is interoperable with the [6Aika Resource reservation API specification](https://github.com/6aika/api-resurssienvaraus) created by the six largest cities in Finland.

User interface for Respa developed by the City of Turku is [Varaamo](https://github.com/codepointtku/varaamo)

There are two user interfaces for editing data: Admins may use the more powerful Django Admin UI - other users with less privileges may use the more restricted but easier-to-use and nicer-looking Respa Admin UI.


Table of Contents
-----------------
- [Contributing](#contributing)
- [Who is using Respa](#who-is-using-respa)
- [FAQ](#faq)
- [Installation](#installation)
- [Installation with Docker](#installation-with-docker)
- [Database](#database)
- [Running tests](#running-tests)
- [Production considerations](#production-considerations)
- [Requirements](#requirements)
- [Documentation](#documentation)
- [License](#license)


Contributing
------------

Your contributions are always welcome!

Our main issue tracking is on [Github](https://github.com/codepointtku/respa/issues). If you want to report a bug or see a new feature feel free to create a [new issue](https://github.com/codepointtku/respa/issues/new) on GitHub. Alternatively, you can create a pull request (base master branch). Your PR will be reviewed by the project tech lead.

- [City of Helsinki](https://api.hel.fi/respa/v1/) - for [Varaamo UI](https://varaamo.hel.fi/) & [Huvaja UI](https://huonevaraus.hel.fi/)
- [City of Lappeenranta](https://varaamo.lappeenranta.fi/respa/v1/) - for [Varaamo UI](https://varaamo.lappeenranta.fi/) - [GitHub repo](https://github.com/City-of-Lappeenranta/Respa)
- [City of Turku](https://respa.turku.fi/v1/) - for [Varaamo UI](https://varaamo.turku.fi/) - [GitHub repo](https://github.com/codepointtku/respa)
- [City of Hämeenlinna](https://varaukset.hameenlinna.fi/v1) - for [Varaamo UI](https://varaukset.hameenlinna.fi/varaamo/) and [Berth Reservation UI](https://varaukset.hameenlinna.fi/)  - [GitHub repo](https://github.com/CityOfHameenlinna/respa)
- [City of Espoo](https://api.hel.fi/respa/v1/) - for [Varaamo UI](https://varaamo.espoo.fi/)
- [City of Vantaa](https://api.hel.fi/respa/v1/) - for [Varaamo UI](https://varaamo.vantaa.fi/)
- [City of Oulu](https://varaamo-api.ouka.fi/v1/) - for [Varaamo UI](https://varaamo.ouka.fi/)
- [City of Mikkeli](https://mikkeli-respa.metatavu.io/v1/) - for [Varaamo UI](https://varaamo.mikkeli.fi/)
- [City of Raahe](https://varaamo-api.raahe.fi/v1/) - for [Varaamo UI](https://varaamo.raahe.fi/)
- [The Libraries of Lapland](https://varaamo-api.lapinkirjasto.fi/v1) - for [Varaamo UI](https://varaamo.lapinkirjasto.fi/)
- [City of Tampere](https://respa.tampere.fi/v1/) - for [Varaamo UI](https://varaamo.tampere.fi/) - [GitHub repo](https://github.com/Tampere/respa)
- [City of Lappeenranta](https://varaamo.lappeenranta.fi/respa/v1/) - for [Varaamo UI](https://varaamo.lappeenranta.fi/) - [GitHub repo](https://github.com/City-of-Lappeenranta/Respa)
     
FAQ
------------

### Why is it called Respa?
Short for "RESurssiPAlvelu" i.e. Resource Service.

Installation
------------

### Prepare and activate virtualenv

     virtualenv -p /usr/bin/python3 venv
     source venv/bin/activate

### Install required packages

Install all packages required for development with pip command:

     pip install -r dev-requirements.txt


### Create the database

Linux
```shell
sudo -u postgres createuser -P -R -S respa
sudo -u postgres psql -d template1 -c "create extension hstore;"
sudo -u postgres createdb -Orespa respa
sudo -u postgres psql respa -c "CREATE EXTENSION postgis;"
```

Windows
```
psql -U postgres -c "create role respa with encrypted password 'password';"
psql -U postgres --dbname=template1 -c "create extension hstore;"
psql -U postgres -c "create database respa;"
psql -U postgres --dbname=respa -c "create extension postgis;"
```


### Build Respa Admin static resources

Make sure you have Node 14 and npm installed.

```shell
./build-resources
```

### Dev environment configuration

Copy `.env.example` to `respa/.env`. Make sure the config matches your database setup.

```
cp .env.example respa/.env
```
### Run Django migrations and import data

```shell
python manage.py migrate
python manage.py createsuperuser
```

### Settings

Settings are done either by setting environment variables named after the setting or adding them to a `.env` file in the project root. The .env file syntax is similar to TOML files (INI files), ie. key-value pairs. The project root is the directory where this README is found. You can also set settings in a local_settings.py, which allows you to set any variables whatsoever. However, some of the settings documented here are named differently in settings.py, especially authentication variables.

- `DEBUG`: Whether to run Django in debug mode. [Django setting](https://docs.djangoproject.com/en/2.2/ref/settings/#debug).
- `GDAL_LIBRARY_PATH`: When GeoDjango can’t find the GDAL library, configure your Library environment settings or set GDAL_LIBRARY_PATH in your settings. [Django setting](https://docs.djangoproject.com/en/2.2/ref/contrib/gis/install/geolibs/#gdal-library-path)
- `SECRET_KEY`: Secret used for various functions within Django. This setting is mandatory for Django. [Django setting](https://docs.djangoproject.com/en/2.2/ref/settings/#secret-key).
- `ALLOWED_HOSTS`: List of Host-values, that Respa will accept in requests. This setting is a Django protection measure against HTTP [Host-header attacks](https://docs.djangoproject.com/en/2.2/topics/security/#host-headers-virtual-hosting). Specified as a comma separated list of allowed values. Note that this does NOT matter if you are running with DEBUG. [Django setting](https://docs.djangoproject.com/en/2.2/ref/settings/#allowed-hosts).
- `ADMINS`: List of tuples (or just e-mail addresses) specifying Administrators of this Respa instance. Django uses this only when logging is configured to send exceptions to admins. [Django setting](https://docs.djangoproject.com/en/2.2/ref/settings/#admins).
- `DATABASE_URL`: Configures database for Respa using URL style. Format is: `'postgis://USER:PASSWORD@HOST:PORT/NAME'`. Unused components may be left out, only Postgis is supported. The example value `'postgis:///respa'` configures Respa to use local PostgreSQL database called "respa", connecting same as username as Django is running as. [Django setting](https://docs.djangoproject.com/en/2.2/ref/settings/#databases).
- `SECURE_PROXY_SSL_HEADER`: Specifies a header that is trusted to indicate that the request was using https while traversing over the Internet at large. This is used when a proxy terminates the TLS connection and forwards the request over a secure network. Specified using a tuple. [Django setting](https://docs.djangoproject.com/en/2.2/ref/settings/#secure-proxy-ssl-header).
- `TOKEN_AUTH_ACCEPTED_AUDIENCE`: Respa uses JWT tokens for authentication. This setting specifies the value that must be present in the "aud"-key of the token presented by a client when making an authenticated request. Respa uses this key for verifying that the token was meant for accessing this particular Respa instance (the tokens are signed, see below). Does not correspond to standard Django setting.
- `TOKEN_AUTH_SHARED_SECRET`: This key is used by Respa to verify the JWT token is from trusted Identity Provider (OpenID terminology). The provider must have signed the JWT TOKEN using this shared secret. Does not correspond to standard Django setting.
- `MEDIA_ROOT`: Media root is the place in file system where Django and, by extension Respa stores "uploaded" files. This means any and all files that are inputted through importers or API. [Django setting](https://docs.djangoproject.com/en/2.2/ref/settings/#media-root).
- `STATIC_ROOT`: Static root is the place where Respa will install any static files that need to be served to clients. [Django setting](https://docs.djangoproject.com/en/2.2/ref/settings/#STATIC_ROOT).
- `MEDIA_URL`: Media URL is address (URL) where users can access files in MEDIA_ROOT through http. Ie. where your uploaded files are publicly accessible. In the simple case this is a relative URL to same server as API. [Django setting](https://docs.djangoproject.com/en/2.2/ref/settings/#media-url).
- `STATIC_URL`: Static URL is address (URL) where users can access files in STATIC_ROOT through http. Same factors apply as to MEDIA_URL. [Django setting](https://docs.djangoproject.com/en/2.2/ref/settings/#static-url).
- `SENTRY_DSN`: Sentry is an error tracking sentry (sentry.io) that can be self hosted or purchased as PaaS. SENTRY_DSN setting specifies the URL where reports for this Respa instance should be sent. You can find this in your Sentry interface (or through its API). Example value `'http://your.sentry.here/fsdafads/13'`.
- `SENTRY_ENVIRONMENT`: Sentry environment is an optional tag that can be included in sentry reports. It is used to separate deployments within Sentry UI.
- `COOKIE_PREFIX`: Cookie prefix is added to the every cookie set by Respa. These are mostly used when accessing the internal Django admin site. This applies to django session cookie and csrf cookie. Django setting: prepended to `CSRF_COOKIE_NAME` and `SESSION_COOKIE_NAME`.
- `INTERNAL_IPS`: Django INTERNAL_IPS setting allows some debugging aids for the addresses specified here. [Django setting](https://docs.djangoproject.com/en/2.2/ref/settings/#internal-ips). Example value `'127.0.0.1'`.
- `MAIL_ENABLED`: Whether sending emails to users is enabled or not.
- `RESPA_IMAGE_BASE_URL`: Base URL used when building image URLs in email notifications. Example value: `'https://turku.fi'`.
- `ACCESSIBILITY_API_BASE_URL`: Base URL used for Respa Admin Accessibility data input link. If left empty, the input link remains hidden in Respa Admin.
- `ACCESSIBILITY_API_SYSTEM_ID`: Accessibility API system ID. If left empty, the input link remains hidden in Respa Admin.
- `ACCESSIBILITY_API_SECRET`: Secret for the Accessibility API. If left empty, the input link remains hidden in Respa Admin.
- `RESPA_ADMIN_INSTRUCTIONS_URL`: URL for the user instructions link visible in Respa Admin. Example value: `'https://digipoint-turku.gitbook.io/varaamo-turku/yllapitoliittyma/aloitus'`.
- `RESPA_ADMIN_SUPPORT_EMAIL`: Email address for user support link visible in Respa Admin.
- `RESPA_ADMIN_VIEW_RESOURCE_URL`: URL for a "view changes" link in Respa Admin through which the user can view changes made to a given resource. Example value: `'https://varaamo.turku.fi/resources/'`.
- `RESPA_ADMIN_LOGO`: Name of the logo file to be displayed in Respa Admin UI. Logo file is assumed to be located in `respa_admin/static_src/img/`. Example value: `ra-logo.svg`.
- `RESPA_ADMIN_KORO_STYLE`: Defines the style of koro-shape used in login page and resources page. Accepts values: `koro-basic`, `koro-pulse`, `koro-beat`, `koro-storm`, `koro-wave`.
- `ENABLE_RESOURCE_TOKEN_AUTH`: Enable Django Rest Frameworks token authentication method for Resource endpoint.
- `DISABLE_SERVER_SIDE_CURSORS`: Disable server side cursors. Useful when using pgBouncer for example. See Django docs for more information: [Django setting](https://docs.djangoproject.com/en/3.0/ref/databases/#transaction-pooling-server-side-cursors).

### Setting up PostGIS/GEOS/GDAL on Windows (x64) / Python 3

* Install PGSQL from http://get.enterprisedb.com/postgresql/postgresql-9.4.5-1-windows-x64.exe
  * At the end of installation, agree to run Stack Builder and have it install the PostGIS bundle
* Install OSGeo4W64 from http://download.osgeo.org/osgeo4w/osgeo4w-setup-x86_64.exe
  * The defaults should do
* Add the osgeo4w64 bin path to your PATH
  * Failing to do this while setting `GEOS_LIBRARY_PATH`/`GDAL_LIBRARY_PATH` will result in
    "Module not found" errors or similar, which can be annoying to track down.

### Respa Admin authentication

Respa Admin views require logged in user with staff status.  For local
development you can log in via Django Admin login page to an account
with staff privileges and use that session to access the Respa Admin.

When accessing the Respa Admin without being logged in, the login
happens with Tunnistamo.  To test the Tunnistamo login flow in local
development environment this needs either real Respa app client id and
client secret in the production Tunnistamo or modifying helusers to use
local Tunnistamo.  The client id and client secret should be configured
in Django Admin or shell within a socialaccount.SocialApp instance with
id "turku".  When adding the app to Tunnistamo, the OIDC callback
URL for the app should be something like:
http://localhost:8000/accounts/tunnistamo/login/callback/

When the Tunnistamo registration is configured and the login is working,
then go to Django Admin and set the `is_staff` flag on for the user that
got created when testing the login.  This allows the user to use the
Respa Admin.

Installation with Docker
------------------------

```shell
# Setup multicontainer environment
docker-compose up

# Import database dump
cat <name_of_the_sanitized_respa_dump>.sql | docker exec -i respa-db psql -U postgres -d respa
```

Try: http://localhost:8000/ra/


Database
-------------

### Creating a sanitized database dump

This project uses Django Sanitized Dump for database sanitation.  Issue
the following management command on the server to create a sanitized
database dump:

    ./manage.py create_sanitized_dump > sanitized_db.sql


### Importing a database dump

If you want to import a database dump, create the empty database as in
"Create the database". Do not run any django commands on it, such as migrations
or import scripts. Instead import the tables and data from the dump:

    psql -h localhost -d respa -U respa -f sanitized_db.sql

After importing, check for missing migrations (your codebase may contain new
migrations that have not been executed in the dump) with `python manage.py
showmigrations`. You can run the new migrations with `python manage.py
migrate`.


Running tests
-------------

Respa uses the [pytest](http://pytest.org/latest/) test framework.

To run the test suite,

```shell
$ py.test .
```

should be enough.

```shell
$ py.test --cov-report html .
```

to generate a HTML coverage report.

If you get errors about failed database creation, you might need to add
priviledges for the respa postgresql account:

```
sudo -u postgres psql respa -c "ALTER ROLE respa WITH SUPERUSER CREATEDB;"
```

CreateDB allows the account to create a new database for the test run and
superuser is required to add the required extensions to the database.

Production considerations
-------------------------

### Respa Exchange sync

Respa supports synchronizing reservations with Exchange resource mailboxes (calendars). You can run the sync either manually through `manage.py respa_exchange_download`, or you can set up a listener daemon with `manage.py respa_exchange_listen_notifications`.

If you're using UWSGI, you can set up the listener as an attached daemon:

```yaml
uwsgi:
  attach-daemon2: cmd=/home/respa/run-exchange-sync.sh,pidfile=/home/respa/exchange_sync.pid,reloadsignal=15,touch=/home/respa/service_state/touch_to_reload
```

The helper script `run-exchange-sync.sh` activates a virtualenv and starts the listener daemon:

```bash
#!/bin/sh

. $HOME/venv/bin/activate

cd $HOME/respa
./manage.py respa_exchange_listen_notifications --log-file=$HOME/logs/exchange_sync.log --pid-file=$HOME/exchange_sync.pid --daemonize
```

### Delayed SMS Notifications

Use cron

```sh
$ crontab -e
$ */5 * * * * cd <project_path> && <venv_path/bin/python> manage.py handle_reminders > /dev/null 2>&1
```
### Theme customization

Theme customization, such as changing the main colors, can be done in `respa_admin/static_src/styles/application-variables.scss`.

By default, color theme is imported in this file. If you want to override certain colors, take a copy of the contents of the file
specified in the import, and customize. Remember to remove or uncomment the original import.

Requirements
------------

This project uses two files for requirements. The workflow is as follows.

`requirements.txt` is not edited manually, but is generated
with `pip-compile`.

`requirements.txt` always contains fully tested, pinned versions
of the requirements. `requirements.in` contains the primary, unpinned
requirements of the project without their dependencies.

In production, deployments should always use `requirements.txt`
and the versions pinned therein. In development, new virtualenvs
and development environments should also be initialised using
`requirements.txt`. `pip-sync` will synchronize the active
virtualenv to match exactly the packages in `requirements.txt`.

In development and testing, to update to the latest versions
of requirements, use the command `pip-compile`. You can
use [requires.io](https://requires.io) to monitor the
pinned versions for updates.

To remove a dependency, remove it from `requirements.in`,
run `pip-compile` and then `pip-sync`. If everything works
as expected, commit the changes.


Documentation
-------------

Documentation can be found in this GitHub repository (in English) and on [Gitbook](https://digipoint-turku.gitbook.io/varaamo-turku/yllapitoliittyma/aloitus) (in Finnish).

License
------------

Usage is provided under the [MIT License](https://github.com/City-of-Helsinki/respa/blob/master/LICENSE).
