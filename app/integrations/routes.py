"""
Integration routes for data pipelines
"""
import logging
from flask import Blueprint, jsonify, request
from datetime import datetime

logger = logging.getLogger(__name__)

integrations_bp = Blueprint('integrations', __name__)

@integrations_bp.route('/api/integrations/status')
def integration_status():
    """Get status of all integrations."""
    try:
        integrations = {
            'weather': {'status': 'active', 'last_sync': datetime.utcnow().isoformat()},
            'maritime': {'status': 'active', 'last_sync': datetime.utcnow().isoformat()},
            'aviation': {'status': 'active', 'last_sync': datetime.utcnow().isoformat()},
            'geopolitical': {'status': 'active', 'last_sync': datetime.utcnow().isoformat()},
            'supplier': {'status': 'active', 'last_sync': datetime.utcnow().isoformat()}
        }
        
        return jsonify({
            'integrations': integrations,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting integration status: {e}")
        return jsonify({'error': 'Failed to get integration status'}), 500

@integrations_bp.route('/api/integrations/sync', methods=['POST'])
def trigger_sync():
    """Manually trigger data sync for an integration."""
    try:
        integration_type = request.json.get('type')
        
        if not integration_type:
            return jsonify({'error': 'Integration type required'}), 400
        
        # TODO: Trigger actual sync based on type
        
        return jsonify({
            'success': True,
            'integration': integration_type,
            'message': f'Sync triggered for {integration_type}'
        })
        
    except Exception as e:
        logger.error(f"Error triggering sync: {e}")
        return jsonify({'error': 'Failed to trigger sync'}), 500
