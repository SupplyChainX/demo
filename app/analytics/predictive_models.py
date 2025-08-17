"""
Predictive Models for Supply Chain Optimization
"""
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import json

try:
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import mean_squared_error, r2_score
    import xgboost as xgb
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from app import db
from app.models import Shipment, Route, Supplier, Inventory, PurchaseOrder
from .ml_engine import MLEngine, MLPrediction

logger = logging.getLogger(__name__)

class DemandForecastModel:
    """Predicts future demand for inventory optimization"""
    
    def __init__(self, ml_engine: MLEngine):
        self.ml_engine = ml_engine
        self.model_category = 'demand_forecast'
        
    def predict_demand(self, product_id: str, horizon_days: int = 30, 
                      historical_data: Optional[Dict] = None) -> MLPrediction:
        """Predict demand for a product over specified horizon"""
        try:
            # Get historical data
            if not historical_data:
                historical_data = self._get_historical_demand(product_id)
            
            # Extract features
            features = self._extract_demand_features(historical_data, horizon_days)
            
            # Make prediction
            prediction = self.ml_engine.predict(
                self.model_category, 'rf', features, include_confidence=True
            )
            
            # Add demand-specific context
            prediction.explanation = self._generate_demand_explanation(
                prediction.prediction, historical_data, horizon_days
            )
            
            return prediction
            
        except Exception as e:
            logger.error(f"Error predicting demand for {product_id}: {e}")
            return self._fallback_demand_prediction(product_id, horizon_days)
    
    def predict_seasonal_demand(self, product_id: str, months_ahead: int = 12) -> Dict[str, float]:
        """Predict seasonal demand patterns"""
        try:
            historical_data = self._get_historical_demand(product_id)
            seasonal_predictions = {}
            
            for month in range(1, months_ahead + 1):
                features = self._extract_seasonal_features(historical_data, month)
                prediction = self.ml_engine.predict(self.model_category, 'gb', features)
                seasonal_predictions[f"month_{month}"] = prediction.prediction
            
            return seasonal_predictions
            
        except Exception as e:
            logger.error(f"Error predicting seasonal demand: {e}")
            return {f"month_{i}": 100.0 for i in range(1, months_ahead + 1)}
    
    def _get_historical_demand(self, product_id: str) -> Dict[str, Any]:
        """Get historical demand data for product"""
        # Simulate historical demand data
        base_demand = 100
        return {
            'avg_daily_demand': base_demand,
            'demand_volatility': 0.2,
            'seasonal_factor': 1.1,
            'trend_factor': 1.05,
            'historical_points': [base_demand * (1 + np.random.normal(0, 0.1)) for _ in range(30)]
        }
    
    def _extract_demand_features(self, historical_data: Dict, horizon_days: int) -> np.ndarray:
        """Extract features for demand prediction"""
        features = [
            historical_data.get('avg_daily_demand', 100),
            historical_data.get('demand_volatility', 0.2),
            historical_data.get('seasonal_factor', 1.0),
            historical_data.get('trend_factor', 1.0),
            horizon_days,
            datetime.now().weekday(),
            datetime.now().month,
            len(historical_data.get('historical_points', [])),
        ]
        return np.array(features)
    
    def _extract_seasonal_features(self, historical_data: Dict, month_offset: int) -> np.ndarray:
        """Extract seasonal features"""
        target_month = (datetime.now().month + month_offset - 1) % 12 + 1
        features = [
            historical_data.get('avg_daily_demand', 100),
            historical_data.get('seasonal_factor', 1.0),
            target_month,
            target_month / 12.0,  # Normalized month
            np.sin(2 * np.pi * target_month / 12),  # Seasonal sine
            np.cos(2 * np.pi * target_month / 12),  # Seasonal cosine
        ]
        return np.array(features)
    
    def _generate_demand_explanation(self, prediction: float, historical_data: Dict, 
                                   horizon_days: int) -> str:
        """Generate explanation for demand prediction"""
        avg_demand = historical_data.get('avg_daily_demand', 100)
        change_pct = ((prediction - avg_demand) / avg_demand) * 100
        
        if abs(change_pct) < 5:
            trend = "stable"
        elif change_pct > 0:
            trend = f"increasing by {change_pct:.1f}%"
        else:
            trend = f"decreasing by {abs(change_pct):.1f}%"
        
        return f"Predicted demand: {prediction:.1f} units over {horizon_days} days. Trend: {trend} compared to historical average."
    
    def _fallback_demand_prediction(self, product_id: str, horizon_days: int) -> MLPrediction:
        """Fallback prediction when ML is unavailable"""
        return MLPrediction(
            model_name="demand_forecast.fallback",
            prediction=100.0 * horizon_days / 30,
            confidence=0.5,
            feature_importance={},
            explanation=f"Fallback demand prediction for {horizon_days} days: assuming baseline demand"
        )

