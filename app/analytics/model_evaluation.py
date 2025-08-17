"""
Model Evaluation and Performance Monitoring
"""
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import json

from .ml_engine import MLEngine
from .model_training import ModelTrainer

logger = logging.getLogger(__name__)

class ModelEvaluator:
    """Comprehensive model evaluation and monitoring"""
    
    def __init__(self, ml_engine: MLEngine):
        self.ml_engine = ml_engine
        self.evaluation_history = {}
        self.performance_thresholds = self._initialize_performance_thresholds()
    
    def _initialize_performance_thresholds(self) -> Dict[str, Dict[str, float]]:
        """Initialize performance thresholds for different model types"""
        return {
            'demand_forecast': {
                'min_r2': 0.6,
                'max_rmse': 50.0,
                'min_confidence': 0.7
            },
            'risk_prediction': {
                'min_accuracy': 0.7,
                'min_precision': 0.65,
                'min_confidence': 0.6
            },
            'route_optimization': {
                'min_r2': 0.5,
                'max_rmse': 100.0,
                'min_confidence': 0.6
            },
            'supplier_scoring': {
                'min_r2': 0.55,
                'max_rmse': 0.3,
                'min_confidence': 0.65
            },
            'inventory_optimization': {
                'min_r2': 0.6,
                'max_rmse': 20.0,
                'min_confidence': 0.7
            }
        }
    
    def evaluate_all_models(self) -> Dict[str, Any]:
        """Evaluate all available models"""
        evaluation_report = {
            'timestamp': datetime.utcnow().isoformat(),
            'categories': {},
            'summary': {
                'total_models': 0,
                'passing_models': 0,
                'failing_models': 0,
                'warnings': []
            }
        }
        
        for category in self.ml_engine.models.keys():
            category_evaluation = self.evaluate_category(category)
            evaluation_report['categories'][category] = category_evaluation
            
            # Update summary
            category_models = category_evaluation.get('models', {})
            evaluation_report['summary']['total_models'] += len(category_models)
            
            for model_eval in category_models.values():
                if model_eval.get('status') == 'pass':
                    evaluation_report['summary']['passing_models'] += 1
                elif model_eval.get('status') == 'fail':
                    evaluation_report['summary']['failing_models'] += 1
        
        # Generate overall recommendations
        evaluation_report['recommendations'] = self._generate_recommendations(evaluation_report)
        
        return evaluation_report
    
    def evaluate_category(self, category: str) -> Dict[str, Any]:
        """Evaluate all models in a specific category"""
        if category not in self.ml_engine.models:
            return {'error': f'Category {category} not found'}
        
        category_evaluation = {
            'category': category,
            'models': {},
            'category_summary': {
                'total_models': 0,
                'available_models': 0,
                'passing_models': 0
            },
            'timestamp': datetime.utcnow().isoformat()
        }
        
        models = self.ml_engine.models[category]
        
        for model_name, model in models.items():
            model_evaluation = self.evaluate_single_model(category, model_name)
            category_evaluation['models'][model_name] = model_evaluation
            
            # Update category summary
            category_evaluation['category_summary']['total_models'] += 1
            
            if model is not None:
                category_evaluation['category_summary']['available_models'] += 1
                
                if model_evaluation.get('status') == 'pass':
                    category_evaluation['category_summary']['passing_models'] += 1
        
        return category_evaluation
    
    def evaluate_single_model(self, category: str, model_name: str) -> Dict[str, Any]:
        """Evaluate a single model"""
        try:
            model = self.ml_engine.models[category].get(model_name)
            
            if model is None:
                return {
                    'status': 'unavailable',
                    'message': 'Model not loaded or unavailable',
                    'timestamp': datetime.utcnow().isoformat()
                }
            
            # Generate test features for evaluation
            test_features = self._generate_test_features(category)
            
            # Make prediction
            prediction = self.ml_engine.predict(category, model_name, test_features)
            
            if prediction is None:
                return {
                    'status': 'fail',
                    'message': 'Prediction failed',
                    'timestamp': datetime.utcnow().isoformat()
                }
            
            # Evaluate prediction quality
            evaluation = {
                'status': 'pass',
                'prediction_value': prediction.prediction,
                'confidence': prediction.confidence,
                'feature_importance_count': len(prediction.feature_importance),
                'has_explanation': bool(prediction.explanation),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Check against thresholds
            if category in self.performance_thresholds:
                thresholds = self.performance_thresholds[category]
                threshold_checks = self._check_thresholds(prediction, thresholds)
                evaluation.update(threshold_checks)
            
            return evaluation
            
        except Exception as e:
            logger.error(f"Error evaluating {category}.{model_name}: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def _generate_test_features(self, category: str) -> np.ndarray:
        """Generate appropriate test features for a model category"""
        test_features = {
            'demand_forecast': np.array([100, 1.1, 1.05, 3, 6, 30, 0, 0]),  # 8 features
            'risk_prediction': np.array([5000, 2000, 48, 2, 3, 6, 40.7, -74.0, 51.5, 0.1]),  # 10 features
            'route_optimization': np.array([3000, 1500, 36, 150, 2, 7]),  # 6 features
            'supplier_scoring': np.array([0.8, 0.7, 0.75, 0.6, 0.8, 15, 50]),  # 7 features
            'inventory_optimization': np.array([100, 50, 200, 15, 5, 7])  # 6 features
        }
        
        return test_features.get(category, np.array([1.0, 1.0, 1.0, 1.0]))
    
    def _check_thresholds(self, prediction, thresholds: Dict[str, float]) -> Dict[str, Any]:
        """Check prediction against performance thresholds"""
        checks = {
            'threshold_checks': {},
            'passes_thresholds': True
        }
        
        # Check confidence threshold
        if 'min_confidence' in thresholds:
            confidence_pass = prediction.confidence >= thresholds['min_confidence']
            checks['threshold_checks']['confidence'] = {
                'value': prediction.confidence,
                'threshold': thresholds['min_confidence'],
                'pass': confidence_pass
            }
            if not confidence_pass:
                checks['passes_thresholds'] = False
        
        # Additional threshold checks would be implemented here
        # For now, we'll focus on confidence as the main metric
        
        if not checks['passes_thresholds']:
            checks['status'] = 'warning'
        
        return checks
    
    def monitor_prediction_drift(self, category: str, model_name: str, 
                               recent_predictions: List[Dict]) -> Dict[str, Any]:
        """Monitor for prediction drift over time"""
        if len(recent_predictions) < 10:
            return {
                'drift_detected': False,
                'message': 'Insufficient data for drift detection',
                'sample_count': len(recent_predictions)
            }
        
        # Extract prediction values and confidences
        predictions = [p.get('prediction', 0) for p in recent_predictions]
        confidences = [p.get('confidence', 0.5) for p in recent_predictions]
        
        # Simple drift detection using standard deviation
        pred_std = np.std(predictions)
        conf_std = np.std(confidences)
        pred_mean = np.mean(predictions)
        conf_mean = np.mean(confidences)
        
        # Define drift thresholds (these could be more sophisticated)
        pred_drift_threshold = pred_mean * 0.5  # 50% of mean
        conf_drift_threshold = 0.2  # Absolute threshold for confidence
        
        drift_analysis = {
            'drift_detected': False,
            'prediction_drift': {
                'std_dev': pred_std,
                'mean': pred_mean,
                'threshold': pred_drift_threshold,
                'high_variance': pred_std > pred_drift_threshold
            },
            'confidence_drift': {
                'std_dev': conf_std,
                'mean': conf_mean,
                'threshold': conf_drift_threshold,
                'high_variance': conf_std > conf_drift_threshold
            },
            'sample_count': len(recent_predictions),
            'analysis_timestamp': datetime.utcnow().isoformat()
        }
        
        # Determine if drift is detected
        if (drift_analysis['prediction_drift']['high_variance'] or 
            drift_analysis['confidence_drift']['high_variance']):
            drift_analysis['drift_detected'] = True
            drift_analysis['recommendation'] = 'Consider model retraining due to detected drift'
        
        return drift_analysis
    
    def generate_performance_insights(self, evaluation_report: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate actionable insights from evaluation report"""
        insights = []
        
        summary = evaluation_report.get('summary', {})
        categories = evaluation_report.get('categories', {})
        
        # Overall performance insight
        total_models = summary.get('total_models', 0)
        passing_models = summary.get('passing_models', 0)
        
        if total_models > 0:
            pass_rate = passing_models / total_models
            
            if pass_rate >= 0.8:
                insights.append({
                    'type': 'performance',
                    'level': 'good',
                    'insight': f'Model performance is good: {passing_models}/{total_models} models passing',
                    'pass_rate': pass_rate
                })
            elif pass_rate >= 0.6:
                insights.append({
                    'type': 'performance',
                    'level': 'moderate',
                    'insight': f'Model performance is moderate: {passing_models}/{total_models} models passing',
                    'pass_rate': pass_rate
                })
            else:
                insights.append({
                    'type': 'performance',
                    'level': 'poor',
                    'insight': f'Model performance needs attention: only {passing_models}/{total_models} models passing',
                    'pass_rate': pass_rate
                })
        
        # Category-specific insights
        for category_name, category_data in categories.items():
            category_summary = category_data.get('category_summary', {})
            available = category_summary.get('available_models', 0)
            total = category_summary.get('total_models', 0)
            
            if total > 0 and available < total:
                insights.append({
                    'type': 'availability',
                    'level': 'warning',
                    'insight': f'{category_name}: {available}/{total} models available',
                    'category': category_name
                })
        
        # Model-specific insights
        for category_name, category_data in categories.items():
            models = category_data.get('models', {})
            for model_name, model_data in models.items():
                if model_data.get('status') == 'fail':
                    insights.append({
                        'type': 'model_failure',
                        'level': 'error',
                        'insight': f'{category_name}.{model_name} is failing: {model_data.get("message", "Unknown error")}',
                        'category': category_name,
                        'model': model_name
                    })
                elif model_data.get('status') == 'warning':
                    insights.append({
                        'type': 'model_warning',
                        'level': 'warning',
                        'insight': f'{category_name}.{model_name} has performance issues',
                        'category': category_name,
                        'model': model_name
                    })
        
        return insights
    
    def _generate_recommendations(self, evaluation_report: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate recommendations based on evaluation results"""
        recommendations = []
        
        summary = evaluation_report.get('summary', {})
        failing_models = summary.get('failing_models', 0)
        total_models = summary.get('total_models', 0)
        
        # High-level recommendations
        if failing_models > 0:
            recommendations.append({
                'priority': 'high',
                'action': f'Investigate and fix {failing_models} failing models',
                'rationale': 'Failed models impact prediction quality',
                'category': 'model_health'
            })
        
        if total_models > 0 and summary.get('passing_models', 0) / total_models < 0.7:
            recommendations.append({
                'priority': 'medium',
                'action': 'Consider model retraining or parameter tuning',
                'rationale': 'Low overall model pass rate indicates performance issues',
                'category': 'performance_optimization'
            })
        
        # Category-specific recommendations
        categories = evaluation_report.get('categories', {})
        for category_name, category_data in categories.items():
            category_summary = category_data.get('category_summary', {})
            available = category_summary.get('available_models', 0)
            total = category_summary.get('total_models', 0)
            
            if total > 0 and available == 0:
                recommendations.append({
                    'priority': 'critical',
                    'action': f'Restore {category_name} models - none are available',
                    'rationale': f'Category {category_name} has no working models',
                    'category': 'availability'
                })
            elif total > 0 and available < total * 0.5:
                recommendations.append({
                    'priority': 'high',
                    'action': f'Fix {category_name} models - only {available}/{total} available',
                    'rationale': f'Low availability in {category_name} category',
                    'category': 'availability'
                })
        
        return recommendations
    
    def create_health_dashboard_data(self) -> Dict[str, Any]:
        """Create data for ML health dashboard"""
        evaluation = self.evaluate_all_models()
        insights = self.generate_performance_insights(evaluation)
        
        # Categorize insights by level
        insight_levels = {'good': [], 'moderate': [], 'poor': [], 'warning': [], 'error': []}
        for insight in insights:
            level = insight.get('level', 'moderate')
            if level in insight_levels:
                insight_levels[level].append(insight)
        
        # Calculate health score
        total_models = evaluation['summary']['total_models']
        passing_models = evaluation['summary']['passing_models']
        health_score = (passing_models / total_models * 100) if total_models > 0 else 0
        
        dashboard_data = {
            'health_score': round(health_score, 1),
            'model_summary': evaluation['summary'],
            'insights_by_level': insight_levels,
            'recommendations': evaluation.get('recommendations', []),
            'category_status': {},
            'last_updated': datetime.utcnow().isoformat()
        }
        
        # Category status for dashboard
        for category_name, category_data in evaluation.get('categories', {}).items():
            summary = category_data.get('category_summary', {})
            dashboard_data['category_status'][category_name] = {
                'total': summary.get('total_models', 0),
                'available': summary.get('available_models', 0),
                'passing': summary.get('passing_models', 0),
                'health_percentage': (summary.get('passing_models', 0) / 
                                    summary.get('total_models', 1) * 100) if summary.get('total_models', 0) > 0 else 0
            }
        
        return dashboard_data
