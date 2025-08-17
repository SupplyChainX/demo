"""
Procurement Agent - Monitors inventory and automates purchase orders
"""
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from flask import current_app
from sqlalchemy import and_, or_
from app import db
from app.models import (
    Inventory, Supplier, PurchaseOrder, PurchaseOrderItem,
    Recommendation, RecommendationType, AlertSeverity,
    PurchaseOrderStatus, Outbox, Alert, AlertType,
    SupplierScore, Contract
)
from app.agents.communicator import AgentCommunicator
from app.agents.routes import update_agent_status
from app.integrations.supplier_apis import SupplierIntegration
from app.integrations.watsonx_client import WatsonxClient

logger = logging.getLogger(__name__)

class ProcurementAgent:
    """Automate procurement decisions and purchase order generation."""
    
    def __init__(self):
        self.name = 'procurement_agent'
        self.communicator = AgentCommunicator(self.name)
        self.supplier_api = SupplierIntegration()
        self.watsonx_client = WatsonxClient()
        self.thresholds = current_app.config.get('INVENTORY_THRESHOLDS', {})
        self.procurement_rules = current_app.config.get('PROCUREMENT_RULES', {})
        
    def run_cycle(self):
        """Run one procurement cycle."""
        try:
            logger.info(f"{self.name} starting procurement cycle")
            update_agent_status(self.name, status='running')
            
            # 1. Monitor inventory levels
            low_inventory_items = self._check_inventory_thresholds()
            
            # 2. Process procurement requests from stream
            procurement_requests = self.communicator.receive_messages(
                ['procurement.actions'], count=10
            )
            
            # 3. Generate purchase orders for low inventory
            pos_created = 0
            for item in low_inventory_items:
                po = self._generate_purchase_order(item)
                if po:
                    pos_created += 1
                    self._notify_orchestrator(po)
            
            # 4. Process negotiation requests
            for request in procurement_requests:
                self._process_procurement_request(request)
            
            # 5. Update supplier scores
            self._update_supplier_scores()
            
            logger.info(f"{self.name} created {pos_created} purchase orders")
            update_agent_status(self.name, purchase_orders=pos_created)
            
        except Exception as e:
            logger.error(f"Error in {self.name} cycle: {e}")
            update_agent_status(self.name, status='error')
    
    def _check_inventory_thresholds(self) -> List[Inventory]:
        """Check inventory levels against thresholds."""
        low_items = []
        
        # Get default threshold or 10 days
        default_threshold = self.thresholds.get('default_days_cover', 10)
        
        # Query all active inventory items and filter programmatically
        all_inventory_items = Inventory.query.filter(
            Inventory.workspace_id == 1
        ).all()
        
        # Filter by days_cover threshold programmatically
        inventory_items = [
            item for item in all_inventory_items 
            if item.days_cover < default_threshold
        ]
        
        for item in inventory_items:
            # Check item-specific thresholds
            item_threshold = self.thresholds.get(
                f'sku_{item.sku}', 
                self.thresholds.get('default_category', default_threshold)
            )
            
            if item.days_cover < item_threshold:
                low_items.append(item)
                logger.info(f"Low inventory detected: {item.sku} - {item.days_cover} days cover")
        
        return low_items
    
    def _generate_purchase_order(self, inventory_item: Inventory) -> Optional[PurchaseOrder]:
        """Generate purchase order using AI assistance."""
        try:
            # 1. Find suitable suppliers
            suppliers = self._find_suitable_suppliers(inventory_item)
            if not suppliers:
                logger.warning(f"No suppliers found for {inventory_item.sku}")
                return None
            
            # 2. Score and rank suppliers
            scored_suppliers = self._score_suppliers(suppliers, inventory_item)
            best_supplier = scored_suppliers[0]['supplier']
            
            # 3. Calculate order quantity
            order_quantity = self._calculate_order_quantity(inventory_item)
            
            # 4. Generate PO details using Granite model
            po_details = self._generate_po_with_ai(
                inventory_item, best_supplier, order_quantity, scored_suppliers
            )
            
            # 5. Create purchase order
            po = PurchaseOrder(
                workspace_id=inventory_item.workspace_id,
                supplier_id=best_supplier.id,
                reference_number=self._generate_po_number(),
                status=PurchaseOrderStatus.DRAFT,
                total_amount=po_details['total_amount'],
                currency=po_details.get('currency', 'USD'),
                payment_terms=po_details.get('payment_terms', 'Net 30'),
                delivery_date=datetime.utcnow() + timedelta(days=po_details.get('lead_time', 14)),
                delivery_location=inventory_item.location,
                notes=po_details.get('notes', ''),
                ai_generated=True,
                created_by=self.name
            )
            db.session.add(po)
            
            # Add line items
            po_item = PurchaseOrderItem(
                purchase_order=po,
                sku=inventory_item.sku,
                description=inventory_item.description,
                quantity=order_quantity,
                unit_price=po_details['unit_price'],
                total_price=po_details['total_amount']
            )
            db.session.add(po_item)
            
            # Create recommendation for approval
            recommendation = Recommendation(
                workspace_id=inventory_item.workspace_id,
                type=RecommendationType.PROCUREMENT,
                subject_type='purchase_order',
                subject_id=po.id,
                title=f"Approve PO for {inventory_item.sku} from {best_supplier.name}",
                description=f"Auto-generated PO to replenish {inventory_item.sku}. Current cover: {inventory_item.days_cover} days",
                actions=[
                    {
                        'type': 'approve_po',
                        'label': 'Approve Order',
                        'params': {'po_id': po.id}
                    },
                    {
                        'type': 'negotiate',
                        'label': 'Negotiate Terms',
                        'params': {
                            'po_id': po.id,
                            'current_price': po_details['unit_price']
                        }
                    },
                    {
                        'type': 'change_supplier',
                        'label': 'Select Different Supplier',
                        'params': {
                            'alternatives': len(scored_suppliers) - 1
                        }
                    }
                ],
                severity=AlertSeverity.MEDIUM if inventory_item.days_cover < 5 else AlertSeverity.LOW,
                confidence=po_details['confidence'],
                impact_assessment={
                    'cost': po_details['total_amount'],
                    'lead_time_days': po_details.get('lead_time', 14),
                    'inventory_days_gained': order_quantity / (inventory_item.quantity_on_hand / inventory_item.days_cover) if inventory_item.days_cover > 0 else 30
                },
                model_config={
                    'agent': self.name,
                    'model': 'granite-3-2b-instruct',
                    'version': '1.0',
                    'temperature': 0.7
                },
                input_data={
                    'inventory_id': inventory_item.id,
                    'sku': inventory_item.sku,
                    'suppliers_evaluated': len(scored_suppliers),
                    'order_quantity': order_quantity
                },
                xai_explanation=po_details['explanation'],
                status='pending',
                created_by=self.name
            )
            db.session.add(recommendation)
            
            # Add to outbox
            outbox_event = Outbox(
                aggregate_id=str(po.id),
                aggregate_type='purchase_order',
                event_type='po_created',
                event_data={
                    'po_id': po.id,
                    'supplier_id': best_supplier.id,
                    'amount': po_details['total_amount'],
                    'auto_generated': True
                },
                stream_name='procurement.actions'
            )
            db.session.add(outbox_event)
            
            db.session.commit()
            
            logger.info(f"Created PO {po.reference_number} for {inventory_item.sku}")
            return po
            
        except Exception as e:
            logger.error(f"Error generating PO: {e}")
            db.session.rollback()
            return None
    
    def _find_suitable_suppliers(self, inventory_item: Inventory) -> List[Supplier]:
        """Find suppliers that can provide the inventory item."""
        # Query suppliers by category and SKU
        # Find suppliers that can provide this product (using categories for now)
        suppliers = Supplier.query.filter(
            or_(
                Supplier.categories.contains(['default']),
                Supplier.categories.contains([getattr(inventory_item, 'category', 'general')])
            ),
            Supplier.status == 'active',
            Supplier.workspace_id == inventory_item.workspace_id
        ).all()
        
        # Filter by geographic constraints if any
        if 'excluded_regions' in self.procurement_rules:
            suppliers = [s for s in suppliers 
                        if s.country not in self.procurement_rules['excluded_regions']]
        
        return suppliers
    
    def _score_suppliers(self, suppliers: List[Supplier], 
                        inventory_item: Inventory) -> List[Dict[str, Any]]:
        """Score and rank suppliers based on multiple factors."""
        scored_suppliers = []
        
        for supplier in suppliers:
            # Get latest score record
            latest_score = SupplierScore.query.filter_by(
                supplier_id=supplier.id
            ).order_by(SupplierScore.calculated_at.desc()).first()
            
            # Calculate composite score
            price_score = latest_score.price_score if latest_score else 0.7
            reliability_score = latest_score.reliability_score if latest_score else 0.8
            lead_time_score = latest_score.lead_time_score if latest_score else 0.7
            quality_score = latest_score.quality_score if latest_score else 0.85
            
            # Apply weights
            weights = self.procurement_rules.get('scoring_weights', {
                'price': 0.3,
                'reliability': 0.3,
                'lead_time': 0.2,
                'quality': 0.2
            })
            
            composite_score = (
                price_score * weights.get('price', 0.3) +
                reliability_score * weights.get('reliability', 0.3) +
                lead_time_score * weights.get('lead_time', 0.2) +
                quality_score * weights.get('quality', 0.2)
            )
            
            # Get estimated price from contracts or history
            unit_price = self._get_estimated_price(supplier, inventory_item.sku)
            
            scored_suppliers.append({
                'supplier': supplier,
                'composite_score': round(composite_score, 3),
                'price_score': price_score,
                'reliability_score': reliability_score,
                'lead_time_score': lead_time_score,
                'quality_score': quality_score,
                'estimated_price': unit_price,
                'estimated_lead_time': supplier.average_lead_time_days or 14
            })
        
        # Sort by composite score (descending)
        return sorted(scored_suppliers, key=lambda x: x['composite_score'], reverse=True)
    
    def _calculate_order_quantity(self, inventory_item: Inventory) -> int:
        """Calculate optimal order quantity."""
        # Simple EOQ-inspired calculation
        daily_usage = inventory_item.quantity_on_hand / inventory_item.days_cover if inventory_item.days_cover > 0 else 100
        
        # Target days cover (e.g., 30 days)
        target_days = self.thresholds.get('target_days_cover', 30)
        
        # Base order quantity
        base_quantity = daily_usage * target_days
        
        # Consider minimum order quantities
        moq = self.procurement_rules.get('minimum_order_quantity', {}).get(
            inventory_item.sku, 
            self.procurement_rules.get('default_moq', 100)
        )
        
        return max(int(base_quantity), moq)
    
    def _generate_po_with_ai(self, inventory_item: Inventory, supplier: Supplier,
                            quantity: int, alternatives: List[Dict]) -> Dict[str, Any]:
        """Use Granite model to generate PO details and negotiation strategy."""
        try:
            # Prepare context for AI
            context = {
                'item': {
                    'sku': inventory_item.sku,
                    'description': inventory_item.description,
                    'current_stock': inventory_item.quantity_on_hand,
                    'days_cover': inventory_item.days_cover,
                    'category': 'general'
                },
                'supplier': {
                    'name': supplier.name,
                    'score': alternatives[0]['composite_score'],
                    'lead_time': supplier.average_lead_time_days,
                    'payment_terms': supplier.payment_terms
                },
                'quantity': quantity,
                'alternatives': [
                    {
                        'name': alt['supplier'].name,
                        'score': alt['composite_score'],
                        'price': alt['estimated_price']
                    }
                    for alt in alternatives[:3]
                ]
            }
            
            # Generate PO details using Granite
            prompt = f"""
            Generate purchase order details for the following procurement need:
            
            Item: {inventory_item.sku} - {inventory_item.description}
            Current Stock: {inventory_item.quantity_on_hand} units ({inventory_item.days_cover} days cover)
            Order Quantity: {quantity} units
            
            Selected Supplier: {supplier.name}
            Supplier Score: {alternatives[0]['composite_score']:.2f}
            Lead Time: {supplier.average_lead_time_days} days
            
            Alternative Suppliers Available: {len(alternatives) - 1}
            
            Please provide:
            1. Recommended unit price based on market conditions
            2. Suggested payment terms
            3. Any negotiation points
            4. Risk factors to consider
            5. Confidence level (0-1) in this recommendation
            
            Format the response as JSON.
            """
            
            response = self.watsonx_client.generate(
                prompt=prompt,
                model_id='granite-3-2b-instruct',
                max_tokens=500,
                temperature=0.7
            )
            
            # Parse AI response
            ai_details = self._parse_ai_response(response)
            
            # Calculate final details
            unit_price = ai_details.get('recommended_unit_price', alternatives[0]['estimated_price'])
            total_amount = unit_price * quantity
            
            return {
                'unit_price': unit_price,
                'total_amount': total_amount,
                'payment_terms': ai_details.get('payment_terms', supplier.payment_terms or 'Net 30'),
                'lead_time': supplier.average_lead_time_days or 14,
                'currency': 'USD',
                'notes': ai_details.get('negotiation_points', ''),
                'confidence': ai_details.get('confidence', 0.85),
                'explanation': {
                    'rationale': f"Selected {supplier.name} based on composite score of {alternatives[0]['composite_score']:.2f}",
                    'factors': [
                        f"Price competitiveness: {alternatives[0]['price_score']:.2f}",
                        f"Reliability: {alternatives[0]['reliability_score']:.2f}",
                        f"Lead time performance: {alternatives[0]['lead_time_score']:.2f}",
                        f"Quality score: {alternatives[0]['quality_score']:.2f}"
                    ],
                    'alternatives_considered': len(alternatives),
                    'ai_insights': ai_details.get('insights', []),
                    'risk_factors': ai_details.get('risk_factors', [])
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating PO with AI: {e}")
            # Fallback to simple calculation
            return {
                'unit_price': alternatives[0]['estimated_price'],
                'total_amount': alternatives[0]['estimated_price'] * quantity,
                'payment_terms': 'Net 30',
                'lead_time': 14,
                'currency': 'USD',
                'notes': 'Auto-generated without AI assistance',
                'confidence': 0.7,
                'explanation': {
                    'rationale': 'Fallback to rule-based selection',
                    'factors': ['Selected based on highest composite score'],
                    'alternatives_considered': len(alternatives),
                    'ai_insights': [],
                    'risk_factors': []
                }
            }
    
    def _parse_ai_response(self, response: str) -> Dict[str, Any]:
        """Parse AI response into structured data."""
        try:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            
            # Fallback parsing logic
            parsed = {
                'recommended_unit_price': 100.0,
                'payment_terms': 'Net 30',
                'confidence': 0.8,
                'negotiation_points': 'Standard terms applied',
                'risk_factors': ['Supply chain stability'],
                'insights': ['Market conditions stable']
            }
            
            # Extract values from text if possible
            price_match = re.search(r'price[:\s]+\$?([\d,]+\.?\d*)', response, re.I)
            if price_match:
                parsed['recommended_unit_price'] = float(price_match.group(1).replace(',', ''))
            
            return parsed
            
        except Exception as e:
            logger.error(f"Error parsing AI response: {e}")
            return {}
    
    def _get_estimated_price(self, supplier: Supplier, sku: str) -> float:
        """Get estimated price from contracts or purchase history."""
        # Check active contracts
        contract = Contract.query.filter(
            Contract.supplier_id == supplier.id,
            Contract.status == 'active',
            Contract.start_date <= datetime.utcnow(),
            Contract.end_date >= datetime.utcnow()
        ).first()
        
        if contract and contract.pricing_data:
            sku_price = contract.pricing_data.get(sku)
            if sku_price:
                return float(sku_price)
        
        # Check recent POs
        recent_po = PurchaseOrder.query.join(PurchaseOrderItem).filter(
            PurchaseOrder.supplier_id == supplier.id,
            PurchaseOrderItem.sku == sku,
            PurchaseOrder.created_at >= datetime.utcnow() - timedelta(days=90)
        ).order_by(PurchaseOrder.created_at.desc()).first()
        
        if recent_po:
            item = next((i for i in recent_po.items if i.sku == sku), None)
            if item:
                return float(item.unit_price)
        
        # Default estimate
        return 100.0
    
    def _generate_po_number(self) -> str:
        """Generate unique PO number."""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        return f"PO-{timestamp}"
    
    def _process_procurement_request(self, request: Dict[str, Any]):
        """Process specific procurement requests."""
        request_type = request.get('type')
        
        if request_type == 'negotiate':
            self._handle_negotiation_request(request)
        elif request_type == 'change_supplier':
            self._handle_supplier_change(request)
        elif request_type == 'expedite':
            self._handle_expedite_request(request)
    
    def _handle_negotiation_request(self, request: Dict[str, Any]):
        """Handle negotiation request using AI."""
        try:
            po_id = request.get('po_id')
            po = db.session.get(PurchaseOrder, po_id)
            if not po:
                return
            
            # Generate negotiation strategy
            prompt = f"""
            Generate a negotiation strategy for purchase order {po.reference_number}:
            Current terms:
            - Supplier: {po.supplier.name}
            - Amount: ${po.total_amount:,.2f}
            - Payment: {po.payment_terms}
            - Delivery: {po.delivery_date}
            
            Market conditions and alternatives available.
            Suggest negotiation points and target improvements.
            """
            
            response = self.watsonx_client.generate(
                prompt=prompt,
                model_id='granite-3-2b-instruct',
                max_tokens=300
            )
            
            # Create negotiation recommendation
            recommendation = Recommendation(
                workspace_id=po.workspace_id,
                type=RecommendationType.PROCUREMENT,
                subject_type='negotiation',
                subject_id=po.id,
                title=f"Negotiation Strategy for {po.reference_number}",
                description=response,
                severity=AlertSeverity.LOW,
                confidence=0.8,
                status='pending',
                created_by=self.name
            )
            db.session.add(recommendation)
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Error handling negotiation: {e}")
    
    def _update_supplier_scores(self):
        """Update supplier performance scores."""
        try:
            suppliers = Supplier.query.filter_by(status='active').all()
            
            for supplier in suppliers:
                # Calculate performance metrics
                recent_pos = PurchaseOrder.query.filter(
                    PurchaseOrder.supplier_id == supplier.id,
                    PurchaseOrder.created_at >= datetime.utcnow() - timedelta(days=90)
                ).all()
                
                if not recent_pos:
                    continue
                
                # Calculate scores
                on_time_deliveries = sum(1 for po in recent_pos 
                                       if po.actual_delivery_date and 
                                       po.actual_delivery_date <= po.delivery_date)
                reliability_score = on_time_deliveries / len(recent_pos) if recent_pos else 0.5
                
                # Price competitiveness (simplified)
                price_score = 0.8  # Would compare with market rates
                
                # Lead time performance
                avg_lead_time = sum((po.actual_delivery_date - po.created_at).days 
                                  for po in recent_pos 
                                  if po.actual_delivery_date) / len(recent_pos) if recent_pos else 14
                lead_time_score = max(0, 1 - (avg_lead_time - 7) / 30)  # 7 days is ideal
                
                # Quality score (would track defects/returns)
                quality_score = 0.9
                
                # Create score record
                score = SupplierScore(
                    supplier_id=supplier.id,
                    overall_score=(reliability_score + price_score + lead_time_score + quality_score) / 4,
                    reliability_score=reliability_score,
                    price_score=price_score,
                    lead_time_score=lead_time_score,
                    quality_score=quality_score,
                    data_points=len(recent_pos),
                    calculated_at=datetime.utcnow()
                )
                db.session.add(score)
            
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Error updating supplier scores: {e}")
            db.session.rollback()
    
    def _notify_orchestrator(self, po: PurchaseOrder):
        """Notify orchestrator about new purchase order."""
        try:
            # Request approval for PO
            self.communicator.request_approval(
                recommendation_id=po.id,
                recommendation_type='purchase_order',
                details={
                    'po_id': po.id,
                    'amount': po.total_amount,
                    'supplier': po.supplier.name,
                    'items': [{'sku': item.sku, 'quantity': item.quantity} 
                             for item in po.items]
                }
            )
            
            # Broadcast to UI
            self.communicator.broadcast_update('po_created', {
                'po_id': po.id,
                'reference': po.reference_number,
                'supplier': po.supplier.name,
                'amount': po.total_amount,
                'status': po.status.value
            })
            
        except Exception as e:
            logger.error(f"Error notifying about PO: {e}")

def start_procurement_agent_loop(app=None):
    """Main loop for Procurement Agent."""
    logger.info("Starting Procurement Agent loop")
    
    if app is None:
        from flask import current_app
        app = current_app._get_current_object()
    
    with app.app_context():
        agent = ProcurementAgent()
        loop_interval = 60  # Run every minute
        
        while True:
            try:
                agent.run_cycle()
                time.sleep(loop_interval)
            except Exception as e:
                logger.error(f"Error in procurement agent loop: {e}")
                time.sleep(loop_interval)
        app = current_app._get_current_object()
    
    with app.app_context():
        agent = ProcurementAgent()
        loop_interval = 60  # Run every 60 seconds
        while True:
            try:
                agent.run_cycle()
            except Exception as e:
                logger.error(f"Error in procurement agent loop: {e}")
                update_agent_status('procurement_agent', status='error')
            
            time.sleep(loop_interval)