class RiskPredictionModel:
    """Predicts supply chain risks across multiple dimensions"""
    
    def __init__(self, ml_engine: MLEngine):
        self.ml_engine = ml_engine
        self.model_category = 'risk_prediction'
    
    def predict_shipment_risk(self, shipment_id: str) -> MLPrediction:
        """Predict risk for a specific shipment"""
        try:
            shipment = db.session.get(Shipment, shipment_id)
            if not shipment:
                return self._fallback_risk_prediction("shipment", 0.3)
            
            # Extract shipment features
            shipment_data = {
                'cost_usd': shipment.cost_usd or 0,
                'distance_km': sum(r.distance_km or 0 for r in shipment.routes),
                'estimated_duration_hours': sum(r.estimated_duration_hours or 0 for r in shipment.routes),
                'carbon_emissions_kg': sum(r.carbon_emissions_kg or 0 for r in shipment.routes),
                'risk_score': shipment.risk_score or 0,
                'routes': [{'mode': r.mode, 'carrier': r.carrier} for r in shipment.routes],
                'created_at': shipment.created_at,
                'origin_lat': shipment.origin_lat,
                'origin_lon': shipment.origin_lon,
                'destination_lat': shipment.destination_lat,
                'destination_lon': shipment.destination_lon,
            }
            
            features = self.ml_engine.extract_features('shipment', shipment_data)
            prediction = self.ml_engine.predict(self.model_category, 'rf_classifier', features)
            
            # Add risk-specific context
            prediction.explanation = self._generate_risk_explanation(
                prediction.prediction, shipment_data
            )
            
            return prediction
            
        except Exception as e:
            logger.error(f"Error predicting shipment risk: {e}")
            return self._fallback_risk_prediction("shipment", 0.3)
    
    def predict_supplier_risk(self, supplier_id: str) -> MLPrediction:
        """Predict risk for a specific supplier"""
        try:
            supplier = db.session.get(Supplier, supplier_id)
            if not supplier:
                return self._fallback_risk_prediction("supplier", 0.3)
            
            # Extract supplier features
            supplier_data = {
                'reliability_score': getattr(supplier, 'reliability_score', 0.7),
                'quality_score': getattr(supplier, 'quality_score', 0.7),
                'delivery_performance': getattr(supplier, 'delivery_performance', 0.7),
                'cost_competitiveness': getattr(supplier, 'cost_competitiveness', 0.7),
                'financial_stability': getattr(supplier, 'financial_stability', 0.7),
                'total_orders': getattr(supplier, 'total_orders', 10),
                'on_time_delivery_rate': getattr(supplier, 'on_time_delivery_rate', 0.8),
                'defect_rate': getattr(supplier, 'defect_rate', 0.05),
                'average_lead_time_days': getattr(supplier, 'average_lead_time_days', 14),
                'price_volatility': getattr(supplier, 'price_volatility', 0.1),
            }
            
            features = self.ml_engine.extract_features('supplier', supplier_data)
            prediction = self.ml_engine.predict(self.model_category, 'gb_classifier', features)
            
            prediction.explanation = self._generate_supplier_risk_explanation(
                prediction.prediction, supplier_data
            )
            
            return prediction
            
        except Exception as e:
            logger.error(f"Error predicting supplier risk: {e}")
            return self._fallback_risk_prediction("supplier", 0.3)
    
    def predict_route_risk(self, route_id: str) -> MLPrediction:
        """Predict risk for a specific route"""
        try:
            route = db.session.get(Route, route_id)
            if not route:
                return self._fallback_risk_prediction("route", 0.3)
            
            # Extract route features
            route_data = {
                'cost_usd': route.cost_usd or 0,
                'distance_km': route.distance_km or 0,
                'estimated_duration_hours': route.estimated_duration_hours or 0,
                'carbon_emissions_kg': route.carbon_emissions_kg or 0,
                'risk_score': route.risk_score or 0,
                'mode': route.mode,
                'carrier': route.carrier,
                'legs': route.legs if hasattr(route, 'legs') else []
            }
            
            features = self.ml_engine.extract_features('route', route_data)
            prediction = self.ml_engine.predict(self.model_category, 'isolation_forest', features)
            
            return prediction
            
        except Exception as e:
            logger.error(f"Error predicting route risk: {e}")
            return self._fallback_risk_prediction("route", 0.3)
    
    def _generate_risk_explanation(self, risk_score: float, shipment_data: Dict) -> str:
        """Generate explanation for risk prediction"""
        risk_level = "low" if risk_score < 0.3 else "medium" if risk_score < 0.7 else "high"
        
        factors = []
        if shipment_data.get('distance_km', 0) > 5000:
            factors.append("long distance")
        if shipment_data.get('cost_usd', 0) > 10000:
            factors.append("high value")
        if len(shipment_data.get('routes', [])) > 3:
            factors.append("complex routing")
        
        factor_text = f" Key factors: {', '.join(factors)}" if factors else ""
        
        return f"Risk level: {risk_level} ({risk_score:.2f}).{factor_text}"
    
    def _generate_supplier_risk_explanation(self, risk_score: float, supplier_data: Dict) -> str:
        """Generate explanation for supplier risk"""
        risk_level = "low" if risk_score < 0.3 else "medium" if risk_score < 0.7 else "high"
        
        factors = []
        if supplier_data.get('reliability_score', 0.7) < 0.6:
            factors.append("low reliability")
        if supplier_data.get('on_time_delivery_rate', 0.8) < 0.7:
            factors.append("delivery issues")
        if supplier_data.get('financial_stability', 0.7) < 0.6:
            factors.append("financial concerns")
        
        factor_text = f" Key concerns: {', '.join(factors)}" if factors else ""
        
        return f"Supplier risk: {risk_level} ({risk_score:.2f}).{factor_text}"
    
    def _fallback_risk_prediction(self, risk_type: str, default_risk: float) -> MLPrediction:
        """Fallback risk prediction"""
        return MLPrediction(
            model_name=f"risk_prediction.fallback",
            prediction=default_risk,
            confidence=0.5,
            feature_importance={},
            explanation=f"Fallback {risk_type} risk assessment: {default_risk:.2f}"
        )

