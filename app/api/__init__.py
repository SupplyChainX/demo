"""
API Blueprint - RESTful endpoints
"""
from flask import Blueprint

api_bp = Blueprint('api', __name__)

# Import all route modules to register them
from app.api import routes
from app.api import reports_routes
from app.api import approvals_routes
