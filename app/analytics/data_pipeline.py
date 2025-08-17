"""
Data Pipeline for ML Feature Engineering and Data Processing
"""
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import json
from collections import defaultdict

from app import db
from app.models import (
    Shipment, Route, Supplier, Inventory, PurchaseOrder, Alert,
    Recommendation, User, Workspace
)

logger = logging.getLogger(__name__)

class DataPipeline:
    """Handles data extraction, transformation, and loading for ML models"""
    
    def __init__(self):
        self.name = 'data_pipeline'
        self.feature_cache = {}
        self.cache_ttl = 3600  # 1 hour cache
    
    def extract_training_data(self, model_category: str, workspace_id: Optional[str] = None,
                            days_back: int = 90) -> Tuple[np.ndarray, np.ndarray]:
        """Extract training data for a specific model category"""
        try:
            # Get cutoff date
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)
            
            if model_category == 'demand_forecast':
                return self._extract_demand_training_data(workspace_id, cutoff_date)
            elif model_category == 'risk_prediction':
                return self._extract_risk_training_data(workspace_id, cutoff_date)
            elif model_category == 'route_optimization':
                return self._extract_route_training_data(workspace_id, cutoff_date)
            elif model_category == 'supplier_scoring':
                return self._extract_supplier_training_data(workspace_id, cutoff_date)
            elif model_category == 'inventory_optimization':
                return self._extract_inventory_training_data(workspace_id, cutoff_date)
            else:
                logger.warning(f"Unknown model category for training data: {model_category}")
                return np.array([]), np.array([])
                
        except Exception as e:
            logger.error(f"Error extracting training data for {model_category}: {e}")
            return np.array([]), np.array([])
    
    def _extract_demand_training_data(self, workspace_id: Optional[str], 
                                    cutoff_date: datetime) -> Tuple[np.ndarray, np.ndarray]:
        """Extract training data for demand forecasting"""
        # Simulate demand training data
        # In a real implementation, this would query actual historical demand data
        
        num_samples = 1000
        features = []
        targets = []
        
        for _ in range(num_samples):
            # Simulate features: [base_demand, seasonality, trend, day_of_week, month, etc.]
            base_demand = np.random.normal(100, 20)
            seasonality = np.random.normal(1.0, 0.1)
            trend = np.random.normal(1.0, 0.05)
            day_of_week = np.random.randint(0, 7)
            month = np.random.randint(1, 13)
            
            feature_row = [base_demand, seasonality, trend, day_of_week, month, 30]  # 30-day horizon
            target = base_demand * seasonality * trend * (1 + np.random.normal(0, 0.1))
            
            features.append(feature_row)
            targets.append(target)
        
        return np.array(features), np.array(targets)
    
    def _extract_risk_training_data(self, workspace_id: Optional[str], 
                                  cutoff_date: datetime) -> Tuple[np.ndarray, np.ndarray]:
        """Extract training data for risk prediction"""
        query = Shipment.query.filter(Shipment.created_at >= cutoff_date)
        if workspace_id:
            query = query.filter(Shipment.workspace_id == workspace_id)
        
        shipments = query.all()
        
        features = []
        targets = []
        
        for shipment in shipments:
            try:
                # Extract features
                total_cost = sum(r.cost_usd or 0 for r in shipment.routes)
                total_distance = sum(r.distance_km or 0 for r in shipment.routes)
                total_duration = sum(r.estimated_duration_hours or 0 for r in shipment.routes)
                
                feature_row = [
                    total_cost,
                    total_distance,
                    total_duration,
                    len(shipment.routes),
                    shipment.created_at.weekday(),
                    shipment.created_at.month,
                    shipment.origin_lat or 0,
                    shipment.origin_lon or 0,
                    shipment.destination_lat or 0,
                    shipment.destination_lon or 0,
                ]
                
                # Target: actual risk score or derived risk
                risk_score = shipment.risk_score or self._calculate_historical_risk(shipment)
                
                features.append(feature_row)
                targets.append(risk_score)
                
            except Exception as e:
                logger.warning(f"Error processing shipment {shipment.id} for training: {e}")
                continue
        
        # If no real data, generate synthetic training data
        if len(features) < 50:
            return self._generate_synthetic_risk_data()
        
        return np.array(features), np.array(targets)
    
    def _extract_route_training_data(self, workspace_id: Optional[str], 
                                   cutoff_date: datetime) -> Tuple[np.ndarray, np.ndarray]:
        """Extract training data for route optimization"""
        query = Route.query.join(Shipment).filter(Shipment.created_at >= cutoff_date)
        if workspace_id:
            query = query.filter(Shipment.workspace_id == workspace_id)
        
        routes = query.all()
        
        features = []
        targets = []
        
        for route in routes:
            try:
                feature_row = [
                    route.cost_usd or 0,
                    route.distance_km or 0,
                    route.estimated_duration_hours or 0,
                    route.carbon_emissions_kg or 0,
                    len(route.mode or ''),  # Mode complexity
                    len(route.carrier or ''),  # Carrier name length as proxy
                ]
                
                # Target: optimization score (higher is better)
                optimization_score = self._calculate_route_optimization_score(route)
                
                features.append(feature_row)
                targets.append(optimization_score)
                
            except Exception as e:
                logger.warning(f"Error processing route {route.id} for training: {e}")
                continue
        
        if len(features) < 50:
            return self._generate_synthetic_route_data()
        
        return np.array(features), np.array(targets)
    
    def _extract_supplier_training_data(self, workspace_id: Optional[str], 
                                      cutoff_date: datetime) -> Tuple[np.ndarray, np.ndarray]:
        """Extract training data for supplier scoring"""
        query = Supplier.query.filter(Supplier.created_at >= cutoff_date)
        if workspace_id:
            query = query.filter(Supplier.workspace_id == workspace_id)
        
        suppliers = query.all()
        
        features = []
        targets = []
        
        for supplier in suppliers:
            try:
                feature_row = [
                    getattr(supplier, 'reliability_score', 0.7),
                    getattr(supplier, 'quality_score', 0.7),
                    getattr(supplier, 'delivery_performance', 0.7),
                    getattr(supplier, 'cost_competitiveness', 0.7),
                    getattr(supplier, 'financial_stability', 0.7),
                    len(supplier.name or ''),
                    len(supplier.contact_info or '{}'),
                ]
                
                # Target: overall supplier performance score
                performance_score = self._calculate_supplier_performance(supplier)
                
                features.append(feature_row)
                targets.append(performance_score)
                
            except Exception as e:
                logger.warning(f"Error processing supplier {supplier.id} for training: {e}")
                continue
        
        if len(features) < 20:
            return self._generate_synthetic_supplier_data()
        
        return np.array(features), np.array(targets)
    
    def _extract_inventory_training_data(self, workspace_id: Optional[str], 
                                       cutoff_date: datetime) -> Tuple[np.ndarray, np.ndarray]:
        """Extract training data for inventory optimization"""
        query = Inventory.query.filter(Inventory.created_at >= cutoff_date)
        if workspace_id:
            query = query.filter(Inventory.workspace_id == workspace_id)
        
        inventory_items = query.all()
        
        features = []
        targets = []
        
        for item in inventory_items:
            try:
                feature_row = [
                    getattr(item, 'current_stock', 100),
                    getattr(item, 'reorder_point', 50),
                    getattr(item, 'max_stock', 200),
                    getattr(item, 'unit_cost', 10),
                    getattr(item, 'avg_daily_demand', 5),
                    getattr(item, 'lead_time_days', 7),
                ]
                
                # Target: optimal stock level
                optimal_level = self._calculate_optimal_inventory(item)
                
                features.append(feature_row)
                targets.append(optimal_level)
                
            except Exception as e:
                logger.warning(f"Error processing inventory {item.id} for training: {e}")
                continue
        
        if len(features) < 20:
            return self._generate_synthetic_inventory_data()
        
        return np.array(features), np.array(targets)
    
    def _calculate_historical_risk(self, shipment) -> float:
        """Calculate historical risk score for a shipment"""
        # Simple heuristic for historical risk
        risk_factors = []
        
        # Distance-based risk
        total_distance = sum(r.distance_km or 0 for r in shipment.routes)
        distance_risk = min(total_distance / 10000, 1.0)  # Normalize to 10k km
        risk_factors.append(distance_risk)
        
        # Cost-based risk
        total_cost = sum(r.cost_usd or 0 for r in shipment.routes)
        cost_risk = min(total_cost / 50000, 1.0)  # Normalize to $50k
        risk_factors.append(cost_risk)
        
        # Route complexity risk
        complexity_risk = min(len(shipment.routes) / 5, 1.0)  # Normalize to 5 routes
        risk_factors.append(complexity_risk)
        
        return np.mean(risk_factors)
    
    def _calculate_route_optimization_score(self, route) -> float:
        """Calculate optimization score for a route"""
        # Higher score = better optimized
        cost_score = 1.0 - min((route.cost_usd or 1000) / 10000, 1.0)
        time_score = 1.0 - min((route.estimated_duration_hours or 24) / 168, 1.0)  # Week normalize
        
        return (cost_score + time_score) / 2
    
    def _calculate_supplier_performance(self, supplier) -> float:
        """Calculate overall supplier performance score"""
        scores = [
            getattr(supplier, 'reliability_score', 0.7),
            getattr(supplier, 'quality_score', 0.7),
            getattr(supplier, 'delivery_performance', 0.7),
            getattr(supplier, 'cost_competitiveness', 0.7),
            getattr(supplier, 'financial_stability', 0.7),
        ]
        return np.mean(scores)
    
    def _calculate_optimal_inventory(self, inventory_item) -> float:
        """Calculate optimal inventory level"""
        # Simple economic order quantity approximation
        daily_demand = getattr(inventory_item, 'avg_daily_demand', 5)
        lead_time = getattr(inventory_item, 'lead_time_days', 7)
        safety_factor = 1.5
        
        return daily_demand * lead_time * safety_factor
    
    def _generate_synthetic_risk_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """Generate synthetic risk training data"""
        num_samples = 500
        features = []
        targets = []
        
        for _ in range(num_samples):
            cost = np.random.exponential(5000)
            distance = np.random.exponential(2000)
            duration = np.random.exponential(48)
            num_routes = np.random.poisson(2) + 1
            
            feature_row = [cost, distance, duration, num_routes, 
                          np.random.randint(0, 7), np.random.randint(1, 13),
                          np.random.uniform(-90, 90), np.random.uniform(-180, 180),
                          np.random.uniform(-90, 90), np.random.uniform(-180, 180)]
            
            # Risk increases with cost, distance, duration, and complexity
            risk = (cost/10000 + distance/5000 + duration/100 + num_routes/5) / 4
            risk = min(max(risk + np.random.normal(0, 0.1), 0), 1)
            
            features.append(feature_row)
            targets.append(risk)
        
        return np.array(features), np.array(targets)
    
    def _generate_synthetic_route_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """Generate synthetic route training data"""
        num_samples = 300
        features = []
        targets = []
        
        for _ in range(num_samples):
            cost = np.random.exponential(3000)
            distance = np.random.exponential(1500)
            duration = np.random.exponential(36)
            emissions = distance * 0.1 + np.random.normal(0, 10)
            
            feature_row = [cost, distance, duration, emissions, 3, 7]  # mode/carrier length
            
            # Optimization score: lower cost and time are better
            score = 1.0 - (cost/10000 + duration/100) / 2
            score = max(min(score + np.random.normal(0, 0.1), 1), 0)
            
            features.append(feature_row)
            targets.append(score)
        
        return np.array(features), np.array(targets)
    
    def _generate_synthetic_supplier_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """Generate synthetic supplier training data"""
        num_samples = 200
        features = []
        targets = []
        
        for _ in range(num_samples):
            reliability = np.random.beta(8, 3)
            quality = np.random.beta(7, 3)
            delivery = np.random.beta(6, 4)
            cost_comp = np.random.beta(5, 5)
            financial = np.random.beta(7, 3)
            
            feature_row = [reliability, quality, delivery, cost_comp, financial, 
                          np.random.randint(5, 20), np.random.randint(10, 100)]
            
            # Overall performance is weighted average
            performance = (reliability * 0.25 + quality * 0.25 + delivery * 0.2 + 
                          cost_comp * 0.15 + financial * 0.15)
            
            features.append(feature_row)
            targets.append(performance)
        
        return np.array(features), np.array(targets)
    
    def _generate_synthetic_inventory_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """Generate synthetic inventory training data"""
        num_samples = 150
        features = []
        targets = []
        
        for _ in range(num_samples):
            current = np.random.randint(0, 500)
            reorder = np.random.randint(20, 100)
            max_stock = np.random.randint(100, 1000)
            unit_cost = np.random.exponential(15)
            daily_demand = np.random.exponential(8)
            lead_time = np.random.randint(1, 30)
            
            feature_row = [current, reorder, max_stock, unit_cost, daily_demand, lead_time]
            
            # Optimal level based on demand and lead time
            optimal = daily_demand * lead_time * 1.5 + np.random.normal(0, 10)
            optimal = max(optimal, 0)
            
            features.append(feature_row)
            targets.append(optimal)
        
        return np.array(features), np.array(targets)

