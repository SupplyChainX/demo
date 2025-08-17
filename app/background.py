"""
Background processing loops for agents and messaging
"""
import logging
import time
import json
import os
from datetime import datetime
from flask import current_app
from app import db, socketio, redis_client
from app.models import Outbox, OutboxStatus

logger = logging.getLogger(__name__)

def outbox_publisher_loop(app):
    """Publish outbox messages to Redis streams"""
    from app.agents.communicator import AgentCommunicator
    
    communicator = AgentCommunicator()
    
    logger.info("Starting Outbox Publisher loop")
    
    while True:
        try:
            with app.app_context():
                # Fetch unprocessed outbox messages
                messages = Outbox.query.filter_by(
                    status='pending'
                ).order_by(Outbox.created_at).limit(100).all()
                
                for message in messages:
                    try:
                        # Publish to appropriate stream
                        communicator.publish_message(
                            message.stream_name,
                            message.payload
                        )
                        
                        # Mark as processed
                        message.status = 'processed'
                        message.processed_at = datetime.utcnow()
                        
                    except Exception as e:
                        logger.error(f"Failed to publish message {message.id}: {str(e)}")
                        message.status = 'failed'
                        message.error = str(e)
                    
                if messages:
                    db.session.commit()
                    
        except Exception as e:
            logger.error(f"Outbox publisher error: {str(e)}")
            
        time.sleep(1)  # Check every second

def start_risk_predictor_loop(app):
    """Start the Risk Predictor Agent background loop"""
    from app.agents.risk_predictor import RiskPredictorAgent
    
    agent = RiskPredictorAgent()
    interval = int(os.getenv('RISK_PREDICTOR_INTERVAL', '300'))  # 5 minutes default
    
    logger.info("Starting Risk Predictor Agent loop")
    
    while True:
        try:
            with app.app_context():
                agent.run_cycle()
        except Exception as e:
            logger.error(f"Risk Predictor Agent error: {str(e)}")
        
        time.sleep(interval)

def start_route_optimizer_loop(app):
    """Start the Route Optimizer Agent background loop"""
    from app.agents.route_optimizer import RouteOptimizerAgent
    
    agent = RouteOptimizerAgent()
    interval = int(os.getenv('ROUTE_OPTIMIZER_INTERVAL', '600'))  # 10 minutes default
    
    logger.info("Starting Route Optimizer Agent loop")
    
    while True:
        try:
            with app.app_context():
                agent.run_cycle()
        except Exception as e:
            logger.error(f"Route Optimizer Agent error: {str(e)}")
        
        time.sleep(interval)

def start_procurement_agent_loop(app):
    """Start the Procurement Agent background loop"""
    from app.agents.procurement_agent import ProcurementAgent
    
    agent = ProcurementAgent()
    interval = int(os.getenv('PROCUREMENT_AGENT_INTERVAL', '900'))  # 15 minutes default
    
    logger.info("Starting Procurement Agent loop")
    
    while True:
        try:
            with app.app_context():
                agent.run_cycle()
        except Exception as e:
            logger.error(f"Procurement Agent error: {str(e)}")
        
        time.sleep(interval)

def start_orchestrator_loop(app):
    """Start the Orchestrator Agent background loop"""
    from app.agents.orchestrator import OrchestratorAgent
    
    agent = OrchestratorAgent()
    interval = int(os.getenv('ORCHESTRATOR_INTERVAL', '60'))  # 1 minute default
    
    logger.info("Starting Orchestrator Agent loop")
    
    while True:
        try:
            with app.app_context():
                agent.run_cycle()
        except Exception as e:
            logger.error(f"Orchestrator Agent error: {str(e)}")
        
        time.sleep(interval)

def ui_bridge_loop(app):
    """Bridge Redis pub/sub to Socket.IO"""
    import redis
    import json
    
    r = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379'))
    pubsub = r.pubsub()
    pubsub.subscribe('ui.broadcast')
    
    logger.info("Starting UI Bridge loop")
    
    for message in pubsub.listen():
        try:
            if message['type'] == 'message':
                data = json.loads(message['data'])
                
                # Emit to appropriate Socket.IO event
                event_type = data.get('event', 'update')
                
                with app.app_context():
                    socketio.emit(event_type, data, namespace='/')
                    
        except Exception as e:
            logger.error(f"UI Bridge error: {str(e)}")

