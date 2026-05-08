import sys
import os

# Путь к виртуальному окружению на Beget (заполняется после загрузки)
VENV_PATH = os.path.join(os.path.dirname(__file__), 'venv', 'lib', 'python3.11', 'site-packages')
if VENV_PATH not in sys.path:
    sys.path.insert(0, VENV_PATH)

sys.path.insert(0, os.path.dirname(__file__))

os.environ['DJANGO_SETTINGS_MODULE'] = 'florea.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
