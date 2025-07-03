from pathlib import Path
from dotenv import load_dotenv
import environ
from datetime import timedelta
import os

env = environ.Env()
environ.Env.read_env()
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-1%s1ng!@lu-v=jg$c)6zk5jq@c-$+n6z%3tg%gl35h12hj=kp7'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

#
# ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")

ALLOWED_HOSTS= ["*"]
# # Application definition

INSTALLED_APPS = [
    'corsheaders',
    'channels',
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_telegram_login',
    'users.apps.UsersConfig',
    'games.apps.GamesConfig',
    "django_celery_beat",
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",

]


LOG_DIR = "logs"  # Папка для логов
os.makedirs(LOG_DIR, exist_ok=True)  # Создаем папку, если её нет

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} [{module}.{funcName}]: {message}",
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "style": "{",
        },
        "simple": {
            "format": "[{asctime}] {levelname}: {message}",
            "datefmt": "%H:%M:%S",
            "style": "{",
        },
    },
    "handlers": {
        "debug_file": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(LOG_DIR, "debug.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
            "formatter": "verbose",
        },
        "error_file": {
            "level": "ERROR",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(LOG_DIR, "errors.log"),
            "maxBytes": 2 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "console": {
            "level": "INFO",  # Теперь показывает только INFO, WARNING, ERROR
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "loggers": {
        "django.db.backends": {
            "handlers": ["debug_file"],
            "level": "WARNING",
            "propagate": False,
        },
        "transactions": {
            "handlers": ["console", "debug_file", "error_file"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ]
}



SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'AUTH_HEADER_TYPES': ('Bearer',),
}


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    "users.middleware.AdminIPRestrictionMiddleware"
]

SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"

ROOT_URLCONF = 'GamesCripth.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


AUTH_USER_MODEL = 'users.User'


ASGI_APPLICATION = "GamesCripth.asgi.application"

WSGI_APPLICATION = 'GamesCripth.wsgi.application'

SESSION_ENGINE = "django.contrib.sessions.backends.db"  # Хранение в БД
SESSION_COOKIE_NAME = "sessionid"  # Название cookie
SESSION_COOKIE_HTTPONLY = True  # Запрет на доступ через JS
SESSION_COOKIE_SECURE = False  # Включи True, если HTTPS
SESSION_SAVE_EVERY_REQUEST = True  # Обновлять сессию при каждом запросе
# CORS_ORIGIN_ALLOW_ALL = True
# CSRF_TRUSTED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
#

# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases
#
# CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "GamesCripth",
        "USER": env("POSTGRES_USER", default="postgres"),
        "PASSWORD": env("POSTGRES_PASSWORD", default="postgres"),
        "HOST": env("POSTGRES_HOST", cast=str),
        "PORT": env("POSTGRES_PORT", cast=str),
    },
}



# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(env("REDIS_HOST"), 6379)],
        },
    },
}



#Кэш
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
         'LOCATION': f'redis://{env("REDIS_HOST", default="127.0.0.1")}:6379/1',  # База Redis для кэша
    }
}


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'ru'
TIME_ZONE = 'Europe/Moscow'

USE_I18N = True
USE_L10N = True
USE_TZ = True

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]



# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = 'static/'

CELERY_BROKER_URL = f"redis://{env('REDIS_HOST', cast=str)}:6379/0"
CELERY_RESULT_BACKEND = f"redis://{env('REDIS_HOST', cast=str)}:6379/0"
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 3600}

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

TELEGRAM_BOT_NAME = env("TELEGRAM_BOT_NAME")
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_LOGIN_REDIRECT_URL = 'https://gamecripth.share.zrok.io'

__all__=()
