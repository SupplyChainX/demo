"""
Enhanced AI Assistant Demo Route
"""
from flask import Blueprint, render_template, current_app
import logging

logger = logging.getLogger(__name__)

# Create blueprint for enhanced assistant demo
demo_bp = Blueprint('enhanced_assistant_demo', __name__)

@demo_bp.route('/enhanced-assistant-demo')
def demo_page():
    """
    Demo page showcasing the enhanced AI assistant capabilities
    """
    try:
        return render_template('enhanced_assistant_demo.html')
    except Exception as e:
        logger.error(f"Error rendering enhanced assistant demo: {e}")
        return f"Error loading demo page: {str(e)}", 500

@demo_bp.route('/enhanced-assistant-embed')
def embed_demo():
    """
    Embeddable version of the enhanced assistant for integration testing
    """
    try:
        return render_template('enhanced_assistant_embed.html')
    except Exception as e:
        logger.error(f"Error rendering enhanced assistant embed: {e}")
        return f"Error loading embed demo: {str(e)}", 500
