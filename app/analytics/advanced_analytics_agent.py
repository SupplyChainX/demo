"""
Advanced Analytics Agent - Machine Learning Integration for Supply Chain Optimization
"""
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from flask import current_app

from app import db
from app.models import (
    Shipment, Route, Supplier, Inventory, PurchaseOrder, Recommendation,
    RecommendationType, Alert, Workspace, Outbox, AuditLog
)
from app.agents.communicator import AgentCommunicator
from app.agents.routes import update_agent_status

from .ml_engine import MLEngine
from .inference_engine import InferenceEngine
from .model_training import ModelTrainer
from .model_evaluation import ModelEvaluator
from .data_pipeline import DataPipeline, FeatureEngineering

logger = logging.getLogger(__name__)

class AdvancedAnalyticsAgent:
    """Advanced Analytics Agent with ML-powered supply chain optimization"""
    
    def __init__(self):
        self.name = 'advanced_analytics'
        self.communicator = AgentCommunicator(self.name)
        
        # Initialize ML components
        self.ml_engine = MLEngine()
        self.data_pipeline = DataPipeline()
        self.feature_engineering = FeatureEngineering()
        self.inference_engine = InferenceEngine()
        self.model_trainer = ModelTrainer(self.ml_engine, self.data_pipeline)
        self.model_evaluator = ModelEvaluator(self.ml_engine)
        
        # Analytics configuration
        self.analysis_intervals = {
            'real_time': 0,      # Immediate analysis
            'hourly': 3600,      # 1 hour
            'daily': 86400,      # 24 hours
            'weekly': 604800     # 7 days
        }
        
        self.prediction_cache = {}
        self.analytics_history = {}
        
        logger.info("Advanced Analytics Agent initialized with ML capabilities")
    
    def start(self):
        """Start the analytics agent"""
        try:
            update_agent_status(self.name, {'status': 'starting'})
            
            # Initialize models if available
            self._initialize_models()
            
            # Start main analytics loop
            self._start_analytics_loop()
            
            update_agent_status(self.name, {'status': 'running'})
            logger.info("Advanced Analytics Agent started successfully")
            
        except Exception as e:
            logger.error(f"Error starting Advanced Analytics Agent: {e}")
            update_agent_status(self.name, {'status': 'error', 'error': str(e)})
    
    def _initialize_models(self):
        """Initialize and validate ML models"""
        try:
            # Check if models need training
            if self._should_train_models():
                logger.info("Training ML models...")
                training_results = self.model_trainer.train_all_models()
                logger.info(f"Model training completed: {training_results}")
            
            # Evaluate model health
            evaluation = self.model_evaluator.evaluate_all_models()
            logger.info(f"Model evaluation: {evaluation['summary']}")
            
        except Exception as e:
            logger.error(f"Error initializing models: {e}")
    
    def _should_train_models(self) -> bool:
        """Determine if models need training"""
        # Check if model files exist and are recent
        model_info = self.ml_engine.get_model_info()
        if model_info['total_models'] == 0:
            return True
        
        # In production, check model age and performance
        return False  # Skip training for now to avoid delays
    
    def _start_analytics_loop(self):
        """Start the main analytics processing loop"""
        try:
            # Process pending analytics requests
            self._process_analytics_requests()
            
            # Generate proactive insights
            self._generate_proactive_insights()
            
            # Update analytics cache
            self._update_analytics_cache()
            
        except Exception as e:
            logger.error(f"Error in analytics loop: {e}")
    
    def analyze_shipment_optimization(self, shipment_id: str, 
                                    analysis_type: str = 'comprehensive') -> Dict[str, Any]:
        """Comprehensive shipment optimization analysis"""
        try:
            # Get ML predictions
            ml_predictions = self.inference_engine.predict_shipment_optimization(shipment_id)
            
            # Add traditional analytics
            traditional_analysis = self._traditional_shipment_analysis(shipment_id)
            
            # Combine insights
            analysis = {
                'shipment_id': shipment_id,
                'analysis_type': analysis_type,
                'ml_predictions': ml_predictions,
                'traditional_analysis': traditional_analysis,
                'combined_insights': self._combine_shipment_insights(ml_predictions, traditional_analysis),
                'recommendations': self._generate_shipment_recommendations(ml_predictions, traditional_analysis),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Create recommendations in the system
            self._create_recommendations_from_analysis(shipment_id, analysis)
            
            # Log analytics activity
            self._log_analytics_activity('shipment_optimization', shipment_id, analysis)
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing shipment {shipment_id}: {e}")
            return {'error': str(e), 'shipment_id': shipment_id}
    
    def analyze_supplier_performance(self, supplier_id: str) -> Dict[str, Any]:
        """Comprehensive supplier performance analysis"""
        try:
            # Get ML predictions
            ml_predictions = self.inference_engine.predict_supplier_performance(supplier_id)
            
            # Add traditional analytics
            traditional_analysis = self._traditional_supplier_analysis(supplier_id)
            
            # Combine insights
            analysis = {
                'supplier_id': supplier_id,
                'ml_predictions': ml_predictions,
                'traditional_analysis': traditional_analysis,
                'combined_insights': self._combine_supplier_insights(ml_predictions, traditional_analysis),
                'recommendations': self._generate_supplier_recommendations(ml_predictions, traditional_analysis),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Update supplier scoring
            self._update_supplier_scoring(supplier_id, analysis)
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing supplier {supplier_id}: {e}")
            return {'error': str(e), 'supplier_id': supplier_id}
    
    def analyze_demand_patterns(self, workspace_id: Optional[str] = None,
                              product_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Analyze demand patterns and forecasting"""
        try:
            if not product_ids:
                # Get products from inventory
                inventory_query = Inventory.query
                if workspace_id:
                    inventory_query = inventory_query.filter(Inventory.workspace_id == workspace_id)
                
                inventory_items = inventory_query.limit(20).all()
                product_ids = [str(item.id) for item in inventory_items]
            
            if not product_ids:
                return {'error': 'No products found for analysis'}
            
            # Get ML predictions
            ml_predictions = self.inference_engine.predict_demand_patterns(product_ids)
            
            # Add traditional demand analysis
            traditional_analysis = self._traditional_demand_analysis(product_ids, workspace_id)
            
            analysis = {
                'workspace_id': workspace_id,
                'product_count': len(product_ids),
                'ml_predictions': ml_predictions,
                'traditional_analysis': traditional_analysis,
                'combined_insights': self._combine_demand_insights(ml_predictions, traditional_analysis),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing demand patterns: {e}")
            return {'error': str(e)}
    
    def analyze_risk_landscape(self, workspace_id: Optional[str] = None) -> Dict[str, Any]:
        """Comprehensive risk landscape analysis"""
        try:
            # Get ML predictions
            ml_predictions = self.inference_engine.predict_risk_landscape(workspace_id)
            
            # Add traditional risk analysis
            traditional_analysis = self._traditional_risk_analysis(workspace_id)
            
            analysis = {
                'workspace_id': workspace_id,
                'ml_predictions': ml_predictions,
                'traditional_analysis': traditional_analysis,
                'combined_insights': self._combine_risk_insights(ml_predictions, traditional_analysis),
                'recommendations': self._generate_risk_recommendations(ml_predictions, traditional_analysis),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Generate alerts for high-risk items
            self._generate_risk_alerts(analysis)
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing risk landscape: {e}")
            return {'error': str(e)}
    
    def generate_executive_dashboard(self, workspace_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate executive dashboard with key metrics and insights"""
        try:
            # Get shipment metrics
            shipment_metrics = self._get_shipment_metrics(workspace_id)
            
            # Get supplier metrics
            supplier_metrics = self._get_supplier_metrics(workspace_id)
            
            # Get inventory metrics
            inventory_metrics = self._get_inventory_metrics(workspace_id)
            
            # Get risk metrics
            risk_metrics = self._get_risk_metrics(workspace_id)
            
            # Get ML model health
            model_health = self.model_evaluator.create_health_dashboard_data()
            
            # Combine into executive summary
            dashboard = {
                'workspace_id': workspace_id,
                'summary_metrics': {
                    'shipments': shipment_metrics,
                    'suppliers': supplier_metrics,
                    'inventory': inventory_metrics,
                    'risk': risk_metrics
                },
                'ml_health': model_health,
                'key_insights': self._generate_executive_insights(
                    shipment_metrics, supplier_metrics, inventory_metrics, risk_metrics
                ),
                'recommendations': self._generate_executive_recommendations(),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            return dashboard
            
        except Exception as e:
            logger.error(f"Error generating executive dashboard: {e}")
            return {'error': str(e)}
    
    def _traditional_shipment_analysis(self, shipment_id: str) -> Dict[str, Any]:
        """Traditional shipment analysis without ML"""
        shipment = db.session.get(Shipment, shipment_id)
        if not shipment:
            return {'error': 'Shipment not found'}
        
        # Calculate basic metrics
        total_cost = sum(r.cost_usd or 0 for r in shipment.routes)
        total_distance = sum(r.distance_km or 0 for r in shipment.routes)
        total_duration = sum(r.estimated_duration_hours or 0 for r in shipment.routes)
        
        # Route efficiency analysis
        if total_distance > 0 and total_duration > 0:
            cost_per_km = total_cost / total_distance
            speed_kmh = total_distance / total_duration
        else:
            cost_per_km = 0
            speed_kmh = 0
        
        return {
            'basic_metrics': {
                'total_cost': total_cost,
                'total_distance': total_distance,
                'total_duration': total_duration,
                'route_count': len(shipment.routes)
            },
            'efficiency_metrics': {
                'cost_per_km': cost_per_km,
                'average_speed_kmh': speed_kmh,
                'modes_used': list(set(r.mode for r in shipment.routes if r.mode))
            }
        }
    
    def _traditional_supplier_analysis(self, supplier_id: str) -> Dict[str, Any]:
        """Traditional supplier analysis without ML"""
        supplier = db.session.get(Supplier, supplier_id)
        if not supplier:
            return {'error': 'Supplier not found'}
        
        # Get purchase orders for this supplier
        recent_pos = PurchaseOrder.query.filter(
            PurchaseOrder.supplier_id == supplier_id,
            PurchaseOrder.created_at >= datetime.utcnow() - timedelta(days=90)
        ).all()
        
        # Calculate metrics
        total_orders = len(recent_pos)
        total_value = sum(po.total_amount or 0 for po in recent_pos)
        avg_order_value = total_value / total_orders if total_orders > 0 else 0
        
        return {
            'order_metrics': {
                'total_orders_90d': total_orders,
                'total_value_90d': total_value,
                'avg_order_value': avg_order_value
            },
            'supplier_attributes': {
                'name': supplier.name,
                'contact_info': supplier.contact_info,
                'is_active': supplier.is_active
            }
        }
    
    def _traditional_demand_analysis(self, product_ids: List[str], 
                                   workspace_id: Optional[str]) -> Dict[str, Any]:
        """Traditional demand analysis without ML"""
        # Get inventory items
        inventory_query = Inventory.query.filter(
            Inventory.id.in_([int(pid) for pid in product_ids if pid.isdigit()])
        )
        if workspace_id:
            inventory_query = inventory_query.filter(Inventory.workspace_id == workspace_id)
        
        inventory_items = inventory_query.all()
        
        # Calculate aggregate metrics
        total_current_stock = sum(getattr(item, 'current_stock', 0) for item in inventory_items)
        avg_reorder_point = np.mean([getattr(item, 'reorder_point', 50) for item in inventory_items])
        
        return {
            'inventory_summary': {
                'total_items': len(inventory_items),
                'total_current_stock': total_current_stock,
                'avg_reorder_point': avg_reorder_point
            }
        }
    
    def _traditional_risk_analysis(self, workspace_id: Optional[str]) -> Dict[str, Any]:
        """Traditional risk analysis without ML"""
        # Get recent alerts
        alert_query = Alert.query.filter(
            Alert.created_at >= datetime.utcnow() - timedelta(days=30)
        )
        if workspace_id:
            alert_query = alert_query.filter(Alert.workspace_id == workspace_id)
        
        recent_alerts = alert_query.all()
        
        # Categorize alerts by severity
        alert_summary = {
            'high': len([a for a in recent_alerts if a.severity == 'high']),
            'medium': len([a for a in recent_alerts if a.severity == 'medium']),
            'low': len([a for a in recent_alerts if a.severity == 'low'])
        }
        
        return {
            'alert_summary': alert_summary,
            'total_alerts_30d': len(recent_alerts)
        }
    
    def _process_analytics_requests(self):
        """Process pending analytics requests from other agents"""
        try:
            # Check for messages from other agents
            messages = self.communicator.get_messages('analytics.requests')
            
            for message in messages:
                self._process_analytics_message(message)
                
        except Exception as e:
            logger.error(f"Error processing analytics requests: {e}")
    
    def _process_analytics_message(self, message: Dict[str, Any]):
        """Process a single analytics message"""
        try:
            msg_type = message.get('type')
            
            if msg_type == 'shipment_analysis':
                result = self.analyze_shipment_optimization(message['shipment_id'])
                self.communicator.send_message('analytics.results', result)
                
            elif msg_type == 'supplier_analysis':
                result = self.analyze_supplier_performance(message['supplier_id'])
                self.communicator.send_message('analytics.results', result)
                
            elif msg_type == 'risk_analysis':
                result = self.analyze_risk_landscape(message.get('workspace_id'))
                self.communicator.send_message('analytics.results', result)
                
        except Exception as e:
            logger.error(f"Error processing analytics message: {e}")
    
    def _generate_proactive_insights(self):
        """Generate proactive insights and recommendations"""
        try:
            # Analyze recent shipments for optimization opportunities
            recent_shipments = Shipment.query.filter(
                Shipment.created_at >= datetime.utcnow() - timedelta(hours=24)
            ).limit(10).all()
            
            for shipment in recent_shipments:
                analysis = self.analyze_shipment_optimization(str(shipment.id), 'proactive')
                if analysis.get('recommendations'):
                    self._create_proactive_recommendations(shipment.id, analysis['recommendations'])
                    
        except Exception as e:
            logger.error(f"Error generating proactive insights: {e}")
    
    def _log_analytics_activity(self, activity_type: str, subject_id: str, analysis: Dict[str, Any]):
        """Log analytics activity for audit trail"""
        try:
            audit_log = AuditLog(
                actor_type='agent',
                actor_id=self.name,
                action=f'analytics_{activity_type}',
                subject_type=activity_type.split('_')[0],
                subject_id=subject_id,
                changes={'analysis_summary': analysis.get('combined_insights', {})},
                workspace_id=analysis.get('workspace_id')
            )
            db.session.add(audit_log)
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Error logging analytics activity: {e}")
    
    def get_analytics_summary(self) -> Dict[str, Any]:
        """Get summary of analytics agent status and capabilities"""
        return {
            'name': self.name,
            'status': 'running',
            'ml_capabilities': {
                'models_available': self.ml_engine.get_model_info(),
                'inference_engine': 'active',
                'training_capability': 'available',
                'evaluation_capability': 'available'
            },
            'supported_analyses': [
                'shipment_optimization',
                'supplier_performance', 
                'demand_patterns',
                'risk_landscape',
                'executive_dashboard'
            ],
            'cache_status': {
                'prediction_cache_size': len(self.prediction_cache),
                'analytics_history_size': len(self.analytics_history)
            }
        }

# Helper functions for numpy operations
try:
    import numpy as np
except ImportError:
    # Fallback implementations
    class np:
        @staticmethod
        def mean(values):
            return sum(values) / len(values) if values else 0
        
        @staticmethod  
        def std(values):
            if not values:
                return 0
            mean_val = sum(values) / len(values)
            variance = sum((x - mean_val) ** 2 for x in values) / len(values)
            return variance ** 0.5