def start_all_background_loops(app):
    """Start all background loops"""
    from threading import Thread
    
    # Outbox Publisher
    outbox_thread = Thread(target=outbox_publisher_loop, args=(app,), daemon=True)
    outbox_thread.start()
    
    # Risk Predictor Agent
    risk_thread = Thread(target=start_risk_predictor_loop, args=(app,), daemon=True)
    risk_thread.start()
    
    # Route Optimizer Agent
    route_thread = Thread(target=start_route_optimizer_loop, args=(app,), daemon=True)
    route_thread.start()
    
    # Procurement Agent
    procurement_thread = Thread(target=start_procurement_agent_loop, args=(app,), daemon=True)
    procurement_thread.start()
    
    # Orchestrator Agent
    orchestrator_thread = Thread(target=start_orchestrator_loop, args=(app,), daemon=True)
    orchestrator_thread.start()
    
    # UI Bridge
    ui_thread = Thread(target=ui_bridge_loop, args=(app,), daemon=True)
    ui_thread.start()
    
    logger.info("All background loops started")

def start_outbox_publisher(app):
    """Publish outbox events to Redis streams."""
    logger.info("Starting outbox publisher")
    
    with app.app_context():
        while True:
            try:
                # Get pending outbox entries
                pending = Outbox.query.filter_by(
                    status=OutboxStatus.PENDING
                ).order_by(Outbox.created_at).limit(100).all()
                
                for entry in pending:
                    try:
                        # Publish to Redis stream
                        stream_name = entry.stream_name
                        message_id = redis_client.xadd(
                            stream_name,
                            {
                                'event_type': entry.event_type,
                                'aggregate_type': entry.aggregate_type or '',
                                'aggregate_id': entry.aggregate_id or '',
                                'event_data': json.dumps(entry.event_data) if entry.event_data else '{}',
                                'created_at': entry.created_at.isoformat()
                            }
                        )
                        
                        # Update outbox entry
                        entry.status = OutboxStatus.PUBLISHED
                        entry.published_at = datetime.utcnow()
                        
                        logger.debug(f"Published {entry.event_type} to {stream_name}")
                        
                    except Exception as e:
                        logger.error(f"Error publishing outbox entry {entry.id}: {e}")
                        entry.status = OutboxStatus.FAILED
                        entry.error_message = str(e)
                        entry.retry_count = (entry.retry_count or 0) + 1
                
                db.session.commit()
                
            except Exception as e:
                logger.error(f"Error in outbox publisher: {e}")
                db.session.rollback()
            
            time.sleep(1)  # Process every second

def start_ui_bridge(app):
    """Bridge Redis pub/sub to Socket.IO for UI updates."""
    logger.info("Starting UI bridge")
    
    with app.app_context():
        try:
            pubsub = redis_client.pubsub()
            if pubsub is None:
                logger.error("Redis pubsub client is not available")
                return
                
            pubsub.subscribe('ui.broadcast')
            
            for message in pubsub.listen():
                try:
                    if message['type'] == 'message':
                        data = json.loads(message['data'])
                        event_type = data.get('event')
                        payload = data.get('payload', {})
                        
                        # Emit to all connected clients
                        socketio.emit(event_type, payload, namespace='/')
                        
                        logger.debug(f"Broadcast {event_type} to UI clients")
                        
                except Exception as e:
                    logger.error(f"Error processing UI bridge message: {e}")
                    
        except Exception as e:
            logger.error(f"Error in UI bridge: {e}")

def start_risk_predictor_loop(app):
    """Start the risk predictor agent loop."""
    from app.agents.risk_predictor import RiskPredictorAgent
    from app.agents.communicator import AgentCommunicator
    
    logger.info("Starting enhanced risk predictor loop with external data feeds")
    
    with app.app_context():
        communicator = AgentCommunicator()
        agent = RiskPredictorAgent(communicator)
        
        while True:
            try:
                # Run enhanced assessment cycle
                agent.run_assessment_cycle()
            except Exception as e:
                logger.error(f"Error in enhanced risk predictor loop: {e}")
            
            time.sleep(300)  # Run every 5 minutes

