"""
Application Configuration
Loads environment variables and provides configuration classes for different environments
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


class Config:
    """Base configuration class"""

    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'perfume_pos.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    # Cloud Database for Sync
    CLOUD_DATABASE_URL = os.environ.get('CLOUD_DATABASE_URL')
    ENABLE_CLOUD_SYNC = os.environ.get('ENABLE_CLOUD_SYNC', 'False').lower() == 'true'
    SYNC_INTERVAL_MINUTES = int(os.environ.get('SYNC_INTERVAL_MINUTES', 30))
    AUTO_SYNC = os.environ.get('AUTO_SYNC', 'True').lower() == 'true'

    # Email Configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or os.environ.get('MAIL_USERNAME')
    DAILY_REPORT_RECIPIENTS = os.environ.get('DAILY_REPORT_RECIPIENTS', '').split(',')
    DAILY_REPORT_TIME = os.environ.get('DAILY_REPORT_TIME', '18:00')

    # SendGrid
    SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')

    # Business Configuration
    BUSINESS_NAME = os.environ.get('BUSINESS_NAME', 'Sunnat Collection')
    BUSINESS_ADDRESS = os.environ.get('BUSINESS_ADDRESS', 'Mall of Wah, Pakistan')
    BUSINESS_PHONE = os.environ.get('BUSINESS_PHONE', '')
    BUSINESS_EMAIL = os.environ.get('BUSINESS_EMAIL', '')
    CURRENCY = os.environ.get('CURRENCY', 'PKR')
    CURRENCY_SYMBOL = os.environ.get('CURRENCY_SYMBOL', 'Rs.')
    TAX_RATE = float(os.environ.get('TAX_RATE', 0.0))

    # Session Configuration
    PERMANENT_SESSION_LIFETIME = timedelta(
        seconds=int(os.environ.get('PERMANENT_SESSION_LIFETIME', 3600))
    )
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # File Upload
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))  # 16MB
    UPLOAD_FOLDER = os.path.join(basedir, os.environ.get('UPLOAD_FOLDER', 'static/uploads'))
    ALLOWED_EXTENSIONS = set(os.environ.get('ALLOWED_EXTENSIONS', 'png,jpg,jpeg,gif,csv,xlsx').split(','))

    # Pagination
    ITEMS_PER_PAGE = int(os.environ.get('ITEMS_PER_PAGE', 50))

    # Stock Alerts
    LOW_STOCK_THRESHOLD = int(os.environ.get('LOW_STOCK_THRESHOLD', 10))
    CRITICAL_STOCK_THRESHOLD = int(os.environ.get('CRITICAL_STOCK_THRESHOLD', 5))

    # Backup
    BACKUP_ENABLED = os.environ.get('BACKUP_ENABLED', 'True').lower() == 'true'
    BACKUP_TIME = os.environ.get('BACKUP_TIME', '23:00')
    BACKUP_RETENTION_DAYS = int(os.environ.get('BACKUP_RETENTION_DAYS', 30))
    BACKUP_FOLDER = os.path.join(basedir, 'backups')

    # Security
    BCRYPT_LOG_ROUNDS = int(os.environ.get('BCRYPT_LOG_ROUNDS', 12))
    LOGIN_ATTEMPTS_LIMIT = int(os.environ.get('LOGIN_ATTEMPTS_LIMIT', 5))
    LOGIN_TIMEOUT_MINUTES = int(os.environ.get('LOGIN_TIMEOUT_MINUTES', 15))

    # CSRF Configuration
    WTF_CSRF_TIME_LIMIT = None  # CSRF token doesn't expire (valid for session lifetime)
    WTF_CSRF_SSL_STRICT = False  # Don't require HTTPS for CSRF
    WTF_CSRF_HEADERS = ['X-CSRFToken', 'X-CSRF-Token']  # Accept token from these headers

    # Logging
    LOG_FOLDER = os.path.join(basedir, 'logs')
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

    # Caching
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'SimpleCache')  # SimpleCache, RedisCache, MemcachedCache
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get('CACHE_DEFAULT_TIMEOUT', 300))  # 5 minutes
    CACHE_REDIS_URL = os.environ.get('CACHE_REDIS_URL', 'redis://localhost:6379/0')

    # Sentry Error Tracking (optional)
    SENTRY_DSN = os.environ.get('SENTRY_DSN', '')

    # WhatsApp Cloud API (FREE - Meta Business Platform)
    # Get these from: https://developers.facebook.com/apps/
    WHATSAPP_PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
    WHATSAPP_ACCESS_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
    WHATSAPP_BUSINESS_ACCOUNT_ID = os.environ.get('WHATSAPP_BUSINESS_ACCOUNT_ID')
    WHATSAPP_VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', 'sunnat_collection_webhook')

    # Twilio (Fallback - paid)
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
    TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER')


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_ECHO = False  # Set to True to see SQL queries


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    # Production should use HTTPS with secure cookies
    # Respect environment variable to allow HTTP in local production setups
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'True').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'  # Lax allows cookies on same-site navigations
    SQLALCHEMY_ECHO = False

    # Additional production security settings
    PREFERRED_URL_SCHEME = 'https' if SESSION_COOKIE_SECURE else 'http'


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
