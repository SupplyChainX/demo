"""
ML Engine - Central machine learning orchestration for supply chain optimization
"""
import logging
import numpy as np
import pandas as pd
import joblib
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# ML Libraries
try:
    import sklearn
    from sklearn.model_selection import train_test_split, GridSearchCV, TimeSeriesSplit
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor, IsolationForest
    from sklearn.linear_model import LinearRegression, Ridge, Lasso, ElasticNet
    from sklearn.preprocessing import StandardScaler, MinMaxScaler, LabelEncoder
    from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
    from sklearn.cluster import KMeans, DBSCAN
    import xgboost as xgb
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from flask import current_app
from app import db
from app.models import (
    Shipment, Route, Supplier, PurchaseOrder, Inventory, Alert,
    Recommendation, RecommendationType, User, Workspace
)

logger = logging.getLogger(__name__)

@dataclass
class ModelMetrics:
    """Model performance metrics"""
    mae: float
    mse: float
    rmse: float
    r2: float
    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None

@dataclass
class MLPrediction:
    """ML prediction result"""
    model_name: str
    prediction: Union[float, List[float], Dict[str, float]]
    confidence: float
    feature_importance: Dict[str, float]
    prediction_interval: Optional[Tuple[float, float]] = None
    explanation: Optional[str] = None
    timestamp: datetime = datetime.utcnow()

