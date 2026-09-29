#!/bin/sh
set -eu

alembic -c conf/alembic.ini upgrade head
exec supervisord -n -c /app/conf/supervisord.conf
