"""Settings per environment. Secrets come from .env, never from this file."""
import os
from dotenv import load_dotenv

load_dotenv(override=True)


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', '')
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False
    TESTING = False


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = 'test-only-secret'


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True


config_by_name = {'development': DevelopmentConfig, 'testing': TestingConfig,
                  'production': ProductionConfig}