class MLEngine:
    """Central ML engine for supply chain predictive analytics"""
    
    def __init__(self):
        self.name = 'ml_engine'
        self.models = {}
        self.scalers = {}
        self.feature_extractors = {}
        self.model_metadata = {}
        self.model_dir = Path(current_app.config.get('MODEL_DIR', 'models'))
        self.model_dir.mkdir(exist_ok=True)
        
        # Initialize models if sklearn is available
        if SKLEARN_AVAILABLE:
            self._initialize_models()
            logger.info("ML Engine initialized with sklearn support")
        else:
            logger.warning("ML Engine initialized without sklearn (models disabled)")
    
    def _initialize_models(self):
        """Initialize all ML models"""
        try:
            # Demand Forecasting Models
            self.models['demand_forecast'] = {
                'linear': LinearRegression(),
                'rf': RandomForestRegressor(n_estimators=100, random_state=42),
                'xgb': xgb.XGBRegressor(objective='reg:squarederror', random_state=42) if 'xgb' in globals() else None,
                'gb': GradientBoostingRegressor(n_estimators=100, random_state=42)
            }
            
            # Risk Prediction Models
            self.models['risk_prediction'] = {
                'rf_classifier': sklearn.ensemble.RandomForestClassifier(n_estimators=100, random_state=42),
                'isolation_forest': IsolationForest(contamination=0.1, random_state=42),
                'gb_classifier': sklearn.ensemble.GradientBoostingClassifier(n_estimators=100, random_state=42)
            }
            
            # Route Optimization Models
            self.models['route_optimization'] = {
                'cost_predictor': RandomForestRegressor(n_estimators=100, random_state=42),
                'time_predictor': GradientBoostingRegressor(n_estimators=100, random_state=42),
                'risk_predictor': RandomForestRegressor(n_estimators=100, random_state=42)
            }
            
            # Supplier Scoring Models
            self.models['supplier_scoring'] = {
                'performance_scorer': RandomForestRegressor(n_estimators=100, random_state=42),
                'reliability_scorer': GradientBoostingRegressor(n_estimators=100, random_state=42),
                'risk_scorer': sklearn.ensemble.RandomForestClassifier(n_estimators=100, random_state=42)
            }
            
            # Inventory Optimization Models
            self.models['inventory_optimization'] = {
                'demand_predictor': RandomForestRegressor(n_estimators=100, random_state=42),
                'stockout_predictor': sklearn.ensemble.RandomForestClassifier(n_estimators=100, random_state=42),
                'reorder_optimizer': GradientBoostingRegressor(n_estimators=100, random_state=42)
            }
            
            # Price Optimization Models
            self.models['price_optimization'] = {
                'price_predictor': RandomForestRegressor(n_estimators=100, random_state=42),
                'elasticity_model': LinearRegression(),
                'competition_model': GradientBoostingRegressor(n_estimators=100, random_state=42)
            }
            
            # Disruption Detection Models
            self.models['disruption_detection'] = {
                'anomaly_detector': IsolationForest(contamination=0.1, random_state=42),
                'pattern_classifier': sklearn.ensemble.RandomForestClassifier(n_estimators=100, random_state=42),
                'time_series_detector': sklearn.ensemble.GradientBoostingClassifier(n_estimators=100, random_state=42)
            }
            
            # Performance Analytics Models
            self.models['performance_analytics'] = {
                'kpi_predictor': RandomForestRegressor(n_estimators=100, random_state=42),
                'trend_analyzer': LinearRegression(),
                'efficiency_scorer': GradientBoostingRegressor(n_estimators=100, random_state=42)
            }
            
            # Initialize scalers
            for model_category in self.models.keys():
                self.scalers[model_category] = {
                    'standard': StandardScaler(),
                    'minmax': MinMaxScaler()
                }
            
            logger.info(f"Initialized {len(self.models)} model categories")
            
        except Exception as e:
            logger.error(f"Error initializing ML models: {e}")
    
    def extract_features(self, data_type: str, data: Dict[str, Any]) -> np.ndarray:
        """Extract features from raw data"""
        try:
            if data_type == 'shipment':
                return self._extract_shipment_features(data)
            elif data_type == 'supplier':
                return self._extract_supplier_features(data)
            elif data_type == 'route':
                return self._extract_route_features(data)
            elif data_type == 'inventory':
                return self._extract_inventory_features(data)
            elif data_type == 'purchase_order':
                return self._extract_po_features(data)
            else:
                logger.warning(f"Unknown data type for feature extraction: {data_type}")
                return np.array([])
                
        except Exception as e:
            logger.error(f"Error extracting features for {data_type}: {e}")
            return np.array([])
    
    def _extract_shipment_features(self, shipment_data: Dict[str, Any]) -> np.ndarray:
        """Extract features from shipment data"""
        features = []
        
        # Basic shipment features
        features.extend([
            shipment_data.get('cost_usd', 0),
            shipment_data.get('distance_km', 0),
            shipment_data.get('estimated_duration_hours', 0),
            shipment_data.get('carbon_emissions_kg', 0),
            shipment_data.get('risk_score', 0),
            shipment_data.get('weight_kg', 0),
            shipment_data.get('volume_m3', 0)
        ])
        
        # Route complexity features
        routes = shipment_data.get('routes', [])
        features.extend([
            len(routes),  # Number of route alternatives
            len([r for r in routes if r.get('mode') == 'sea']),  # Sea routes
            len([r for r in routes if r.get('mode') == 'air']),  # Air routes
            len([r for r in routes if r.get('mode') == 'road']),  # Road routes
        ])
        
        # Temporal features
        created_at = shipment_data.get('created_at', datetime.utcnow())
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        
        features.extend([
            created_at.weekday(),  # Day of week
            created_at.month,      # Month
            created_at.hour,       # Hour of day
            (datetime.utcnow() - created_at).days  # Age in days
        ])
        
        # Geographic features (if available)
        origin_lat = shipment_data.get('origin_lat', 0)
        origin_lon = shipment_data.get('origin_lon', 0)
        dest_lat = shipment_data.get('destination_lat', 0)
        dest_lon = shipment_data.get('destination_lon', 0)
        
        features.extend([
            origin_lat, origin_lon, dest_lat, dest_lon,
            abs(dest_lat - origin_lat),  # Latitude difference
            abs(dest_lon - origin_lon),  # Longitude difference
        ])
        
        return np.array(features)
    
    def _extract_supplier_features(self, supplier_data: Dict[str, Any]) -> np.ndarray:
        """Extract features from supplier data"""
        features = []
        
        # Basic supplier metrics
        features.extend([
            supplier_data.get('reliability_score', 0.5),
            supplier_data.get('quality_score', 0.5),
            supplier_data.get('delivery_performance', 0.5),
            supplier_data.get('cost_competitiveness', 0.5),
            supplier_data.get('financial_stability', 0.5),
        ])
        
        # Historical performance
        features.extend([
            supplier_data.get('total_orders', 0),
            supplier_data.get('on_time_delivery_rate', 0.5),
            supplier_data.get('defect_rate', 0.1),
            supplier_data.get('average_lead_time_days', 14),
            supplier_data.get('price_volatility', 0.1),
        ])
        
        # Risk factors
        features.extend([
            supplier_data.get('geographic_risk', 0.3),
            supplier_data.get('political_risk', 0.3),
            supplier_data.get('financial_risk', 0.3),
            supplier_data.get('operational_risk', 0.3),
            supplier_data.get('compliance_score', 0.8),
        ])
        
        # Capacity and scale
        features.extend([
            supplier_data.get('production_capacity', 1000),
            supplier_data.get('warehouse_capacity', 500),
            supplier_data.get('employee_count', 50),
            supplier_data.get('years_in_business', 5),
            supplier_data.get('certification_count', 2),
        ])
        
        return np.array(features)
    
    def _extract_route_features(self, route_data: Dict[str, Any]) -> np.ndarray:
        """Extract features from route data"""
        features = []
        
        # Basic route metrics
        features.extend([
            route_data.get('cost_usd', 0),
            route_data.get('distance_km', 0),
            route_data.get('estimated_duration_hours', 0),
            route_data.get('carbon_emissions_kg', 0),
            route_data.get('risk_score', 0),
        ])
        
        # Route complexity
        legs = route_data.get('legs', [])
        features.extend([
            len(legs),  # Number of legs
            len([l for l in legs if l.get('mode') == 'sea']),  # Sea legs
            len([l for l in legs if l.get('mode') == 'air']),  # Air legs
            len([l for l in legs if l.get('mode') == 'road']),  # Road legs
            len([l for l in legs if l.get('mode') == 'rail']),  # Rail legs
        ])
        
        # Geographic spread
        if legs:
            lats = [l.get('origin_lat', 0) for l in legs] + [legs[-1].get('destination_lat', 0)]
            lons = [l.get('origin_lon', 0) for l in legs] + [legs[-1].get('destination_lon', 0)]
            
            features.extend([
                max(lats) - min(lats),  # Latitude span
                max(lons) - min(lons),  # Longitude span
                np.mean(lats),          # Average latitude
                np.mean(lons),          # Average longitude
            ])
        else:
            features.extend([0, 0, 0, 0])
        
        # Carrier diversity
        carriers = list(set([l.get('carrier', 'unknown') for l in legs]))
        features.extend([
            len(carriers),  # Number of unique carriers
            len([c for c in carriers if 'dhl' in c.lower()]),  # DHL segments
            len([c for c in carriers if 'fedex' in c.lower()]),  # FedEx segments
            len([c for c in carriers if 'maersk' in c.lower()]),  # Maersk segments
        ])
        
        return np.array(features)
    
    def _extract_inventory_features(self, inventory_data: Dict[str, Any]) -> np.ndarray:
        """Extract features from inventory data"""
        features = []
        
        # Current inventory state
        features.extend([
            inventory_data.get('current_stock', 0),
            inventory_data.get('reorder_point', 0),
            inventory_data.get('max_stock', 0),
            inventory_data.get('safety_stock', 0),
            inventory_data.get('unit_cost', 0),
        ])
        
        # Demand patterns
        features.extend([
            inventory_data.get('avg_daily_demand', 0),
            inventory_data.get('demand_volatility', 0),
            inventory_data.get('seasonal_factor', 1.0),
            inventory_data.get('trend_factor', 1.0),
            inventory_data.get('lead_time_days', 7),
        ])
        
        # Historical performance
        features.extend([
            inventory_data.get('stockout_frequency', 0),
            inventory_data.get('excess_inventory_days', 0),
            inventory_data.get('turnover_rate', 12),
            inventory_data.get('service_level', 0.95),
            inventory_data.get('carrying_cost_rate', 0.2),
        ])
        
        # Product characteristics
        features.extend([
            inventory_data.get('product_value', 100),
            inventory_data.get('shelf_life_days', 365),
            inventory_data.get('storage_requirements', 1),  # 1=normal, 2=special
            inventory_data.get('handling_complexity', 1),   # 1=simple, 5=complex
            inventory_data.get('supplier_count', 1),
        ])
        
        return np.array(features)
    
    def _extract_po_features(self, po_data: Dict[str, Any]) -> np.ndarray:
        """Extract features from purchase order data"""
        features = []
        
        # Basic PO metrics
        features.extend([
            po_data.get('total_amount', 0),
            po_data.get('item_count', 0),
            po_data.get('requested_delivery_days', 30),
            po_data.get('priority_score', 0.5),
            po_data.get('supplier_score', 0.5),
        ])
        
        # Temporal features
        created_at = po_data.get('created_at', datetime.utcnow())
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        
        requested_date = po_data.get('requested_delivery_date', created_at + timedelta(days=30))
        if isinstance(requested_date, str):
            requested_date = datetime.fromisoformat(requested_date.replace('Z', '+00:00'))
        
        features.extend([
            created_at.weekday(),  # Day of week
            created_at.month,      # Month
            (requested_date - created_at).days,  # Lead time requested
            (datetime.utcnow() - created_at).days,  # Age in days
        ])
        
        # Risk and complexity features
        features.extend([
            po_data.get('geographic_risk', 0.3),
            po_data.get('supplier_risk', 0.3),
            po_data.get('market_risk', 0.3),
            po_data.get('contract_complexity', 0.5),
            po_data.get('regulatory_requirements', 0.5),
        ])
        
        return np.array(features)
    
    def train_model(self, model_category: str, model_name: str, X: np.ndarray, y: np.ndarray, 
                   validation_split: float = 0.2) -> ModelMetrics:
        """Train a specific model with data"""
        if not SKLEARN_AVAILABLE:
            logger.error("Cannot train model: sklearn not available")
            return None
        
        try:
            if model_category not in self.models:
                logger.error(f"Unknown model category: {model_category}")
                return None
            
            if model_name not in self.models[model_category]:
                logger.error(f"Unknown model {model_name} in category {model_category}")
                return None
            
            model = self.models[model_category][model_name]
            if model is None:
                logger.error(f"Model {model_name} not available")
                return None
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=validation_split, random_state=42
            )
            
            # Scale features
            scaler = self.scalers[model_category]['standard']
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # Train model
            model.fit(X_train_scaled, y_train)
            
            # Make predictions
            y_pred = model.predict(X_test_scaled)
            
            # Calculate metrics
            metrics = self._calculate_metrics(y_test, y_pred, model_category)
            
            # Save model and scaler
            self._save_model(model_category, model_name, model, scaler, metrics)
            
            logger.info(f"Trained {model_category}.{model_name} - R2: {metrics.r2:.3f}, RMSE: {metrics.rmse:.3f}")
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error training model {model_category}.{model_name}: {e}")
            return None
    
    def predict(self, model_category: str, model_name: str, features: np.ndarray, 
               include_confidence: bool = True) -> MLPrediction:
        """Make prediction using trained model"""
        if not SKLEARN_AVAILABLE:
            logger.error("Cannot predict: sklearn not available")
            return None
        
        try:
            if model_category not in self.models:
                return self._fallback_prediction(model_category, features)
            
            model = self.models[model_category].get(model_name)
            if model is None:
                return self._fallback_prediction(model_category, features)
            
            # Scale features
            scaler = self.scalers[model_category]['standard']
            features_scaled = scaler.transform(features.reshape(1, -1))
            
            # Make prediction
            prediction = model.predict(features_scaled)[0]
            
            # Calculate confidence (simplified)
            confidence = self._calculate_confidence(model, features_scaled, model_category)
            
            # Get feature importance
            feature_importance = self._get_feature_importance(model, model_category)
            
            return MLPrediction(
                model_name=f"{model_category}.{model_name}",
                prediction=float(prediction),
                confidence=confidence,
                feature_importance=feature_importance,
                explanation=self._generate_explanation(model_category, prediction, feature_importance)
            )
            
        except Exception as e:
            logger.error(f"Error making prediction with {model_category}.{model_name}: {e}")
            return self._fallback_prediction(model_category, features)
    
    def _calculate_metrics(self, y_true, y_pred, model_category: str) -> ModelMetrics:
        """Calculate model performance metrics"""
        mae = mean_absolute_error(y_true, y_pred)
        mse = mean_squared_error(y_true, y_pred)
        rmse = np.sqrt(mse)
        r2 = r2_score(y_true, y_pred)
        
        metrics = ModelMetrics(mae=mae, mse=mse, rmse=rmse, r2=r2)
        
        # Add classification metrics if applicable
        if 'classifier' in model_category or 'detection' in model_category:
            from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
            try:
                metrics.accuracy = accuracy_score(y_true, (y_pred > 0.5).astype(int))
                metrics.precision = precision_score(y_true, (y_pred > 0.5).astype(int), average='weighted')
                metrics.recall = recall_score(y_true, (y_pred > 0.5).astype(int), average='weighted')
                metrics.f1_score = f1_score(y_true, (y_pred > 0.5).astype(int), average='weighted')
            except:
                pass
        
        return metrics
    
    def _calculate_confidence(self, model, features_scaled: np.ndarray, model_category: str) -> float:
        """Calculate prediction confidence"""
        try:
            # For ensemble models, use prediction variance
            if hasattr(model, 'estimators_'):
                predictions = [estimator.predict(features_scaled)[0] for estimator in model.estimators_]
                variance = np.var(predictions)
                confidence = max(0.1, min(0.95, 1.0 - (variance / np.mean(predictions)**2)))
            else:
                # Simple heuristic for non-ensemble models
                confidence = 0.7
            
            return float(confidence)
            
        except Exception:
            return 0.5
    
    def _get_feature_importance(self, model, model_category: str) -> Dict[str, float]:
        """Get feature importance from model"""
        try:
            if hasattr(model, 'feature_importances_'):
                importance = model.feature_importances_
                feature_names = self._get_feature_names(model_category)
                return dict(zip(feature_names[:len(importance)], importance.astype(float)))
            elif hasattr(model, 'coef_'):
                coef = np.abs(model.coef_).flatten()
                feature_names = self._get_feature_names(model_category)
                return dict(zip(feature_names[:len(coef)], coef.astype(float)))
            else:
                return {}
        except Exception:
            return {}
    
    def _get_feature_names(self, model_category: str) -> List[str]:
        """Get feature names for model category"""
        feature_maps = {
            'demand_forecast': ['cost', 'distance', 'duration', 'emissions', 'risk', 'weight', 'volume'],
            'risk_prediction': ['reliability', 'quality', 'delivery', 'cost_comp', 'financial'],
            'route_optimization': ['cost', 'distance', 'duration', 'emissions', 'risk'],
            'supplier_scoring': ['reliability', 'quality', 'delivery', 'cost_comp', 'financial'],
            'inventory_optimization': ['current_stock', 'reorder_point', 'max_stock', 'safety_stock'],
            'price_optimization': ['cost', 'demand', 'competition', 'market_conditions'],
            'disruption_detection': ['weather', 'geopolitical', 'supplier', 'route', 'market'],
            'performance_analytics': ['efficiency', 'cost', 'time', 'quality', 'satisfaction']
        }
        return feature_maps.get(model_category, ['feature_' + str(i) for i in range(10)])
    
    def _generate_explanation(self, model_category: str, prediction: float, 
                            feature_importance: Dict[str, float]) -> str:
        """Generate human-readable explanation for prediction"""
        try:
            top_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:3]
            
            explanations = {
                'demand_forecast': f"Predicted demand: {prediction:.2f}. Key factors: {', '.join([f[0] for f in top_features])}",
                'risk_prediction': f"Risk score: {prediction:.2f}. Main risk drivers: {', '.join([f[0] for f in top_features])}",
                'route_optimization': f"Optimized score: {prediction:.2f}. Critical factors: {', '.join([f[0] for f in top_features])}",
                'supplier_scoring': f"Supplier score: {prediction:.2f}. Key performance areas: {', '.join([f[0] for f in top_features])}",
                'inventory_optimization': f"Optimal level: {prediction:.2f}. Main drivers: {', '.join([f[0] for f in top_features])}",
                'price_optimization': f"Optimized price: ${prediction:.2f}. Key factors: {', '.join([f[0] for f in top_features])}",
                'disruption_detection': f"Disruption probability: {prediction:.2f}. Main indicators: {', '.join([f[0] for f in top_features])}",
                'performance_analytics': f"Performance score: {prediction:.2f}. Key metrics: {', '.join([f[0] for f in top_features])}"
            }
            
            return explanations.get(model_category, f"Prediction: {prediction:.2f}")
            
        except Exception:
            return f"Prediction: {prediction:.2f}"
    
    def _fallback_prediction(self, model_category: str, features: np.ndarray) -> MLPrediction:
        """Provide fallback prediction when ML models are unavailable"""
        fallback_predictions = {
            'demand_forecast': 100.0,
            'risk_prediction': 0.3,
            'route_optimization': 0.7,
            'supplier_scoring': 0.6,
            'inventory_optimization': 50.0,
            'price_optimization': 25.0,
            'disruption_detection': 0.2,
            'performance_analytics': 0.75
        }
        
        prediction = fallback_predictions.get(model_category, 0.5)
        
        return MLPrediction(
            model_name=f"{model_category}.fallback",
            prediction=prediction,
            confidence=0.5,
            feature_importance={},
            explanation=f"Fallback prediction for {model_category}: {prediction}"
        )
    
    def _save_model(self, model_category: str, model_name: str, model, scaler, metrics: ModelMetrics):
        """Save trained model and metadata"""
        try:
            model_path = self.model_dir / f"{model_category}_{model_name}.joblib"
            scaler_path = self.model_dir / f"{model_category}_{model_name}_scaler.joblib"
            metadata_path = self.model_dir / f"{model_category}_{model_name}_metadata.json"
            
            # Save model and scaler
            joblib.dump(model, model_path)
            joblib.dump(scaler, scaler_path)
            
            # Save metadata
            metadata = {
                'model_category': model_category,
                'model_name': model_name,
                'metrics': {
                    'mae': metrics.mae,
                    'mse': metrics.mse,
                    'rmse': metrics.rmse,
                    'r2': metrics.r2,
                    'accuracy': metrics.accuracy,
                    'precision': metrics.precision,
                    'recall': metrics.recall,
                    'f1_score': metrics.f1_score
                },
                'trained_at': datetime.utcnow().isoformat(),
                'features_count': len(self._get_feature_names(model_category))
            }
            
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            logger.info(f"Saved model {model_category}.{model_name}")
            
        except Exception as e:
            logger.error(f"Error saving model {model_category}.{model_name}: {e}")
    
    def load_model(self, model_category: str, model_name: str) -> bool:
        """Load saved model"""
        try:
            model_path = self.model_dir / f"{model_category}_{model_name}.joblib"
            scaler_path = self.model_dir / f"{model_category}_{model_name}_scaler.joblib"
            
            if model_path.exists() and scaler_path.exists():
                model = joblib.load(model_path)
                scaler = joblib.load(scaler_path)
                
                if model_category not in self.models:
                    self.models[model_category] = {}
                if model_category not in self.scalers:
                    self.scalers[model_category] = {}
                
                self.models[model_category][model_name] = model
                self.scalers[model_category]['standard'] = scaler
                
                logger.info(f"Loaded model {model_category}.{model_name}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error loading model {model_category}.{model_name}: {e}")
            return False
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about available models"""
        info = {
            'available_categories': list(self.models.keys()),
            'sklearn_available': SKLEARN_AVAILABLE,
            'total_models': sum(len(models) for models in self.models.values()),
            'model_details': {}
        }
        
        for category, models in self.models.items():
            info['model_details'][category] = {
                'models': list(models.keys()),
                'count': len(models)
            }
        
        return info
