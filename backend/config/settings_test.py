"""
Settings auxiliares solo para CI / tests locales rápidos (sin Postgres).
Uso:  python manage.py test --settings=config.settings_test
"""
from .settings import *  # noqa

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'test_db.sqlite3',
    }
}