class RouteOptimizationModel:
    """Optimizes shipping routes for cost, time, and risk"""
    
    def __init__(self, ml_engine: MLEngine):
        self.ml_engine = ml_engine
        self.model_category = 'route_optimization'
    
    def optimize_route(self, shipment_id: str, objectives: List[str] = None) -> Dict[str, Any]:
        """Optimize route for multiple objectives"""
        if objectives is None:
            objectives = ['cost', 'time', 'risk']
        
        try:
            shipment = db.session.get(Shipment, shipment_id)
            if not shipment:
                return self._fallback_route_optimization()
            
            route_scores = {}
            recommendations = []
            
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
                
                features = self.ml_engine.extract_features('route', route_data)
                
                # Predict scores for each objective
                scores = {}
                for objective in objectives:
                    if objective == 'cost':
                        pred = self.ml_engine.predict(self.model_category, 'cost_predictor', features)
                        scores['cost'] = 1.0 - min(pred.prediction / 10000, 1.0)  # Normalize
                    elif objective == 'time':
                        pred = self.ml_engine.predict(self.model_category, 'time_predictor', features)
                        scores['time'] = 1.0 - min(pred.prediction / 168, 1.0)  # Normalize to weekly
                    elif objective == 'risk':
                        pred = self.ml_engine.predict(self.model_category, 'risk_predictor', features)
                        scores['risk'] = 1.0 - pred.prediction
                
                # Calculate weighted score
                weighted_score = sum(scores.values()) / len(scores)
                route_scores[route.id] = {
                    'overall_score': weighted_score,
                    'objective_scores': scores,
                    'route_data': route_data
                }
            
            # Find best route
            best_route_id = max(route_scores.keys(), key=lambda x: route_scores[x]['overall_score'])
            
            return {
                'recommended_route_id': best_route_id,
                'optimization_score': route_scores[best_route_id]['overall_score'],
                'all_route_scores': route_scores,
                'objectives_optimized': objectives,
                'explanation': self._generate_optimization_explanation(route_scores, best_route_id)
            }
            
        except Exception as e:
            logger.error(f"Error optimizing route: {e}")
            return self._fallback_route_optimization()
    
    def predict_route_performance(self, route_data: Dict) -> Dict[str, MLPrediction]:
        """Predict performance metrics for a route"""
        try:
            features = self.ml_engine.extract_features('route', route_data)
            
            predictions = {}
            for metric in ['cost_predictor', 'time_predictor', 'risk_predictor']:
                pred = self.ml_engine.predict(self.model_category, metric, features)
                predictions[metric.replace('_predictor', '')] = pred
            
            return predictions
            
        except Exception as e:
            logger.error(f"Error predicting route performance: {e}")
            return {}
    
    def _generate_optimization_explanation(self, route_scores: Dict, best_route_id: str) -> str:
        """Generate explanation for route optimization"""
        best_score = route_scores[best_route_id]['overall_score']
        best_objectives = route_scores[best_route_id]['objective_scores']
        
        best_aspect = max(best_objectives.keys(), key=lambda x: best_objectives[x])
        
        return f"Recommended route optimizes for {best_aspect} with overall score {best_score:.2f}. " \
               f"Strongest performance: {best_aspect} ({best_objectives[best_aspect]:.2f})"
    
    def _fallback_route_optimization(self) -> Dict[str, Any]:
        """Fallback route optimization"""
        return {
            'recommended_route_id': None,
            'optimization_score': 0.5,
            'all_route_scores': {},
            'objectives_optimized': ['cost', 'time', 'risk'],
            'explanation': "Fallback optimization: unable to analyze routes"
        }

