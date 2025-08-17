"""
Model Training and Evaluation Components
"""
import logging
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import json
from pathlib import Path

try:
    from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
    from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from .ml_engine import MLEngine, ModelMetrics
from .data_pipeline import DataPipeline

logger = logging.getLogger(__name__)

class ModelTrainer:
    """Handles training and retraining of ML models"""
    
    def __init__(self, ml_engine: MLEngine, data_pipeline: DataPipeline):
        self.ml_engine = ml_engine
        self.data_pipeline = data_pipeline
        self.training_history = {}
        self.hyperparameter_grids = self._initialize_hyperparameter_grids()
    
    def train_all_models(self, workspace_id: Optional[str] = None, 
                        days_back: int = 90) -> Dict[str, Any]:
        """Train all available models"""
        if not SKLEARN_AVAILABLE:
            logger.error("Cannot train models: sklearn not available")
            return {'error': 'sklearn not available'}
        
        training_results = {}
        model_categories = [
            'demand_forecast', 'risk_prediction', 'route_optimization',
            'supplier_scoring', 'inventory_optimization'
        ]
        
        for category in model_categories:
            try:
                category_results = self.train_model_category(category, workspace_id, days_back)
                training_results[category] = category_results
                logger.info(f"Trained models for category: {category}")
                
            except Exception as e:
                logger.error(f"Error training {category} models: {e}")
                training_results[category] = {'error': str(e)}
        
        # Save training summary
        self._save_training_summary(training_results)
        
        return training_results
    
    def train_model_category(self, category: str, workspace_id: Optional[str] = None,
                           days_back: int = 90) -> Dict[str, Any]:
        """Train all models in a specific category"""
        # Extract training data
        X, y = self.data_pipeline.extract_training_data(category, workspace_id, days_back)
        
        if len(X) == 0 or len(y) == 0:
            return {'error': f'No training data available for {category}'}
        
        logger.info(f"Training {category} models with {len(X)} samples")
        
        category_results = {}
        
        # Get models for this category
        if category not in self.ml_engine.models:
            return {'error': f'No models available for category: {category}'}
        
        models = self.ml_engine.models[category]
        
        for model_name, model in models.items():
            if model is None:
                continue
                
            try:
                # Train with hyperparameter optimization if enabled
                if self._should_optimize_hyperparameters(category, model_name):
                    metrics = self._train_with_hyperparameter_optimization(
                        category, model_name, X, y
                    )
                else:
                    metrics = self.ml_engine.train_model(category, model_name, X, y)
                
                if metrics:
                    category_results[model_name] = {
                        'metrics': asdict(metrics) if hasattr(metrics, '__dict__') else metrics,
                        'training_samples': len(X),
                        'trained_at': datetime.utcnow().isoformat()
                    }
                else:
                    category_results[model_name] = {'error': 'Training failed'}
                
            except Exception as e:
                logger.error(f"Error training {category}.{model_name}: {e}")
                category_results[model_name] = {'error': str(e)}
        
        return category_results
    
    def retrain_model(self, category: str, model_name: str, 
                     workspace_id: Optional[str] = None) -> Optional[ModelMetrics]:
        """Retrain a specific model"""
        try:
            X, y = self.data_pipeline.extract_training_data(category, workspace_id)
            
            if len(X) == 0:
                logger.warning(f"No training data for {category}.{model_name}")
                return None
            
            metrics = self.ml_engine.train_model(category, model_name, X, y)
            
            if metrics:
                # Update training history
                history_key = f"{category}_{model_name}"
                if history_key not in self.training_history:
                    self.training_history[history_key] = []
                
                self.training_history[history_key].append({
                    'timestamp': datetime.utcnow().isoformat(),
                    'metrics': asdict(metrics) if hasattr(metrics, '__dict__') else metrics,
                    'training_samples': len(X)
                })
                
                logger.info(f"Retrained {category}.{model_name} - R2: {metrics.r2:.3f}")
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error retraining {category}.{model_name}: {e}")
            return None
    
    def _train_with_hyperparameter_optimization(self, category: str, model_name: str,
                                              X: np.ndarray, y: np.ndarray) -> Optional[ModelMetrics]:
        """Train model with hyperparameter optimization"""
        try:
            if category not in self.hyperparameter_grids:
                return self.ml_engine.train_model(category, model_name, X, y)
            
            if model_name not in self.hyperparameter_grids[category]:
                return self.ml_engine.train_model(category, model_name, X, y)
            
            # Get base model
            base_model = self.ml_engine.models[category][model_name]
            param_grid = self.hyperparameter_grids[category][model_name]
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )
            
            # Scale features
            scaler = self.ml_engine.scalers[category]['standard']
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # Grid search
            grid_search = GridSearchCV(
                base_model, param_grid, cv=3, scoring='r2', n_jobs=-1
            )
            grid_search.fit(X_train_scaled, y_train)
            
            # Update model with best parameters
            best_model = grid_search.best_estimator_
            self.ml_engine.models[category][model_name] = best_model
            
            # Calculate metrics
            y_pred = best_model.predict(X_test_scaled)
            metrics = self.ml_engine._calculate_metrics(y_test, y_pred, category)
            
            # Save optimized model
            self.ml_engine._save_model(category, model_name, best_model, scaler, metrics)
            
            logger.info(f"Optimized {category}.{model_name} - Best params: {grid_search.best_params_}")
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error in hyperparameter optimization: {e}")
            return self.ml_engine.train_model(category, model_name, X, y)
    
    def _should_optimize_hyperparameters(self, category: str, model_name: str) -> bool:
        """Determine if hyperparameter optimization should be performed"""
        # Only optimize for key models to save time
        optimize_models = {
            'demand_forecast': ['rf', 'gb'],
            'risk_prediction': ['rf_classifier'],
            'route_optimization': ['cost_predictor'],
            'supplier_scoring': ['performance_scorer']
        }
        
        return (category in optimize_models and 
                model_name in optimize_models[category])
    
    def _initialize_hyperparameter_grids(self) -> Dict[str, Dict[str, Dict]]:
        """Initialize hyperparameter grids for optimization"""
        return {
            'demand_forecast': {
                'rf': {
                    'n_estimators': [50, 100, 200],
                    'max_depth': [10, 20, None],
                    'min_samples_split': [2, 5, 10]
                },
                'gb': {
                    'n_estimators': [50, 100, 200],
                    'learning_rate': [0.01, 0.1, 0.2],
                    'max_depth': [3, 5, 7]
                }
            },
            'risk_prediction': {
                'rf_classifier': {
                    'n_estimators': [50, 100, 200],
                    'max_depth': [10, 20, None],
                    'min_samples_split': [2, 5, 10]
                }
            },
            'route_optimization': {
                'cost_predictor': {
                    'n_estimators': [50, 100, 200],
                    'max_depth': [10, 20, None]
                }
            },
            'supplier_scoring': {
                'performance_scorer': {
                    'n_estimators': [50, 100, 200],
                    'max_depth': [10, 20, None]
                }
            }
        }
    
    def _save_training_summary(self, training_results: Dict[str, Any]):
        """Save training summary to file"""
        try:
            summary = {
                'timestamp': datetime.utcnow().isoformat(),
                'results': training_results,
                'total_models_trained': sum(
                    len([m for m in cat.keys() if not m.startswith('error')])
                    for cat in training_results.values()
                    if isinstance(cat, dict)
                )
            }
            
            summary_path = self.ml_engine.model_dir / 'training_summary.json'
            with open(summary_path, 'w') as f:
                json.dump(summary, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving training summary: {e}")
    
    def get_training_history(self) -> Dict[str, Any]:
        """Get training history for all models"""
        return self.training_history
    
    def schedule_retraining(self, category: str, model_name: str, 
                          interval_hours: int = 24) -> bool:
        """Schedule automatic retraining (placeholder for production)"""
        # In production, this would integrate with a task scheduler
        logger.info(f"Scheduled retraining for {category}.{model_name} every {interval_hours}h")
        return True

def asdict(obj):
    """Convert object to dictionary (simple implementation)"""
    if hasattr(obj, '__dict__'):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
    return obj

class ModelEvaluator:
    """Evaluates model performance and provides insights"""
    
    def __init__(self, ml_engine: MLEngine):
        self.ml_engine = ml_engine
        self.evaluation_history = {}
    
    def evaluate_model_performance(self, category: str, model_name: str,
                                 test_data: Optional[Tuple[np.ndarray, np.ndarray]] = None) -> Dict[str, Any]:
        """Evaluate a specific model's performance"""
        if not SKLEARN_AVAILABLE:
            return {'error': 'sklearn not available'}
        
        try:
            # Get test data if not provided
            if test_data is None:
                # Use a portion of recent data for testing
                data_pipeline = DataPipeline()
                X, y = data_pipeline.extract_training_data(category, days_back=30)
                if len(X) == 0:
                    return {'error': 'No test data available'}
                test_data = (X, y)
            
            X_test, y_test = test_data
            
            # Make predictions
            prediction = self.ml_engine.predict(category, model_name, X_test[0])
            if prediction is None:
                return {'error': 'Model prediction failed'}
            
            # For batch evaluation, we'd need to modify the predict method
            # For now, evaluate on single samples
            
            evaluation = {
                'model': f"{category}.{model_name}",
                'test_samples': len(X_test),
                'prediction_confidence': prediction.confidence,
                'feature_importance': prediction.feature_importance,
                'evaluation_timestamp': datetime.utcnow().isoformat()
            }
            
            return evaluation
            
        except Exception as e:
            logger.error(f"Error evaluating {category}.{model_name}: {e}")
            return {'error': str(e)}
    
    def compare_model_performance(self, category: str) -> Dict[str, Any]:
        """Compare performance of all models in a category"""
        if category not in self.ml_engine.models:
            return {'error': f'Category {category} not found'}
        
        models = self.ml_engine.models[category]
        comparison = {
            'category': category,
            'models': {},
            'best_model': None,
            'comparison_timestamp': datetime.utcnow().isoformat()
        }
        
        best_score = -float('inf')
        best_model_name = None
        
        for model_name in models.keys():
            if models[model_name] is None:
                continue
                
            evaluation = self.evaluate_model_performance(category, model_name)
            comparison['models'][model_name] = evaluation
            
            # Simple scoring for comparison (could be more sophisticated)
            score = evaluation.get('prediction_confidence', 0)
            if score > best_score:
                best_score = score
                best_model_name = model_name
        
        comparison['best_model'] = best_model_name
        return comparison
    
    def generate_model_insights(self, category: str) -> List[Dict[str, Any]]:
        """Generate insights about model performance"""
        insights = []
        
        try:
            comparison = self.compare_model_performance(category)
            
            if comparison.get('best_model'):
                insights.append({
                    'type': 'best_performer',
                    'insight': f"Best performing model in {category}: {comparison['best_model']}",
                    'category': category
                })
            
            # Check model availability
            available_models = len([m for m in comparison.get('models', {}).values() 
                                  if not m.get('error')])
            total_models = len(comparison.get('models', {}))
            
            if available_models < total_models:
                insights.append({
                    'type': 'availability_issue',
                    'insight': f"Only {available_models}/{total_models} models available in {category}",
                    'category': category
                })
            
            return insights
            
        except Exception as e:
            logger.error(f"Error generating insights for {category}: {e}")
            return [{'type': 'error', 'insight': str(e), 'category': category}]
    
    def create_performance_report(self) -> Dict[str, Any]:
        """Create comprehensive performance report"""
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'model_categories': {},
            'overall_insights': [],
            'recommendations': []
        }
        
        # Evaluate each category
        for category in self.ml_engine.models.keys():
            category_comparison = self.compare_model_performance(category)
            category_insights = self.generate_model_insights(category)
            
            report['model_categories'][category] = {
                'comparison': category_comparison,
                'insights': category_insights
            }
        
        # Generate overall insights
        total_models = sum(len(models) for models in self.ml_engine.models.values())
        available_models = sum(
            len([m for m in models.values() if m is not None])
            for models in self.ml_engine.models.values()
        )
        
        report['overall_insights'] = [
            {
                'type': 'model_availability',
                'insight': f"Total models: {total_models}, Available: {available_models}",
                'availability_rate': available_models / total_models if total_models > 0 else 0
            },
            {
                'type': 'sklearn_status',
                'insight': f"Scikit-learn available: {SKLEARN_AVAILABLE}",
                'ml_capability': SKLEARN_AVAILABLE
            }
        ]
        
        # Generate recommendations
        if not SKLEARN_AVAILABLE:
            report['recommendations'].append({
                'priority': 'high',
                'action': 'Install scikit-learn for full ML capability',
                'rationale': 'ML models currently using fallback predictions'
            })
        
        if available_models < total_models * 0.8:
            report['recommendations'].append({
                'priority': 'medium',
                'action': 'Investigate and fix unavailable models',
                'rationale': f'Only {available_models}/{total_models} models available'
            })
        
        return report