class FeatureEngineering:
    """Advanced feature engineering for supply chain data"""
    
    def __init__(self):
        self.feature_transformers = {}
        self.temporal_features = ['hour', 'day_of_week', 'month', 'quarter', 'is_weekend']
        self.geographic_features = ['lat', 'lon', 'distance', 'region']
    
    def engineer_temporal_features(self, timestamp: datetime) -> Dict[str, float]:
        """Create temporal features from timestamp"""
        return {
            'hour': timestamp.hour,
            'day_of_week': timestamp.weekday(),
            'month': timestamp.month,
            'quarter': (timestamp.month - 1) // 3 + 1,
            'is_weekend': float(timestamp.weekday() >= 5),
            'is_month_end': float(timestamp.day >= 28),
            'is_quarter_end': float(timestamp.month % 3 == 0),
        }
    
    def engineer_geographic_features(self, lat1: float, lon1: float, 
                                   lat2: float, lon2: float) -> Dict[str, float]:
        """Create geographic features from coordinates"""
        # Calculate distance using Haversine formula
        def haversine_distance(lat1, lon1, lat2, lon2):
            R = 6371  # Earth's radius in km
            
            lat1_rad = np.radians(lat1)
            lat2_rad = np.radians(lat2)
            delta_lat = np.radians(lat2 - lat1)
            delta_lon = np.radians(lon2 - lon1)
            
            a = (np.sin(delta_lat/2)**2 + 
                 np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(delta_lon/2)**2)
            c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
            
            return R * c
        
        distance = haversine_distance(lat1, lon1, lat2, lon2)
        
        return {
            'distance_km': distance,
            'lat_diff': abs(lat2 - lat1),
            'lon_diff': abs(lon2 - lon1),
            'origin_hemisphere': 'north' if lat1 >= 0 else 'south',
            'dest_hemisphere': 'north' if lat2 >= 0 else 'south',
            'crosses_equator': float((lat1 >= 0) != (lat2 >= 0)),
            'crosses_dateline': float(abs(lon2 - lon1) > 180),
        }
    
    def engineer_route_complexity_features(self, routes: List[Dict]) -> Dict[str, float]:
        """Create route complexity features"""
        if not routes:
            return {'route_complexity': 0}
        
        # Count different modes and carriers
        modes = set(r.get('mode', 'unknown') for r in routes)
        carriers = set(r.get('carrier', 'unknown') for r in routes)
        
        # Calculate transfer complexity
        mode_changes = len(modes) - 1
        carrier_changes = len(carriers) - 1
        
        return {
            'num_routes': len(routes),
            'num_modes': len(modes),
            'num_carriers': len(carriers),
            'mode_changes': mode_changes,
            'carrier_changes': carrier_changes,
            'route_complexity': (mode_changes + carrier_changes + len(routes)) / 10,
            'has_multimodal': float(len(modes) > 1),
            'has_sea_route': float('sea' in modes),
            'has_air_route': float('air' in modes),
            'has_road_route': float('road' in modes),
        }
    
    def engineer_supplier_relationship_features(self, supplier_history: List[Dict]) -> Dict[str, float]:
        """Create supplier relationship features"""
        if not supplier_history:
            return {'relationship_strength': 0}
        
        # Calculate relationship metrics
        total_orders = len(supplier_history)
        total_value = sum(h.get('order_value', 0) for h in supplier_history)
        avg_order_value = total_value / total_orders if total_orders > 0 else 0
        
        # Calculate performance metrics
        on_time_orders = sum(1 for h in supplier_history if h.get('on_time', True))
        on_time_rate = on_time_orders / total_orders if total_orders > 0 else 1.0
        
        # Calculate recency
        if supplier_history:
            last_order = max(h.get('order_date', datetime.min) for h in supplier_history)
            days_since_last = (datetime.utcnow() - last_order).days
        else:
            days_since_last = 9999
        
        return {
            'total_orders': total_orders,
            'avg_order_value': avg_order_value,
            'total_value': total_value,
            'on_time_rate': on_time_rate,
            'days_since_last_order': days_since_last,
            'relationship_strength': min(total_orders / 50, 1.0),
            'order_frequency': total_orders / max(days_since_last / 30, 1),
            'value_tier': min(total_value / 100000, 3.0),  # 0-3 scale
        }
    
    def create_interaction_features(self, features: Dict[str, float]) -> Dict[str, float]:
        """Create interaction features between key variables"""
        interactions = {}
        
        # Cost and time interactions
        if 'cost_usd' in features and 'duration_hours' in features:
            interactions['cost_per_hour'] = features['cost_usd'] / max(features['duration_hours'], 1)
        
        # Distance and cost interactions
        if 'distance_km' in features and 'cost_usd' in features:
            interactions['cost_per_km'] = features['cost_usd'] / max(features['distance_km'], 1)
        
        # Risk and value interactions
        if 'risk_score' in features and 'cost_usd' in features:
            interactions['risk_adjusted_value'] = features['cost_usd'] * (1 + features['risk_score'])
        
        # Efficiency metrics
        if 'distance_km' in features and 'duration_hours' in features:
            interactions['avg_speed_kmh'] = features['distance_km'] / max(features['duration_hours'], 1)
        
        return interactions
    
    def normalize_features(self, features: Dict[str, float], 
                         feature_ranges: Dict[str, Tuple[float, float]]) -> Dict[str, float]:
        """Normalize features to 0-1 range"""
        normalized = {}
        
        for feature, value in features.items():
            if feature in feature_ranges:
                min_val, max_val = feature_ranges[feature]
                if max_val > min_val:
                    normalized[feature] = (value - min_val) / (max_val - min_val)
                else:
                    normalized[feature] = 0.5  # Default for constant features
            else:
                normalized[feature] = value  # Keep as-is if no range provided
        
        return normalized
