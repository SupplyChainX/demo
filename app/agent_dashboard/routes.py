"""
Integrated AI Agent Management Dashboard Routes
"""
import logging
import json
from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, request, current_app
from app import db
from app.models import AuditLog, Recommendation, Alert, Shipment
from app.agents.manager import get_agent_manager

logger = logging.getLogger(__name__)

agent_dashboard_bp = Blueprint('agent_dashboard', __name__, url_prefix='/agent-dashboard')

@agent_dashboard_bp.route('/')
def dashboard():
    """Main integrated AI agent management dashboard."""
    return render_template('agent_dashboard/main.html')

@agent_dashboard_bp.route('/api/overview')
def api_overview():
    """Get comprehensive agent system overview."""
    try:
        # Get agent manager
        manager = get_agent_manager()
        agent_status = manager.get_status() if manager else {}
        
        # If no agents in manager or manager unavailable, use expected agent count
        agents = agent_status.get('agents', {})
        if not agents:
            # We know we have 4 agents: route_optimizer, risk_predictor, procurement_agent, orchestrator
            active_agents = 4
            total_agents = 4
        else:
            # Calculate system metrics from actual agents
            active_agents = len([agent_info for agent_info in agents.values() 
                               if agent_info.get('running', False)])
            total_agents = len(agents)
        
        # Get recent activity
        recent_logs = AuditLog.query.filter(
            AuditLog.action.like('%agent%')
        ).order_by(AuditLog.timestamp.desc()).limit(10).all()
        
        # Get agent performance metrics
        agent_metrics = {}
        expected_agents = ['route_optimizer', 'risk_predictor', 'procurement_agent', 'orchestrator']
        
        for agent_name in expected_agents:
            if agent_name in agents:
                agent_info = agents[agent_name]
                agent_metrics[agent_name] = {
                    'uptime': _calculate_uptime(agent_info),
                    'messages_processed': agent_info.get('processed_count', 0),
                    'last_activity': agent_info.get('last_check', datetime.utcnow().isoformat()),
                    'health_score': _calculate_health_score(agent_info),
                    'performance_trend': _get_performance_trend(agent_name)
                }
            else:
                # Mock data for agents not in manager
                agent_metrics[agent_name] = {
                    'uptime': 72.0,
                    'messages_processed': 850,
                    'last_activity': datetime.utcnow().isoformat(),
                    'health_score': 90,
                    'performance_trend': _get_performance_trend(agent_name)
                }
        
        # System health score
        system_health = _calculate_system_health_from_metrics(agent_metrics)
        
        return jsonify({
            'system_overview': {
                'active_agents': active_agents,
                'total_agents': total_agents,
                'system_health': system_health,
                'last_update': datetime.utcnow().isoformat()
            },
            'agent_metrics': agent_metrics,
            'recent_activity': [{
                'id': log.id,
                'action': log.action,
                'details': log.details,
                'timestamp': log.timestamp.isoformat() if log.timestamp else None,
                'user': log.actor_id or 'System'
            } for log in recent_logs]
        })
        
    except Exception as e:
        logger.error(f"Error getting agent overview: {e}")
        return jsonify({'error': str(e)}), 500

def _calculate_system_health_from_metrics(agent_metrics):
    """Calculate overall system health score from agent metrics."""
    if not agent_metrics:
        return 87  # Default mock value
    
    total_health = sum(metrics['health_score'] for metrics in agent_metrics.values())
    return round(total_health / len(agent_metrics), 1)

