"""
SupplyChainX Application Factory
"""
import os
import logging
from flask import Flask, request, jsonify, render_template
from flask_socketio import emit
from flask_cors import CORS
from redis import Redis
from dotenv import load_dotenv

# Import extensions from the extensions module
from app.extensions import db, socketio, login_manager, migrate

# Initialize Redis client
redis_client = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from app.config import config

def create_app(config_name='development'):
    """Application factory"""
    # Load environment variables from .env before reading config
    try:
        load_dotenv()
    except Exception:
        pass
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Register custom Jinja2 filters
    @app.template_filter('date')
    def date_filter(value, format='%b %d, %Y'):
        """Format a date using the given format."""
        if value is None:
            return ""
        if isinstance(value, str):
            try:
                from datetime import datetime
                value = datetime.fromisoformat(value)
            except:
                return value
        return value.strftime(format)
    
    @app.template_filter('risk_color')
    def risk_color_filter(value):
        """Convert risk level to Bootstrap color class."""
        if not value:
            return 'secondary'
        value = value.lower()
        if value == 'critical' or value == 'high':
            return 'danger'
        elif value == 'medium':
            return 'warning'
        elif value == 'low':
            return 'success'
        return 'secondary'
        
    @app.template_filter('status_color')
    def status_color_filter(value):
        """Convert shipment status to Bootstrap color class."""
        if not value:
            return 'secondary'
        value = str(value).lower()
        status_colors = {
            'planned': 'info',
            'booked': 'primary',
            'in_transit': 'primary',
            'delayed': 'warning',
            'arrived': 'success',
            'delivered': 'success',
            'cancelled': 'danger',
            'pending': 'secondary',
            'customs_hold': 'warning',
            'port_delay': 'warning',
            'loading': 'info',
            'unloading': 'info',
            'completed': 'success'
        }
        return status_colors.get(value, 'secondary')
    
    # Initialize extensions
    db.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    # Initialize CORS if needed
    if app.config.get('CORS_ENABLED', False):
        CORS(app)
    
    # Initialize Redis
    global redis_client
    from app.utils.redis_manager import RedisManager
    redis_client = RedisManager()
    
    # Configure login manager
    @login_manager.user_loader
    def load_user(user_id):
            # Import here to avoid circular dependencies on initialization
            from app.models import User
            return db.session.get(User, int(user_id))
    
    # Register blueprints
    from app.main.routes import main_bp
    from app.api import api_bp
    from app.agents.routes import agents_bp
    from app.integrations.routes import integrations_bp
    from app.auth.routes import auth_bp
    from app.agent_dashboard import agent_dashboard_bp
    from app.api.smart_assistant_routes import assistant_bp
    from app.routes.enhanced_assistant_demo import demo_bp
    from app.api.analytics_routes import analytics_bp
    # from app.api.policies_routes import policies_bp  # Disabled in favor of new Policy APIs
    from app.api.realtime_routes import realtime_bp
    from app.api.notifications_routes import notifications_bp
    
    app.register_blueprint(main_bp)
    # Register REST API blueprint under /api
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(agents_bp, url_prefix='/agents')
    app.register_blueprint(integrations_bp, url_prefix='/integrations')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(agent_dashboard_bp, url_prefix='/agent-dashboard')
    app.register_blueprint(assistant_bp)
    app.register_blueprint(demo_bp)
    # Register Phase 2 blueprints
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    # Note: Disabled old policy system in favor of new comprehensive Policy APIs in main routes
    # app.register_blueprint(policies_bp, url_prefix='/api/policies')
    # Register Phase 5 real-time blueprint
    app.register_blueprint(realtime_bp, url_prefix='/api/realtime')
    # Register notifications blueprint
    app.register_blueprint(notifications_bp)
    
    # Create database tables within app context
    # Ensure models are imported so SQLAlchemy is aware of them
    from app import models
    with app.app_context():
        db.create_all()
        logger.info("Database tables created")
    
    # Initialize background tasks
    if not app.config.get('TESTING', False):
        with app.app_context():
            # Enable all background loops for full AI automation
            from app.background import start_all_background_loops
            # Start background loops after app is ready
            import threading
            threading.Thread(target=start_all_background_loops, args=(app,), daemon=True).start()
            logger.info("Background loops initialization started")
    
    # Socket.IO event handlers
    @socketio.on('connect')
    def handle_connect():
        logger.info(f"Client connected: {request.sid}")
        emit('connected', {'data': 'Connected to SupplyChainX'})
    
    @socketio.on('disconnect')
    def handle_disconnect():
        logger.info(f"Client disconnected: {request.sid}")
    
    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Not found'}), 404
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Internal server error'}), 500
        return render_template('errors/500.html'), 500
    
    # Initialize agents (now that reloader is disabled, we can safely start agents)
    if not app.config.get('TESTING', False):
        init_agents(app)
    
    return app

def init_agents(app):
    """Initialize AI agents"""
    try:
        from app.agents.manager import get_agent_manager
        
        # Start agents in a separate thread to avoid blocking app startup
        def start_agents():
            with app.app_context():
                manager = get_agent_manager(app=app)
                manager.start()
        
        import threading
        agent_thread = threading.Thread(target=start_agents, daemon=True)
        agent_thread.start()
        
        app.logger.info("AI Agents initialization started")
        
    except Exception as e:
        app.logger.error(f"Failed to initialize agents: {e}")

def register_socketio_events():
    """Register Socket.IO event handlers."""
    
    @socketio.on('connect')
    def handle_connect():
        logger.info('Client connected')
    
    @socketio.on('disconnect')
    def handle_disconnect():
        logger.info('Client disconnected')
    
    @socketio.on('message')
    def handle_message(data):
        logger.info(f'Received message: {data}')
        # Echo back for now
        socketio.emit('message_response', {'echo': data})

def start_background_loops(app):
    """Start all background processing loops."""
    try:
        from app.background import (
            start_outbox_publisher,
            start_ui_bridge,
            start_risk_predictor_loop,
            start_route_optimizer_loop,
            start_procurement_agent_loop,
            start_orchestrator_loop
        )
        
        import threading
        
        logger.info("Starting background loops...")
        
        # Start outbox publisher
        threading.Thread(
            target=start_outbox_publisher,
            args=(app,),
            daemon=True,
            name='outbox-publisher'
        ).start()
        
        # Start UI bridge
        threading.Thread(
            target=start_ui_bridge,
            args=(app,),
            daemon=True,
            name='ui-bridge'
        ).start()
        
        # Start agent loops
        threading.Thread(
            target=start_risk_predictor_loop,
            args=(app,),
            daemon=True,
            name='risk-predictor'
        ).start()
        
        threading.Thread(
            target=start_route_optimizer_loop,
            args=(app,),
            daemon=True,
            name='route-optimizer'
        ).start()
        
        threading.Thread(
            target=start_procurement_agent_loop,
            args=(app,),
            daemon=True,
            name='procurement-agent'
        ).start()
        
        threading.Thread(
            target=start_orchestrator_loop,
            args=(app,),
            daemon=True,
            name='orchestrator'
        ).start()
        
        logger.info("All background loops started")
        
    except ImportError as e:
        logger.warning(f"Background loops not available: {e}")

# Import models and blueprints after app is created to avoid circular imports
from app import models
from app.main.routes import main_bp

# End of file