class SupplierScoringModel:
    """Scores and ranks suppliers based on multiple criteria"""
    
    def __init__(self, ml_engine: MLEngine):
        self.ml_engine = ml_engine
        self.model_category = 'supplier_scoring'
    
    def score_supplier(self, supplier_id: str) -> MLPrediction:
        """Generate comprehensive supplier score"""
        try:
            supplier = db.session.get(Supplier, supplier_id)
            if not supplier:
                return self._fallback_supplier_score()
            
            supplier_data = {
                'reliability_score': getattr(supplier, 'reliability_score', 0.7),
                'quality_score': getattr(supplier, 'quality_score', 0.7),
                'delivery_performance': getattr(supplier, 'delivery_performance', 0.7),
                'cost_competitiveness': getattr(supplier, 'cost_competitiveness', 0.7),
                'financial_stability': getattr(supplier, 'financial_stability', 0.7),
            }
            
            features = self.ml_engine.extract_features('supplier', supplier_data)
            prediction = self.ml_engine.predict(self.model_category, 'performance_scorer', features)
            
            prediction.explanation = self._generate_supplier_score_explanation(
                prediction.prediction, supplier_data
            )
            
            return prediction
            
        except Exception as e:
            logger.error(f"Error scoring supplier: {e}")
            return self._fallback_supplier_score()
    
    def rank_suppliers(self, supplier_ids: List[str], criteria: List[str] = None) -> List[Dict]:
        """Rank multiple suppliers"""
        if criteria is None:
            criteria = ['reliability', 'quality', 'cost', 'delivery']
        
        supplier_scores = []
        
        for supplier_id in supplier_ids:
            score_prediction = self.score_supplier(supplier_id)
            supplier_scores.append({
                'supplier_id': supplier_id,
                'overall_score': score_prediction.prediction,
                'confidence': score_prediction.confidence,
                'explanation': score_prediction.explanation
            })
        
        # Sort by score (descending)
        supplier_scores.sort(key=lambda x: x['overall_score'], reverse=True)
        
        return supplier_scores
    
    def _generate_supplier_score_explanation(self, score: float, supplier_data: Dict) -> str:
        """Generate explanation for supplier score"""
        score_level = "excellent" if score > 0.8 else "good" if score > 0.6 else "fair" if score > 0.4 else "poor"
        
        strengths = []
        weaknesses = []
        
        for metric, value in supplier_data.items():
            if value > 0.8:
                strengths.append(metric.replace('_', ' '))
            elif value < 0.5:
                weaknesses.append(metric.replace('_', ' '))
        
        explanation = f"Supplier score: {score_level} ({score:.2f})"
        
        if strengths:
            explanation += f". Strengths: {', '.join(strengths[:2])}"
        if weaknesses:
            explanation += f". Areas for improvement: {', '.join(weaknesses[:2])}"
        
        return explanation
    
    def _fallback_supplier_score(self) -> MLPrediction:
        """Fallback supplier scoring"""
        return MLPrediction(
            model_name="supplier_scoring.fallback",
            prediction=0.6,
            confidence=0.5,
            feature_importance={},
            explanation="Fallback supplier score: average performance assumed"
        )