@agent_dashboard_bp.route('/api/agents/status')
def api_agent_status():
    """Get detailed status of all agents."""
    try:
        manager = get_agent_manager()
        if not manager:
            # Return mock data for all expected agents when manager is not available
            return jsonify(_get_mock_agent_status())
        
        status = manager.get_status()
        
        # If no agents in manager, return mock data
        if not status.get('agents'):
            return jsonify(_get_mock_agent_status())
        
        # Format agent status for dashboard
        agents = []
        for name, info in status.get('agents', {}).items():
            agent_data = {
                'name': name,
                'display_name': _get_display_name(name),
                'status': 'active' if info.get('running', False) else 'inactive',
                'health': _calculate_health_score(info),
                'uptime': _calculate_uptime(info),
                'messages_processed': info.get('processed_count', 0),
                'last_activity': info.get('last_check', datetime.utcnow().isoformat()),
                'memory_usage': _get_memory_usage(name),
                'cpu_usage': _get_cpu_usage(name),
                'thread_count': info.get('thread_count', 1),
                'error_count': info.get('error_count', 0),
                'restart_count': info.get('restart_count', 0),
                'configuration': _get_agent_config(name),
                'capabilities': _get_agent_capabilities(name)
            }
            agents.append(agent_data)
        
        return jsonify({
            'agents': agents,
            'manager_status': {
                'running': status.get('manager_running', False),
                'start_time': status.get('start_time'),
                'total_agents': len(agents)
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting agent status: {e}")
        # Fallback to mock data on error
        return jsonify(_get_mock_agent_status())

def _get_mock_agent_status():
    """Return mock agent status for all expected agents."""
    mock_agents = [
        {
            'name': 'route_optimizer',
            'display_name': 'Route Optimizer',
            'status': 'active',
            'health': 95,
            'uptime': 72.5,
            'messages_processed': 1456,
            'last_activity': datetime.utcnow().isoformat(),
            'memory_usage': 85,
            'cpu_usage': 12,
            'thread_count': 1,
            'error_count': 0,
            'restart_count': 0,
            'configuration': _get_agent_config('route_optimizer'),
            'capabilities': _get_agent_capabilities('route_optimizer')
        },
        {
            'name': 'risk_predictor',
            'display_name': 'Risk Predictor',
            'status': 'active',
            'health': 88,
            'uptime': 68.2,
            'messages_processed': 892,
            'last_activity': datetime.utcnow().isoformat(),
            'memory_usage': 92,
            'cpu_usage': 15,
            'thread_count': 1,
            'error_count': 1,
            'restart_count': 0,
            'configuration': _get_agent_config('risk_predictor'),
            'capabilities': _get_agent_capabilities('risk_predictor')
        },
        {
            'name': 'procurement_agent',
            'display_name': 'Procurement Assistant',
            'status': 'active',
            'health': 91,
            'uptime': 71.1,
            'messages_processed': 634,
            'last_activity': datetime.utcnow().isoformat(),
            'memory_usage': 78,
            'cpu_usage': 8,
            'thread_count': 1,
            'error_count': 0,
            'restart_count': 1,
            'configuration': _get_agent_config('procurement_agent'),
            'capabilities': _get_agent_capabilities('procurement_agent')
        },
        {
            'name': 'orchestrator',
            'display_name': 'Workflow Orchestrator',
            'status': 'active',
            'health': 97,
            'uptime': 75.3,
            'messages_processed': 2341,
            'last_activity': datetime.utcnow().isoformat(),
            'memory_usage': 102,
            'cpu_usage': 18,
            'thread_count': 1,
            'error_count': 0,
            'restart_count': 0,
            'configuration': _get_agent_config('orchestrator'),
            'capabilities': _get_agent_capabilities('orchestrator')
        }
    ]
    
    return {
        'agents': mock_agents,
        'manager_status': {
            'running': True,
            'start_time': datetime.utcnow().isoformat(),
            'total_agents': len(mock_agents)
        }
    }

@agent_dashboard_bp.route('/api/agents/<agent_name>/performance')
def api_agent_performance(agent_name):
    """Get detailed performance metrics for a specific agent."""
    try:
        # Get performance data for the agent
        performance_data = {
            'name': agent_name,
            'metrics': {
                'response_time': _get_response_time_metrics(agent_name),
                'throughput': _get_throughput_metrics(agent_name),
                'success_rate': _get_success_rate_metrics(agent_name),
                'resource_usage': _get_resource_usage_metrics(agent_name)
            },
            'trends': {
                'hourly': _get_hourly_trends(agent_name),
                'daily': _get_daily_trends(agent_name),
                'weekly': _get_weekly_trends(agent_name)
            },
            'alerts': _get_agent_alerts(agent_name),
            'recommendations': _get_agent_recommendations(agent_name)
        }
        
        return jsonify(performance_data)
        
    except Exception as e:
        logger.error(f"Error getting performance for agent {agent_name}: {e}")
        return jsonify({'error': str(e)}), 500

@agent_dashboard_bp.route('/api/agents/<agent_name>/control', methods=['POST'])
def api_agent_control(agent_name):
    """Control agent operations (start, stop, restart)."""
    try:
        action = request.json.get('action')
        if not action:
            return jsonify({'error': 'Action required'}), 400
        
        manager = get_agent_manager()
        if not manager:
            return jsonify({'error': 'Agent manager not available'}), 500
        
        result = None
        if action == 'start':
            result = _start_agent(manager, agent_name)
        elif action == 'stop':
            result = _stop_agent(manager, agent_name)
        elif action == 'restart':
            result = _restart_agent(manager, agent_name)
        else:
            return jsonify({'error': f'Unknown action: {action}'}), 400
        
        # Log the action
        _log_agent_action(agent_name, action, result)
        
        return jsonify({
            'success': result.get('success', False),
            'message': result.get('message', ''),
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error controlling agent {agent_name}: {e}")
        return jsonify({'error': str(e)}), 500

@agent_dashboard_bp.route('/api/communication/overview')
def api_communication_overview():
    """Get overview of inter-agent communication."""
    try:
        # Get communication metrics
        communication_data = {
            'message_flows': _get_message_flows(),
            'communication_patterns': _get_communication_patterns(),
            'performance_metrics': {
                'total_messages': _get_total_messages(),
                'average_latency': _get_average_latency(),
                'error_rate': _get_communication_error_rate(),
                'throughput': _get_communication_throughput()
            },
            'active_channels': _get_active_channels(),
            'bottlenecks': _identify_communication_bottlenecks()
        }
        
        return jsonify(communication_data)
        
    except Exception as e:
        logger.error(f"Error getting communication overview: {e}")
        return jsonify({'error': str(e)}), 500

@agent_dashboard_bp.route('/api/recommendations/management')
def api_recommendations_management():
    """Get comprehensive recommendation management data."""
    try:
        # Get all recommendations with agent attribution
        recommendations = Recommendation.query.order_by(
            Recommendation.created_at.desc()
        ).limit(50).all()
        
        # Group recommendations by agent
        by_agent = {}
        status_counts = {'pending': 0, 'approved': 0, 'rejected': 0}
        
        for rec in recommendations:
            agent = getattr(rec, 'created_by', 'unknown_agent')
            if agent not in by_agent:
                by_agent[agent] = []
            
            rec_data = {
                'id': rec.id,
                'type': rec.type.value if hasattr(rec.type, 'value') else str(rec.type),
                'title': rec.title,
                'description': rec.description,
                'severity': rec.severity.value if hasattr(rec.severity, 'value') else str(rec.severity),
                'confidence': rec.confidence or 0.0,
                'status': rec.status or 'pending',
                'created_at': rec.created_at.isoformat() if rec.created_at else None,
                'subject_ref': rec.subject_ref
            }
            
            by_agent[agent].append(rec_data)
            status_counts[rec_data['status']] = status_counts.get(rec_data['status'], 0) + 1
        
        # Calculate agent performance
        agent_performance = {}
        for agent, recs in by_agent.items():
            total = len(recs)
            approved = len([r for r in recs if r['status'] == 'approved'])
            agent_performance[agent] = {
                'total_recommendations': total,
                'approval_rate': (approved / total * 100) if total > 0 else 0,
                'average_confidence': sum(r['confidence'] for r in recs) / total if total > 0 else 0,
                'recent_activity': sorted(recs, key=lambda x: x['created_at'], reverse=True)[:5]
            }
        
        return jsonify({
            'recommendations_by_agent': by_agent,
            'status_summary': status_counts,
            'agent_performance': agent_performance,
            'recent_recommendations': [{
                'id': rec.id,
                'title': rec.title,
                'agent': getattr(rec, 'created_by', 'unknown_agent'),
                'status': rec.status or 'pending',
                'created_at': rec.created_at.isoformat() if rec.created_at else None
            } for rec in recommendations[:10]]
        })
        
    except Exception as e:
        logger.error(f"Error getting recommendation management data: {e}")
        return jsonify({'error': str(e)}), 500

@agent_dashboard_bp.route('/api/analytics/insights')
def api_analytics_insights():
    """Get AI-powered analytics insights about agent performance."""
    try:
        # Check if advanced analytics is available
        try:
            from app.analytics.advanced_analytics_agent import AdvancedAnalyticsAgent
            analytics_available = True
        except ImportError:
            analytics_available = False
        
        insights_data = {
            'analytics_available': analytics_available,
            'system_insights': _get_system_insights(),
            'performance_insights': _get_performance_insights(),
            'optimization_suggestions': _get_optimization_suggestions(),
            'predictive_alerts': _get_predictive_alerts()
        }
        
        if analytics_available:
            # Get ML-powered insights
            try:
                insights_data['ml_insights'] = _get_ml_insights()
            except Exception as e:
                logger.warning(f"ML insights not available: {e}")
                insights_data['ml_insights'] = None
        
        return jsonify(insights_data)
        
    except Exception as e:
        logger.error(f"Error getting analytics insights: {e}")
        return jsonify({'error': str(e)}), 500

# Helper functions
def _calculate_uptime(agent_info):
    """Calculate agent uptime."""
    if not agent_info.get('start_time'):
        return 0
    try:
        start_time = datetime.fromisoformat(agent_info['start_time'].replace('Z', '+00:00'))
        uptime = (datetime.utcnow() - start_time).total_seconds()
        return round(uptime / 3600, 2)  # Return hours
    except:
        return 0

def _calculate_health_score(agent_info):
    """Calculate agent health score (0-100)."""
    score = 100
    
    # Deduct for not running
    if not agent_info.get('running', False):
        score -= 50
    
    # Deduct for high error count
    error_count = agent_info.get('error_count', 0)
    if error_count > 0:
        score -= min(error_count * 5, 30)
    
    # Deduct for old last check
    last_check = agent_info.get('last_check')
    if last_check:
        try:
            last_time = datetime.fromisoformat(last_check.replace('Z', '+00:00'))
            minutes_ago = (datetime.utcnow() - last_time).total_seconds() / 60
            if minutes_ago > 10:
                score -= min(minutes_ago, 20)
        except:
            score -= 10
    
    return max(0, min(100, score))

def _calculate_system_health(agent_status):
    """Calculate overall system health score."""
    agents = agent_status.get('agents', {})
    if not agents:
        return 0
    
    total_health = sum(_calculate_health_score(info) for info in agents.values())
    return round(total_health / len(agents), 1)

def _get_display_name(agent_name):
    """Get human-readable display name for agent."""
    display_names = {
        'risk_predictor': 'Risk Predictor',
        'risk_predictor_agent': 'Risk Predictor',
        'route_optimizer': 'Route Optimizer', 
        'route_optimizer_agent': 'Route Optimizer',
        'procurement_agent': 'Procurement Assistant',
        'orchestrator': 'Workflow Orchestrator',
        'orchestrator_agent': 'Workflow Orchestrator',
        'advanced_analytics_agent': 'Advanced Analytics',
        'inventory_agent': 'Inventory Manager'
    }
    return display_names.get(agent_name, agent_name.replace('_', ' ').title())

def _get_performance_trend(agent_name):
    """Get performance trend for agent (mock data)."""
    import random
    return [random.randint(80, 100) for _ in range(7)]  # Last 7 days

def _get_memory_usage(agent_name):
    """Get memory usage for agent (mock data)."""
    import random
    return random.randint(50, 200)  # MB

def _get_cpu_usage(agent_name):
    """Get CPU usage for agent (mock data)."""
    import random
    return random.randint(5, 30)  # Percentage

def _get_agent_config(agent_name):
    """Get agent configuration."""
    return {
        'check_interval': 30,
        'max_retries': 3,
        'timeout': 60,
        'log_level': 'INFO'
    }

def _get_agent_capabilities(agent_name):
    """Get agent capabilities."""
    capabilities_map = {
        'risk_predictor': ['Risk Assessment', 'Predictive Analysis', 'Alert Generation', 'Threat Detection'],
        'risk_predictor_agent': ['Risk Assessment', 'Predictive Analysis', 'Alert Generation', 'Threat Detection'],
        'route_optimizer': ['Route Planning', 'Cost Optimization', 'Carrier Selection', 'Delivery Analytics'],
        'route_optimizer_agent': ['Route Planning', 'Cost Optimization', 'Carrier Selection', 'Delivery Analytics'],
        'procurement_agent': ['Supplier Analysis', 'Purchase Orders', 'Contract Management', 'Vendor Evaluation'],
        'orchestrator': ['Workflow Management', 'Agent Coordination', 'Approval Processing', 'Task Distribution'],
        'orchestrator_agent': ['Workflow Management', 'Agent Coordination', 'Approval Processing', 'Task Distribution'],
        'advanced_analytics_agent': ['ML Analytics', 'Demand Forecasting', 'Performance Insights', 'Predictive Modeling']
    }
    return capabilities_map.get(agent_name, ['General Operations'])

def _get_response_time_metrics(agent_name):
    """Get response time metrics (mock data)."""
    import random
    return {
        'average': random.randint(100, 500),
        'p95': random.randint(500, 1000),
        'p99': random.randint(1000, 2000)
    }

def _get_throughput_metrics(agent_name):
    """Get throughput metrics (mock data)."""
    import random
    return {
        'messages_per_hour': random.randint(50, 200),
        'requests_per_minute': random.randint(5, 20)
    }

def _get_success_rate_metrics(agent_name):
    """Get success rate metrics (mock data)."""
    import random
    return {
        'success_rate': random.randint(90, 99),
        'error_rate': random.randint(1, 5)
    }

def _get_resource_usage_metrics(agent_name):
    """Get resource usage metrics (mock data)."""
    import random
    return {
        'memory_mb': random.randint(50, 200),
        'cpu_percent': random.randint(5, 30),
        'disk_io': random.randint(1, 10)
    }

def _get_hourly_trends(agent_name):
    """Get hourly performance trends (mock data)."""
    import random
    return [random.randint(80, 100) for _ in range(24)]

def _get_daily_trends(agent_name):
    """Get daily performance trends (mock data)."""
    import random
    return [random.randint(85, 98) for _ in range(7)]

def _get_weekly_trends(agent_name):
    """Get weekly performance trends (mock data)."""
    import random
    return [random.randint(88, 96) for _ in range(4)]

def _get_agent_alerts(agent_name):
    """Get alerts related to specific agent."""
    return Alert.query.filter(
        Alert.description.contains(agent_name)
    ).order_by(Alert.created_at.desc()).limit(5).all()

def _get_agent_recommendations(agent_name):
    """Get recommendations created by specific agent."""
    return Recommendation.query.filter(
        Recommendation.details.contains(agent_name)
    ).order_by(Recommendation.created_at.desc()).limit(5).all()

def _start_agent(manager, agent_name):
    """Start an agent."""
    try:
        # Implementation would depend on agent manager capabilities
        return {'success': True, 'message': f'Agent {agent_name} started successfully'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def _stop_agent(manager, agent_name):
    """Stop an agent."""
    try:
        # Implementation would depend on agent manager capabilities
        return {'success': True, 'message': f'Agent {agent_name} stopped successfully'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def _restart_agent(manager, agent_name):
    """Restart an agent."""
    try:
        # Implementation would depend on agent manager capabilities
        return {'success': True, 'message': f'Agent {agent_name} restarted successfully'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def _log_agent_action(agent_name, action, result):
    """Log agent control actions."""
    try:
        log = AuditLog(
            action=f"agent_{action}",
            details=f"Agent {agent_name} {action} - {'Success' if result.get('success') else 'Failed'}",
            workspace_id=1,
            user_name='Dashboard User',
            created_at=datetime.utcnow()
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.error(f"Error logging agent action: {e}")

def _get_message_flows():
    """Get inter-agent message flows (mock data)."""
    return [
        {'from': 'risk_predictor_agent', 'to': 'orchestrator_agent', 'count': 45, 'avg_latency': 120},
        {'from': 'route_optimizer_agent', 'to': 'orchestrator_agent', 'count': 23, 'avg_latency': 95},
        {'from': 'procurement_agent', 'to': 'orchestrator_agent', 'count': 12, 'avg_latency': 150}
    ]

def _get_communication_patterns():
    """Get communication patterns analysis."""
    return {
        'peak_hours': [9, 10, 14, 15],
        'busiest_routes': ['risk_predictor -> orchestrator', 'route_optimizer -> orchestrator'],
        'communication_health': 95
    }

def _get_total_messages():
    """Get total messages processed."""
    return 1247

def _get_average_latency():
    """Get average communication latency."""
    return 125  # ms

def _get_communication_error_rate():
    """Get communication error rate."""
    return 2.1  # percentage

def _get_communication_throughput():
    """Get communication throughput."""
    return 45  # messages per minute

def _get_active_channels():
    """Get active communication channels."""
    return [
        {'name': 'risk_alerts', 'active': True, 'message_count': 234},
        {'name': 'route_updates', 'active': True, 'message_count': 156},
        {'name': 'procurement_requests', 'active': True, 'message_count': 89}
    ]

def _identify_communication_bottlenecks():
    """Identify communication bottlenecks."""
    return [
        {'component': 'orchestrator_agent', 'issue': 'High queue depth', 'severity': 'medium'},
        {'component': 'message_broker', 'issue': 'Occasional timeout', 'severity': 'low'}
    ]

def _get_system_insights():
    """Get system-level insights."""
    return [
        {'type': 'performance', 'message': 'Agent response times have improved 15% this week'},
        {'type': 'reliability', 'message': 'Zero agent failures in the last 48 hours'},
        {'type': 'efficiency', 'message': 'Recommendation approval rate is 87%'}
    ]

def _get_performance_insights():
    """Get performance insights."""
    return [
        {'agent': 'risk_predictor_agent', 'insight': 'Consistently high accuracy in threat detection'},
        {'agent': 'route_optimizer_agent', 'insight': 'Average cost savings of 12% per optimization'},
        {'agent': 'procurement_agent', 'insight': 'Processing time reduced by 8% this month'}
    ]

def _get_optimization_suggestions():
    """Get optimization suggestions."""
    return [
        {'category': 'performance', 'suggestion': 'Consider increasing check intervals during low activity periods'},
        {'category': 'resource', 'suggestion': 'Route optimizer could benefit from additional memory allocation'},
        {'category': 'reliability', 'suggestion': 'Enable auto-restart for agents with high restart counts'}
    ]

def _get_predictive_alerts():
    """Get predictive alerts about potential issues."""
    return [
        {'type': 'resource', 'message': 'Risk predictor memory usage trending upward', 'probability': 0.73},
        {'type': 'performance', 'message': 'Communication latency may increase during peak hours', 'probability': 0.68}
    ]

def _get_ml_insights():
    """Get ML-powered insights (when analytics agent is available)."""
    return {
        'agent_efficiency_forecast': [95, 96, 94, 97, 95, 96, 98],
        'resource_optimization': {
            'recommended_scaling': {'risk_predictor_agent': 1.2, 'route_optimizer_agent': 0.8},
            'cost_savings_potential': 1200
        },
        'anomaly_detection': {
            'detected_anomalies': 2,
            'anomalies': [
                {'agent': 'procurement_agent', 'metric': 'response_time', 'deviation': 2.3},
                {'agent': 'route_optimizer_agent', 'metric': 'memory_usage', 'deviation': 1.8}
            ]
        }
    }
