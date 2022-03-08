#!/bin/bash

echo "NOTICE: Get static files for serving"
./manage.py collectstatic --no-input

echo "NOTICE: Start the uwsgi web server"
exec uwsgi --ini deploy/uwsgi.ini --check-static /var/www