class InventoryOptimizationModel:
    """Optimizes inventory levels and reorder points"""
    
    def __init__(self, ml_engine: MLEngine):
        self.ml_engine = ml_engine
        self.model_category = 'inventory_optimization'
    
    def optimize_inventory_level(self, item_id: str) -> MLPrediction:
        """Optimize inventory level for an item"""
        try:
            inventory = Inventory.query.filter_by(id=item_id).first()
            if not inventory:
                return self._fallback_inventory_optimization()
            
            inventory_data = {
                'current_stock': getattr(inventory, 'current_stock', 100),
                'reorder_point': getattr(inventory, 'reorder_point', 50),
                'max_stock': getattr(inventory, 'max_stock', 200),
                'safety_stock': getattr(inventory, 'safety_stock', 25),
                'unit_cost': getattr(inventory, 'unit_cost', 10),
                'avg_daily_demand': getattr(inventory, 'avg_daily_demand', 5),
                'demand_volatility': getattr(inventory, 'demand_volatility', 0.2),
                'lead_time_days': getattr(inventory, 'lead_time_days', 7),
            }
            
            features = self.ml_engine.extract_features('inventory', inventory_data)
            prediction = self.ml_engine.predict(self.model_category, 'demand_predictor', features)
            
            # Calculate optimal reorder point
            reorder_prediction = self.ml_engine.predict(self.model_category, 'reorder_optimizer', features)
            
            prediction.explanation = self._generate_inventory_explanation(
                prediction.prediction, reorder_prediction.prediction, inventory_data
            )
            
            return prediction
            
        except Exception as e:
            logger.error(f"Error optimizing inventory: {e}")
            return self._fallback_inventory_optimization()
    
    def predict_stockout_risk(self, item_id: str) -> MLPrediction:
        """Predict risk of stockout for an item"""
        try:
            inventory = Inventory.query.filter_by(id=item_id).first()
            if not inventory:
                return self._fallback_stockout_prediction()
            
            inventory_data = {
                'current_stock': getattr(inventory, 'current_stock', 100),
                'avg_daily_demand': getattr(inventory, 'avg_daily_demand', 5),
                'lead_time_days': getattr(inventory, 'lead_time_days', 7),
                'safety_stock': getattr(inventory, 'safety_stock', 25),
                'demand_volatility': getattr(inventory, 'demand_volatility', 0.2),
            }
            
            features = self.ml_engine.extract_features('inventory', inventory_data)
            prediction = self.ml_engine.predict(self.model_category, 'stockout_predictor', features)
            
            prediction.explanation = self._generate_stockout_explanation(
                prediction.prediction, inventory_data
            )
            
            return prediction
            
        except Exception as e:
            logger.error(f"Error predicting stockout risk: {e}")
            return self._fallback_stockout_prediction()
    
    def _generate_inventory_explanation(self, optimal_level: float, reorder_point: float, 
                                      inventory_data: Dict) -> str:
        """Generate explanation for inventory optimization"""
        current = inventory_data.get('current_stock', 100)
        
        if optimal_level > current:
            action = f"increase stock by {optimal_level - current:.0f} units"
        elif optimal_level < current:
            action = f"reduce stock by {current - optimal_level:.0f} units"
        else:
            action = "maintain current stock level"
        
        return f"Optimal inventory: {optimal_level:.0f} units (reorder at {reorder_point:.0f}). " \
               f"Recommendation: {action}"
    
    def _generate_stockout_explanation(self, risk_score: float, inventory_data: Dict) -> str:
        """Generate explanation for stockout risk"""
        current = inventory_data.get('current_stock', 100)
        daily_demand = inventory_data.get('avg_daily_demand', 5)
        days_of_stock = current / daily_demand if daily_demand > 0 else 999
        
        risk_level = "low" if risk_score < 0.3 else "medium" if risk_score < 0.7 else "high"
        
        return f"Stockout risk: {risk_level} ({risk_score:.2f}). " \
               f"Current stock covers {days_of_stock:.1f} days of demand"
    
    def _fallback_inventory_optimization(self) -> MLPrediction:
        """Fallback inventory optimization"""
        return MLPrediction(
            model_name="inventory_optimization.fallback",
            prediction=100.0,
            confidence=0.5,
            feature_importance={},
            explanation="Fallback inventory optimization: maintain baseline stock"
        )
    
    def _fallback_stockout_prediction(self) -> MLPrediction:
        """Fallback stockout prediction"""
        return MLPrediction(
            model_name="inventory_optimization.fallback",
            prediction=0.3,
            confidence=0.5,
            feature_importance={},
            explanation="Fallback stockout risk: medium risk assumed"
        )

# Additional model classes for completeness
class PriceOptimizationModel:
    """Optimizes pricing strategies"""
    
    def __init__(self, ml_engine: MLEngine):
        self.ml_engine = ml_engine
        self.model_category = 'price_optimization'

class DisruptionDetectionModel:
    """Detects potential supply chain disruptions"""
    
    def __init__(self, ml_engine: MLEngine):
        self.ml_engine = ml_engine
        self.model_category = 'disruption_detection'

class PerformanceAnalyticsModel:
    """Analyzes supply chain performance metrics"""
    
    def __init__(self, ml_engine: MLEngine):
        self.ml_engine = ml_engine
        self.model_category = 'performance_analytics'
