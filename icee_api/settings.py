import os
from pathlib import Path
from dotenv import load_dotenv
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'insecure-development-key-change-this')
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
ALLOWED_HOSTS = [x.strip() for x in os.getenv('ALLOWED_HOSTS','localhost,127.0.0.1').split(',')]
INSTALLED_APPS = ['django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','rest_framework','rest_framework.authtoken','rest_framework_simplejwt.token_blacklist','corsheaders','icee_api']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','corsheaders.middleware.CorsMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware']
ROOT_URLCONF = 'icee_api.urls'
TEMPLATES = []
WSGI_APPLICATION = 'icee_api.wsgi.application'
DATABASES = {'default': {'ENGINE':'django.db.backends.sqlite3','NAME':BASE_DIR/'auth.sqlite3'}}
AUTH_PASSWORD_VALIDATORS = [{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator'},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE='en-us'; TIME_ZONE='Africa/Lagos'; USE_I18N=True; USE_TZ=True
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
REST_FRAMEWORK = {
 'DEFAULT_AUTHENTICATION_CLASSES':['rest_framework_simplejwt.authentication.JWTAuthentication'],
 'DEFAULT_PERMISSION_CLASSES':['rest_framework.permissions.IsAuthenticated'],
 'DEFAULT_THROTTLE_CLASSES':['rest_framework.throttling.AnonRateThrottle','rest_framework.throttling.UserRateThrottle'],
 'DEFAULT_THROTTLE_RATES':{'anon':'20/hour','user':'120/hour','face':'20/hour'},
 'DEFAULT_RENDERER_CLASSES':['rest_framework.renderers.JSONRenderer'],
}
CORS_ALLOWED_ORIGINS = [x.strip() for x in os.getenv('CORS_ALLOWED_ORIGINS','http://localhost:5173').split(',')]
MONGO_URI=os.getenv('MONGO_URI','mongodb://127.0.0.1:27017')
MONGO_DATABASE=os.getenv('MONGO_DATABASE','icee')
BIOMETRIC_ENCRYPTION_KEY=os.getenv('BIOMETRIC_ENCRYPTION_KEY','')
MATCH_THRESHOLD=float(os.getenv('MATCH_THRESHOLD','0.48'))
REVIEW_THRESHOLD=float(os.getenv('REVIEW_THRESHOLD','0.40'))
PAD_ENABLED=os.getenv('PAD_ENABLED','False').lower()=='true'
MAX_UPLOAD_MB=int(os.getenv('MAX_UPLOAD_MB','6'))
from datetime import timedelta
SIMPLE_JWT={'ACCESS_TOKEN_LIFETIME':timedelta(minutes=10),'REFRESH_TOKEN_LIFETIME':timedelta(hours=8),'ROTATE_REFRESH_TOKENS':True,'BLACKLIST_AFTER_ROTATION':True,'AUTH_HEADER_TYPES':('Bearer',)}
SECURE_CONTENT_TYPE_NOSNIFF=True
X_FRAME_OPTIONS='DENY'
if not DEBUG:
    SECURE_SSL_REDIRECT=True
    SESSION_COOKIE_SECURE=True
    CSRF_COOKIE_SECURE=True
