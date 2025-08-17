"""
Agents Module
AI Agents for supply chain automation
"""
from .communicator import AgentCommunicator
from .route_optimizer import RouteOptimizerAgent

def create_agent_manager():
    """Create and configure the agent manager"""
    from .manager import AgentManager
    return AgentManager()

__all__ = ['AgentCommunicator', 'RouteOptimizerAgent', 'create_agent_manager']
def start_all_agents(app=None):
    """Start all agent loops with proper app context."""
    logger.info("Starting all agent loops...")
    
    # Import here to avoid circular imports
    from app.agents.risk_predictor import start_risk_predictor_loop
    from app.agents.route_optimizer import start_route_optimizer_loop
    from app.agents.procurement_agent import start_procurement_agent_loop
    from app.agents.orchestrator import start_orchestrator_loop
    
    # Start each agent in its own thread with app context
    Thread(target=start_risk_predictor_loop, args=(app,), name="RiskPredictor", daemon=True).start()
    Thread(target=start_route_optimizer_loop, args=(app,), name="RouteOptimizer", daemon=True).start()
    Thread(target=start_procurement_agent_loop, args=(app,), name="ProcurementAgent", daemon=True).start()
    Thread(target=start_orchestrator_loop, args=(app,), name="Orchestrator", daemon=True).start()
    
    logger.info("All agent loops started successfully")
