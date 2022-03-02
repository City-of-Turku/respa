FROM postgis/postgis:14-master

ENV APP_NAME respa-postgres-db

RUN apt-get update \
        && apt-get install --no-install-recommends -y postgis postgresql postgresql-contrib \
        && rm -rf /var/lib/apt/lists/*

RUN localedef -i fi_FI -c -f UTF-8 -A /usr/share/locale/locale.alias fi_FI.UTF-8

ENV LANG fi_FI.UTF-8

COPY ./docker/postgres/docker-entrypoint.sh /docker-entrypoint-initdb.d/docker-entrypoint.sh

EXPOSE 5432