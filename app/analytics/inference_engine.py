"""
Inference Engine for Real-time ML Predictions
"""
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
import json
from dataclasses import asdict

from app import db
from app.models import Shipment, Route, Supplier, Inventory, Recommendation, RecommendationType
from .ml_engine import MLEngine, MLPrediction
from .predictive_models import (
    DemandForecastModel, RiskPredictionModel, RouteOptimizationModel,
    SupplierScoringModel, InventoryOptimizationModel
)
from .data_pipeline import DataPipeline, FeatureEngineering

logger = logging.getLogger(__name__)

class InferenceEngine:
    """Real-time inference engine for supply chain predictions"""
    
    def __init__(self):
        self.name = 'inference_engine'
        self.ml_engine = MLEngine()
        self.data_pipeline = DataPipeline()
        self.feature_engineering = FeatureEngineering()
        
        # Initialize specialized models
        self.demand_model = DemandForecastModel(self.ml_engine)
        self.risk_model = RiskPredictionModel(self.ml_engine)
        self.route_model = RouteOptimizationModel(self.ml_engine)
        self.supplier_model = SupplierScoringModel(self.ml_engine)
        self.inventory_model = InventoryOptimizationModel(self.ml_engine)
        
        # Prediction cache
        self.prediction_cache = {}
        self.cache_ttl = 300  # 5 minutes
        
        logger.info("Inference Engine initialized")
    
    def predict_shipment_optimization(self, shipment_id: str) -> Dict[str, Any]:
        """Comprehensive shipment optimization predictions"""
        try:
            # Check cache
            cache_key = f"shipment_opt_{shipment_id}"
            cached = self._get_cached_prediction(cache_key)
            if cached:
                return cached
            
            shipment = db.session.get(Shipment, shipment_id)
            if not shipment:
                return {'error': 'Shipment not found'}
            
            predictions = {}
            
            # Risk prediction
            risk_pred = self.risk_model.predict_shipment_risk(shipment_id)
            predictions['risk'] = {
                'score': risk_pred.prediction,
                'confidence': risk_pred.confidence,
                'explanation': risk_pred.explanation,
                'feature_importance': risk_pred.feature_importance
            }
            
            # Route optimization
            route_opt = self.route_model.optimize_route(shipment_id)
            predictions['route_optimization'] = route_opt
            
            # Cost and time predictions for each route
            route_predictions = {}
            for route in shipment.routes:
                route_data = {
                    'cost_usd': route.cost_usd or 0,
                    'distance_km': route.distance_km or 0,
                    'estimated_duration_hours': route.estimated_duration_hours or 0,
                    'carbon_emissions_kg': route.carbon_emissions_kg or 0,
                    'risk_score': route.risk_score or 0,
                    'mode': route.mode,
                    'carrier': route.carrier,
                }
                
                route_perf = self.route_model.predict_route_performance(route_data)
                route_predictions[route.id] = route_perf
            
            predictions['route_performance'] = route_predictions
            
            # Overall recommendations
            predictions['recommendations'] = self._generate_shipment_recommendations(
                shipment, predictions
            )
            
            # Cache the result
            self._cache_prediction(cache_key, predictions)
            
            return predictions
            
        except Exception as e:
            logger.error(f"Error predicting shipment optimization: {e}")
            return {'error': str(e)}
    
    def predict_supplier_performance(self, supplier_id: str) -> Dict[str, Any]:
        """Comprehensive supplier performance predictions"""
        try:
            cache_key = f"supplier_perf_{supplier_id}"
            cached = self._get_cached_prediction(cache_key)
            if cached:
                return cached
            
            # Supplier scoring
            score_pred = self.supplier_model.score_supplier(supplier_id)
            
            # Risk assessment
            risk_pred = self.risk_model.predict_supplier_risk(supplier_id)
            
            predictions = {
                'overall_score': {
                    'score': score_pred.prediction,
                    'confidence': score_pred.confidence,
                    'explanation': score_pred.explanation,
                    'feature_importance': score_pred.feature_importance
                },
                'risk_assessment': {
                    'risk_score': risk_pred.prediction,
                    'confidence': risk_pred.confidence,
                    'explanation': risk_pred.explanation
                },
                'recommendations': self._generate_supplier_recommendations(
                    supplier_id, score_pred, risk_pred
                )
            }
            
            self._cache_prediction(cache_key, predictions)
            return predictions
            
        except Exception as e:
            logger.error(f"Error predicting supplier performance: {e}")
            return {'error': str(e)}
    
    def predict_inventory_optimization(self, item_id: str) -> Dict[str, Any]:
        """Comprehensive inventory optimization predictions"""
        try:
            cache_key = f"inventory_opt_{item_id}"
            cached = self._get_cached_prediction(cache_key)
            if cached:
                return cached
            
            # Demand forecasting
            demand_pred = self.demand_model.predict_demand(item_id)
            
            # Inventory optimization
            inventory_pred = self.inventory_model.optimize_inventory_level(item_id)
            
            # Stockout risk
            stockout_pred = self.inventory_model.predict_stockout_risk(item_id)
            
            # Seasonal demand
            seasonal_demand = self.demand_model.predict_seasonal_demand(item_id)
            
            predictions = {
                'demand_forecast': {
                    'predicted_demand': demand_pred.prediction,
                    'confidence': demand_pred.confidence,
                    'explanation': demand_pred.explanation
                },
                'inventory_optimization': {
                    'optimal_level': inventory_pred.prediction,
                    'confidence': inventory_pred.confidence,
                    'explanation': inventory_pred.explanation
                },
                'stockout_risk': {
                    'risk_score': stockout_pred.prediction,
                    'confidence': stockout_pred.confidence,
                    'explanation': stockout_pred.explanation
                },
                'seasonal_patterns': seasonal_demand,
                'recommendations': self._generate_inventory_recommendations(
                    item_id, demand_pred, inventory_pred, stockout_pred
                )
            }
            
            self._cache_prediction(cache_key, predictions)
            return predictions
            
        except Exception as e:
            logger.error(f"Error predicting inventory optimization: {e}")
            return {'error': str(e)}
    
    def predict_demand_patterns(self, product_ids: List[str], 
                              horizon_days: int = 30) -> Dict[str, Any]:
        """Predict demand patterns for multiple products"""
        try:
            predictions = {}
            
            for product_id in product_ids:
                demand_pred = self.demand_model.predict_demand(product_id, horizon_days)
                seasonal_pred = self.demand_model.predict_seasonal_demand(product_id)
                
                predictions[product_id] = {
                    'short_term_demand': {
                        'prediction': demand_pred.prediction,
                        'confidence': demand_pred.confidence,
                        'horizon_days': horizon_days
                    },
                    'seasonal_patterns': seasonal_pred
                }
            
            # Cross-product insights
            predictions['insights'] = self._generate_demand_insights(predictions)
            
            return predictions
            
        except Exception as e:
            logger.error(f"Error predicting demand patterns: {e}")
            return {'error': str(e)}
    
    def predict_risk_landscape(self, workspace_id: Optional[str] = None) -> Dict[str, Any]:
        """Predict overall risk landscape for workspace"""
        try:
            cache_key = f"risk_landscape_{workspace_id or 'global'}"
            cached = self._get_cached_prediction(cache_key)
            if cached:
                return cached
            
            # Get active shipments and suppliers
            shipment_query = Shipment.query.filter(
                Shipment.status.in_(['pending', 'in_transit'])
            )
            if workspace_id:
                shipment_query = shipment_query.filter(Shipment.workspace_id == workspace_id)
            
            supplier_query = Supplier.query.filter(Supplier.is_active == True)
            if workspace_id:
                supplier_query = supplier_query.filter(Supplier.workspace_id == workspace_id)
            
            shipments = shipment_query.all()
            suppliers = supplier_query.all()
            
            risk_predictions = {
                'shipment_risks': [],
                'supplier_risks': [],
                'overall_risk_score': 0.0,
                'risk_distribution': {},
                'high_risk_items': [],
                'recommendations': []
            }
            
            # Predict risks for shipments
            shipment_risks = []
            for shipment in shipments[:20]:  # Limit for performance
                risk_pred = self.risk_model.predict_shipment_risk(str(shipment.id))
                shipment_risks.append({
                    'shipment_id': shipment.id,
                    'risk_score': risk_pred.prediction,
                    'confidence': risk_pred.confidence,
                    'explanation': risk_pred.explanation
                })
            
            # Predict risks for suppliers
            supplier_risks = []
            for supplier in suppliers[:15]:  # Limit for performance
                risk_pred = self.risk_model.predict_supplier_risk(str(supplier.id))
                supplier_risks.append({
                    'supplier_id': supplier.id,
                    'supplier_name': supplier.name,
                    'risk_score': risk_pred.prediction,
                    'confidence': risk_pred.confidence
                })
            
            risk_predictions['shipment_risks'] = shipment_risks
            risk_predictions['supplier_risks'] = supplier_risks
            
            # Calculate overall metrics
            all_risks = [r['risk_score'] for r in shipment_risks + supplier_risks]
            if all_risks:
                risk_predictions['overall_risk_score'] = np.mean(all_risks)
                risk_predictions['risk_distribution'] = {
                    'low': sum(1 for r in all_risks if r < 0.3) / len(all_risks),
                    'medium': sum(1 for r in all_risks if 0.3 <= r < 0.7) / len(all_risks),
                    'high': sum(1 for r in all_risks if r >= 0.7) / len(all_risks)
                }
                
                # High risk items
                risk_predictions['high_risk_items'] = [
                    item for item in shipment_risks + supplier_risks
                    if item['risk_score'] >= 0.7
                ]
            
            # Generate recommendations
            risk_predictions['recommendations'] = self._generate_risk_recommendations(
                risk_predictions
            )
            
            self._cache_prediction(cache_key, risk_predictions)
            return risk_predictions
            
        except Exception as e:
            logger.error(f"Error predicting risk landscape: {e}")
            return {'error': str(e)}
    
    def batch_predict(self, prediction_requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process multiple prediction requests in batch"""
        results = []
        
        for request in prediction_requests:
            try:
                prediction_type = request.get('type')
                
                if prediction_type == 'shipment_optimization':
                    result = self.predict_shipment_optimization(request['shipment_id'])
                elif prediction_type == 'supplier_performance':
                    result = self.predict_supplier_performance(request['supplier_id'])
                elif prediction_type == 'inventory_optimization':
                    result = self.predict_inventory_optimization(request['item_id'])
                elif prediction_type == 'demand_patterns':
                    result = self.predict_demand_patterns(
                        request['product_ids'], 
                        request.get('horizon_days', 30)
                    )
                elif prediction_type == 'risk_landscape':
                    result = self.predict_risk_landscape(request.get('workspace_id'))
                else:
                    result = {'error': f'Unknown prediction type: {prediction_type}'}
                
                results.append({
                    'request_id': request.get('id', len(results)),
                    'type': prediction_type,
                    'result': result,
                    'timestamp': datetime.utcnow().isoformat()
                })
                
            except Exception as e:
                results.append({
                    'request_id': request.get('id', len(results)),
                    'type': request.get('type', 'unknown'),
                    'error': str(e),
                    'timestamp': datetime.utcnow().isoformat()
                })
        
        return results
    
    def _generate_shipment_recommendations(self, shipment, predictions: Dict) -> List[Dict]:
        """Generate recommendations for shipment optimization"""
        recommendations = []
        
        risk_score = predictions.get('risk', {}).get('score', 0)
        route_opt = predictions.get('route_optimization', {})
        
        # High risk recommendation
        if risk_score > 0.7:
            recommendations.append({
                'type': 'risk_mitigation',
                'priority': 'high',
                'action': 'Consider alternative routing or additional insurance',
                'rationale': f'High risk score: {risk_score:.2f}'
            })
        
        # Route optimization recommendation
        if route_opt.get('recommended_route_id'):
            if route_opt.get('optimization_score', 0) > 0.8:
                recommendations.append({
                    'type': 'route_optimization',
                    'priority': 'medium',
                    'action': f'Switch to route {route_opt["recommended_route_id"]}',
                    'rationale': route_opt.get('explanation', 'Better optimization score')
                })
        
        return recommendations
    
    def _generate_supplier_recommendations(self, supplier_id: str, 
                                         score_pred: MLPrediction, 
                                         risk_pred: MLPrediction) -> List[Dict]:
        """Generate recommendations for supplier management"""
        recommendations = []
        
        # Low performance recommendation
        if score_pred.prediction < 0.5:
            recommendations.append({
                'type': 'performance_improvement',
                'priority': 'high',
                'action': 'Review supplier contract and performance metrics',
                'rationale': f'Low performance score: {score_pred.prediction:.2f}'
            })
        
        # High risk recommendation
        if risk_pred.prediction > 0.6:
            recommendations.append({
                'type': 'risk_management',
                'priority': 'medium',
                'action': 'Implement additional monitoring and backup suppliers',
                'rationale': f'High risk score: {risk_pred.prediction:.2f}'
            })
        
        return recommendations
    
    def _generate_inventory_recommendations(self, item_id: str,
                                          demand_pred: MLPrediction,
                                          inventory_pred: MLPrediction,
                                          stockout_pred: MLPrediction) -> List[Dict]:
        """Generate recommendations for inventory management"""
        recommendations = []
        
        # High stockout risk
        if stockout_pred.prediction > 0.6:
            recommendations.append({
                'type': 'stockout_prevention',
                'priority': 'high',
                'action': 'Increase stock level and expedite next order',
                'rationale': f'High stockout risk: {stockout_pred.prediction:.2f}'
            })
        
        # Inventory optimization
        current_level = 100  # This would come from actual inventory data
        optimal_level = inventory_pred.prediction
        
        if abs(optimal_level - current_level) > current_level * 0.2:
            action = 'increase' if optimal_level > current_level else 'decrease'
            recommendations.append({
                'type': 'inventory_adjustment',
                'priority': 'medium',
                'action': f'Adjust inventory level: {action} to {optimal_level:.0f}',
                'rationale': f'Current level suboptimal by {abs(optimal_level - current_level):.0f} units'
            })
        
        return recommendations
    
    def _generate_demand_insights(self, predictions: Dict) -> List[Dict]:
        """Generate cross-product demand insights"""
        insights = []
        
        # Find products with highest predicted demand
        demand_scores = {}
        for product_id, pred in predictions.items():
            if isinstance(pred, dict) and 'short_term_demand' in pred:
                demand_scores[product_id] = pred['short_term_demand']['prediction']
        
        if demand_scores:
            top_product = max(demand_scores.keys(), key=lambda x: demand_scores[x])
            insights.append({
                'type': 'demand_leader',
                'insight': f'Product {top_product} has highest predicted demand',
                'value': demand_scores[top_product]
            })
        
        return insights
    
    def _generate_risk_recommendations(self, risk_predictions: Dict) -> List[Dict]:
        """Generate recommendations for risk management"""
        recommendations = []
        
        overall_risk = risk_predictions.get('overall_risk_score', 0)
        high_risk_items = risk_predictions.get('high_risk_items', [])
        
        # Overall risk level
        if overall_risk > 0.6:
            recommendations.append({
                'type': 'risk_management',
                'priority': 'high',
                'action': 'Implement enhanced monitoring and contingency planning',
                'rationale': f'Overall risk score elevated: {overall_risk:.2f}'
            })
        
        # High risk items
        if len(high_risk_items) > 5:
            recommendations.append({
                'type': 'risk_diversification',
                'priority': 'medium',
                'action': 'Consider diversifying suppliers and routes',
                'rationale': f'{len(high_risk_items)} items with high risk scores'
            })
        
        return recommendations
    
    def _get_cached_prediction(self, cache_key: str) -> Optional[Dict]:
        """Get prediction from cache if still valid"""
        if cache_key in self.prediction_cache:
            cached_data, timestamp = self.prediction_cache[cache_key]
            if (datetime.utcnow() - timestamp).seconds < self.cache_ttl:
                return cached_data
            else:
                del self.prediction_cache[cache_key]
        return None
    
    def _cache_prediction(self, cache_key: str, prediction: Dict):
        """Cache prediction result"""
        self.prediction_cache[cache_key] = (prediction, datetime.utcnow())
        
        # Clean old cache entries
        if len(self.prediction_cache) > 100:
            oldest_key = min(self.prediction_cache.keys(), 
                           key=lambda k: self.prediction_cache[k][1])
            del self.prediction_cache[oldest_key]
    
    def get_inference_stats(self) -> Dict[str, Any]:
        """Get inference engine statistics"""
        return {
            'cache_size': len(self.prediction_cache),
            'ml_engine_info': self.ml_engine.get_model_info(),
            'available_models': {
                'demand_forecast': True,
                'risk_prediction': True,
                'route_optimization': True,
                'supplier_scoring': True,
                'inventory_optimization': True
            },
            'cache_ttl_seconds': self.cache_ttl
        }
