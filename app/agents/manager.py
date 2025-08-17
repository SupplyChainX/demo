"""
Agent Manager
Manages lifecycle of AI agents
"""
import logging
import threading
import time
from typing import Dict, List
from datetime import datetime

from .route_optimizer import RouteOptimizerAgent
from .risk_predictor import RiskPredictorAgent
from .procurement_agent import ProcurementAgent
from .orchestrator import OrchestratorAgent
from .communicator import AgentCommunicator

logger = logging.getLogger(__name__)

class AgentManager:
    """Manages AI agents lifecycle"""
    
    def __init__(self, app=None):
        self.agents = {}
        self.threads = {}
        self.running = False
        self.app = app
        
    def start(self):
        """Start all agents"""
        logger.info("Starting Agent Manager")
        self.running = True
        
        # Initialize all agents with app context
        try:
            self.agents['route_optimizer'] = RouteOptimizerAgent(app=self.app)
            logger.info("Initialized Route Optimizer Agent")
        except Exception as e:
            logger.error(f"Failed to initialize Route Optimizer Agent: {e}")
        
        try:
            communicator = AgentCommunicator('risk_predictor')
            self.agents['risk_predictor'] = RiskPredictorAgent(communicator)
            logger.info("Initialized Risk Predictor Agent")
        except Exception as e:
            logger.error(f"Failed to initialize Risk Predictor Agent: {e}")
        
        try:
            self.agents['procurement_agent'] = ProcurementAgent()
            logger.info("Initialized Procurement Agent")
        except Exception as e:
            logger.error(f"Failed to initialize Procurement Agent: {e}")
        
        try:
            self.agents['orchestrator'] = OrchestratorAgent()
            logger.info("Initialized Orchestrator Agent")
        except Exception as e:
            logger.error(f"Failed to initialize Orchestrator Agent: {e}")
        
        # Start agents in separate threads
        for name, agent in self.agents.items():
            try:
                if hasattr(agent, 'start'):
                    thread = threading.Thread(target=agent.start, daemon=True)
                    thread.start()
                    self.threads[name] = thread
                    logger.info(f"Started agent: {name}")
                else:
                    logger.warning(f"Agent {name} does not have a start method")
            except Exception as e:
                logger.error(f"Failed to start agent {name}: {e}")
    
    def stop(self):
        """Stop all agents"""
        logger.info("Stopping Agent Manager")
        self.running = False
        
        # Stop all agents
        for agent in self.agents.values():
            if hasattr(agent, 'stop'):
                agent.stop()
        
        # Wait for threads to finish
        for thread in self.threads.values():
            thread.join(timeout=5)
        
        logger.info("Agent Manager stopped")
    
    def get_status(self) -> Dict:
        """Get status of all agents"""
        status = {
            'manager_running': self.running,
            'agents': {},
            'timestamp': datetime.utcnow().isoformat()
        }
        
        for name, agent in self.agents.items():
            try:
                if hasattr(agent, 'get_status'):
                    agent_status = agent.get_status()
                else:
                    # Create basic status for agents without get_status method
                    agent_status = {
                        'name': name,
                        'running': True,
                        'last_check': datetime.utcnow().isoformat(),
                        'processed_count': getattr(agent, 'processed_count', 0)
                    }
                
                agent_status['thread_alive'] = self.threads.get(name, {}).is_alive() if self.threads.get(name) else False
                status['agents'][name] = agent_status
            except Exception as e:
                status['agents'][name] = {'name': name, 'error': str(e), 'running': False}
        
        return status
    
    def request_optimization(self, shipment_id: int, reason: str = None):
        """Request route optimization for a shipment"""
        if 'route_optimizer' in self.agents:
            agent = self.agents['route_optimizer']
            agent.communicator.publish_route_optimization_request(shipment_id, reason)
            logger.info(f"Requested optimization for shipment {shipment_id}")
        else:
            logger.warning("Route optimizer agent not available")

# Global agent manager instance
agent_manager = None

def get_agent_manager(app=None):
    """Get the global agent manager"""
    global agent_manager
    if agent_manager is None:
        agent_manager = AgentManager(app=app)
    return agent_manager
