FROM postgis/postgis:14-3.4

ENV APP_NAME=respa-postgres-db

# Base image already includes PostGIS, PostgreSQL and contrib - no need to apt-get install

RUN localedef -i fi_FI -c -f UTF-8 -A /usr/share/locale/locale.alias fi_FI.UTF-8

ENV LANG=fi_FI.UTF-8

COPY ./docker/postgres/docker-entrypoint.sh /docker-entrypoint-initdb.d/docker-entrypoint.sh

EXPOSE 5432