def start_enhanced_risk_predictor_loop(app):
    """Start the enhanced risk predictor agent loop with real-time external data feeds."""
    logger.info("🚀 Starting Enhanced Risk Predictor Agent with external data feeds")
    
    with app.app_context():
        try:
            # Import the enhanced agent from our activation script
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
            from activate_risk_predictor import EnhancedRiskPredictorAgent
            
            # Initialize enhanced agent
            enhanced_agent = EnhancedRiskPredictorAgent(app)
            
            # Start real-time monitoring
            enhanced_agent.start_real_time_monitoring()
            
            logger.info("✅ Enhanced Risk Predictor Agent activated with external data feeds")
            
            # Keep the loop alive
            while True:
                time.sleep(60)  # Check every minute
                
        except Exception as e:
            logger.error(f"❌ Enhanced Risk Predictor Agent failed to start: {e}")
            # Fallback to standard risk predictor
            logger.info("Falling back to standard risk predictor agent")
            start_risk_predictor_loop(app)

def start_route_optimizer_loop(app):
    """Start the route optimizer agent loop."""
    from app.agents.route_optimizer import RouteOptimizerAgent
    
    logger.info("Starting route optimizer loop")
    interval = int(os.getenv('ROUTE_OPTIMIZER_INTERVAL', '600'))  # 10 minutes default
    
    with app.app_context():
        agent = RouteOptimizerAgent()
        while True:
            try:
                agent.run_cycle()
            except Exception as e:
                logger.error(f"Error in route optimizer loop: {e}")
            
            time.sleep(interval)  # Run every 10 minutes

def start_procurement_agent_loop(app):
    """Start the procurement agent loop."""
    from app.agents.procurement_agent import ProcurementAgent
    
    logger.info("Starting procurement agent loop")
    
    with app.app_context():
        agent = ProcurementAgent()
        while True:
            try:
                agent.run_cycle()
            except Exception as e:
                logger.error(f"Error in procurement agent loop: {e}")
            
            time.sleep(900)  # Run every 15 minutes

def start_orchestrator_loop(app):
    """Start the orchestrator agent loop."""
    from app.agents.orchestrator import OrchestratorAgent
    
    logger.info("Starting orchestrator loop")
    
    with app.app_context():
        agent = OrchestratorAgent()
        while True:
            try:
                agent.run_cycle()
            except Exception as e:
                logger.error(f"Error in orchestrator loop: {e}")
            
            time.sleep(60)  # Run every minute

def start_all_background_loops(app):
    """Start all background loops with enhanced Risk Predictor Agent"""
    from threading import Thread
    
    # Outbox Publisher
    outbox_thread = Thread(target=outbox_publisher_loop, args=(app,), daemon=True)
    outbox_thread.start()
    
    # Start UI bridge
    ui_bridge_thread = Thread(target=start_ui_bridge, args=(app,), daemon=True)
    ui_bridge_thread.start()
    
    # Start ENHANCED risk predictor with external data feeds
    risk_predictor_thread = Thread(target=start_enhanced_risk_predictor_loop, args=(app,), daemon=True, name="EnhancedRiskPredictor")
    risk_predictor_thread.start()
    
    # Start route optimizer
    route_optimizer_thread = Thread(target=start_route_optimizer_loop, args=(app,), daemon=True)
    route_optimizer_thread.start()
    
    # Start procurement agent
    procurement_agent_thread = Thread(target=start_procurement_agent_loop, args=(app,), daemon=True)
    procurement_agent_thread.start()
    
    # Start orchestrator
    orchestrator_thread = Thread(target=start_orchestrator_loop, args=(app,), daemon=True)
    orchestrator_thread.start()
    
    logger.info("🎯 All background loops started with Enhanced Risk Predictor Agent")

if __name__ == '__main__':
    # When run directly, start only background loops
    start_all_background_loops()
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Shutting down background loops")
