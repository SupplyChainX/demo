"""
Custom decorators for SupplyChainX
"""
from functools import wraps
from flask import jsonify, request, current_app
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
import time

def workspace_required(f):
    """Ensure user has access to workspace."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # For MVP, always use workspace_id=1
        # In production, would check user permissions
        request.workspace_id = 1
        return f(*args, **kwargs)
    return decorated_function

def rate_limit(max_calls, time_window):
    """Rate limiting decorator."""
    def decorator(f):
        calls = {}
        
        @wraps(f)
        def decorated_function(*args, **kwargs):
            now = time.time()
            key = f"{request.remote_addr}:{f.__name__}"
            
            if key not in calls:
                calls[key] = []
            
            # Remove old calls outside time window
            calls[key] = [call for call in calls[key] if call > now - time_window]
            
            if len(calls[key]) >= max_calls:
                return jsonify({'error': 'Rate limit exceeded'}), 429
            
            calls[key].append(now)
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def async_task(f):
    """Mark function as async task for background processing."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # For MVP, execute synchronously
        # In production, would queue to Celery
        return f(*args, **kwargs)
    return decorated_function

def audit_action(action_type):
    """Audit trail decorator."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Log action before execution
            from app.models import AuditLog
            from app import db
            
            # Execute function
            result = f(*args, **kwargs)
            
            # Log to audit trail
            audit = AuditLog(
                workspace_id=getattr(request, 'workspace_id', 1),
                actor_type='user',
                actor_id=str(get_jwt_identity()) if current_app.config.get('AUTH_ENABLED') else 'system',
                action=action_type,
                object_type=f.__name__,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            db.session.add(audit)
            db.session.commit()
            
            return result
        
        return decorated_function
    return decorator

def cache_result(ttl_seconds=300):
    """Simple in-memory cache decorator."""
    def decorator(f):
        cache = {}
        
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Create cache key from function name and arguments
            key = f"{f.__name__}:{str(args)}:{str(kwargs)}"
            now = time.time()
            
            # Check if cached and not expired
            if key in cache:
                result, timestamp = cache[key]
                if now - timestamp < ttl_seconds:
                    return result
            
            # Calculate new result
            result = f(*args, **kwargs)
            cache[key] = (result, now)
            
            # Clean old entries
            for k in list(cache.keys()):
                _, ts = cache[k]
                if now - ts > ttl_seconds:
                    del cache[k]
            
            return result
        
        return decorated_function
    return decorator
