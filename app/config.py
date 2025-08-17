"""
Application configuration
"""
import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Base configuration."""
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # SQLAlchemy
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, '..', 'instance', 'supplychain.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'connect_args': {
            'check_same_thread': False,
            'timeout': 30
        }
    }
    
    # Redis
    REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
    REDIS_DB = int(os.environ.get('REDIS_DB', 0))
    REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD')
    
    # IBM watsonx.ai (support both legacy and current env var spellings)
    # Some .env files may provide WATSONX_APIKEY / WATSONX_API_URL (without second underscore)
    WATSONX_API_KEY = os.environ.get('WATSONX_API_KEY') or os.environ.get('WATSONX_APIKEY')
    WATSONX_PROJECT_ID = os.environ.get('WATSONX_PROJECT_ID')
    WATSONX_URL = os.environ.get('WATSONX_URL') or os.environ.get('WATSONX_API_URL', 'https://us-south.ml.cloud.ibm.com')
    WATSONX_MODEL_ID = os.environ.get('GRANITE_INSTRUCT_MODEL', 'ibm/granite-3-8b-instruct')
    
    # External APIs
    OPENROUTESERVICE_API_KEY = os.environ.get('OPENROUTESERVICE_API_KEY')
    OSRM_BASE_URL = os.environ.get('OSRM_BASE_URL', 'http://router.project-osrm.org')
    NEWS_API_KEY = os.environ.get('NEWS_API_KEY')
    COMPANIES_HOUSE_API_KEY = os.environ.get('COMPANIES_HOUSE_API_KEY')
    # Carrier APIs
    MAERSK_API_KEY = os.environ.get('MAERSK_API_KEY')
    
    # Agent Configuration
    RISK_PREDICTOR_INTERVAL = int(os.environ.get('RISK_PREDICTOR_INTERVAL', 300))  # 5 minutes
    ROUTE_OPTIMIZER_INTERVAL = int(os.environ.get('ROUTE_OPTIMIZER_INTERVAL', 600))  # 10 minutes
    PROCUREMENT_AGENT_INTERVAL = int(os.environ.get('PROCUREMENT_AGENT_INTERVAL', 900))  # 15 minutes
    ORCHESTRATOR_INTERVAL = int(os.environ.get('ORCHESTRATOR_INTERVAL', 60))  # 1 minute
    
    # Business Rules
    INVENTORY_THRESHOLD_DAYS = int(os.environ.get('INVENTORY_THRESHOLD_DAYS', 10))
    HIGH_VALUE_THRESHOLD = float(os.environ.get('HIGH_VALUE_THRESHOLD', 75000))
    RISK_SCORE_HIGH = float(os.environ.get('RISK_SCORE_HIGH', 0.7))
    RISK_SCORE_MEDIUM = float(os.environ.get('RISK_SCORE_MEDIUM', 0.4))
    # Automatic reroute recommendation trigger threshold
    REROUTE_RISK_THRESHOLD = float(os.environ.get('REROUTE_RISK_THRESHOLD', 0.75))
    
    # CORS
    ENABLE_CORS = os.environ.get('ENABLE_CORS', 'false').lower() == 'true'
    
    # Session
    SESSION_TYPE = 'filesystem'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # File Upload
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = os.path.join(basedir, '..', 'uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'csv', 'xlsx'}

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    TESTING = False
    
class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    TESTING = False
    
    # Override with production values
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    
    # Security
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    # Keep attributes available after commit to avoid DetachedInstanceError in tests
    SQLALCHEMY_EXPIRE_ON_COMMIT = False
    # Flask-SQLAlchemy 3.x uses session options for expire_on_commit
    SQLALCHEMY_SESSION_OPTIONS = {'expire_on_commit': False}

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}