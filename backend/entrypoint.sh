#!/bin/sh
set -e

# --upload-unhashed-files: django-cloudinary-storage's collectstatic override
# (which shadows Django's own via app-loading order) is a no-op unless
# STATICFILES_STORAGE is its own StaticCloudinaryStorage class or this flag
# is passed -- we use whitenoise for static files, so without this flag
# collectstatic silently copies nothing.
python manage.py migrate --noinput
python manage.py collectstatic --noinput --upload-unhashed-files

exec "$@"
