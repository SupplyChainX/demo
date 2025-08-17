"""
Financial and Economic Data API Integrations
"""
import logging
import requests
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from flask import current_app

logger = logging.getLogger(__name__)

class FinancialIntegration:
    """Integration with financial data sources."""
    
    def __init__(self):
        self.alpha_vantage_key = current_app.config.get('ALPHAVANTAGE_API_KEY')
        self.polygon_key = current_app.config.get('POLYGON_API_KEY')
        self.world_bank_url = current_app.config.get('WORLD_BANK_API_URL', 'http://api.worldbank.org')
        
    def get_exchange_rates(self, base_currency: str = 'USD') -> Dict[str, float]:
        """Get current exchange rates."""
        rates = {base_currency: 1.0}
        
        try:
            if self.alpha_vantage_key:
                url = "https://www.alphavantage.co/query"
                params = {
                    'function': 'CURRENCY_EXCHANGE_RATE',
                    'from_currency': base_currency,
                    'to_currency': 'EUR',
                    'apikey': self.alpha_vantage_key
                }
                
                # Get major currencies
                for currency in ['EUR', 'GBP', 'JPY', 'CNY', 'INR']:
                    params['to_currency'] = currency
                    response = requests.get(url, params=params, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if 'Realtime Currency Exchange Rate' in data:
                            rate = float(data['Realtime Currency Exchange Rate']['5. Exchange Rate'])
                            rates[currency] = rate
                            
        except Exception as e:
            logger.error(f"Error fetching exchange rates: {e}")
        
        # Fallback rates for MVP
        if len(rates) == 1:
            rates.update({
                'EUR': 0.85,
                'GBP': 0.73,
                'JPY': 110.0,
                'CNY': 6.45,
                'INR': 74.5
            })
        
        return rates
    
    def get_commodity_prices(self) -> Dict[str, Any]:
        """Get commodity prices relevant to supply chain."""
        commodities = {}
        
        try:
            # World Bank Commodity Price Data (Pink Sheet)
            # Free access, no API key required
            url = f"{self.world_bank_url}/v2/country/all/indicator/CRUDE_WTI"
            params = {
                'format': 'json',
                'date': '2024',
                'per_page': 1
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if len(data) > 1 and data[1]:
                    crude_price = data[1][0].get('value')
                    if crude_price:
                        commodities['crude_oil_wti'] = {
                            'value': crude_price,
                            'unit': 'USD/barrel',
                            'source': 'World Bank'
                        }
            
            # Get more commodities
            commodity_indicators = {
                'COAL_AUS': 'coal_australian',
                'COPPER': 'copper',
                'ALUMINUM': 'aluminum',
                'WHEAT_US_HRW': 'wheat'
            }
            
            for indicator, name in commodity_indicators.items():
                url = f"{self.world_bank_url}/v2/country/all/indicator/{indicator}"
                response = requests.get(url, params=params, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    if len(data) > 1 and data[1]:
                        value = data[1][0].get('value')
                        if value:
                            commodities[name] = {
                                'value': value,
                                'source': 'World Bank'
                            }
                            
        except Exception as e:
            logger.error(f"Error fetching commodity prices: {e}")
        
        # Add mock data for demo
        if not commodities:
            commodities = {
                'crude_oil_wti': {'value': 85.50, 'unit': 'USD/barrel'},
                'natural_gas': {'value': 3.25, 'unit': 'USD/MMBtu'},
                'copper': {'value': 8500, 'unit': 'USD/metric ton'},
                'aluminum': {'value': 2400, 'unit': 'USD/metric ton'}
            }
        
        return commodities
    
    def get_economic_indicators(self, country_code: str) -> Dict[str, Any]:
        """Get economic indicators for a country."""
        indicators = {
            'country_code': country_code,
            'timestamp': datetime.utcnow().isoformat(),
            'data': {}
        }
        
        try:
            # World Bank indicators
            indicator_codes = {
                'NY.GDP.MKTP.CD': 'gdp',
                'NY.GDP.MKTP.KD.ZG': 'gdp_growth',
                'FP.CPI.TOTL.ZG': 'inflation',
                'SL.UEM.TOTL.ZS': 'unemployment'
            }
            
            for code, name in indicator_codes.items():
                url = f"{self.world_bank_url}/v2/country/{country_code}/indicator/{code}"
                params = {
                    'format': 'json',
                    'date': '2020:2024',
                    'per_page': 5
                }
                
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    if len(data) > 1 and data[1]:
                        # Get most recent non-null value
                        for entry in data[1]:
                            if entry.get('value') is not None:
                                indicators['data'][name] = {
                                    'value': entry['value'],
                                    'year': entry['date']
                                }
                                break
                                
        except Exception as e:
            logger.error(f"Error fetching economic indicators: {e}")
        
        return indicators
    
    def calculate_financial_risk_score(self, supplier_ticker: str = None,
                                     country_code: str = None) -> float:
        """Calculate financial risk score for supplier/country."""
        risk_score = 0.5  # Base score
        
        # Country risk factors
        if country_code:
            indicators = self.get_economic_indicators(country_code)
            
            # GDP growth
            gdp_growth = indicators['data'].get('gdp_growth', {}).get('value', 0)
            if gdp_growth < 0:
                risk_score += 0.2
            elif gdp_growth < 2:
                risk_score += 0.1
            
            # Inflation
            inflation = indicators['data'].get('inflation', {}).get('value', 0)
            if inflation > 10:
                risk_score += 0.2
            elif inflation > 5:
                risk_score += 0.1
            
            # Unemployment
            unemployment = indicators['data'].get('unemployment', {}).get('value', 0)
            if unemployment > 10:
                risk_score += 0.1
        
        # Company-specific risk (if ticker provided)
        if supplier_ticker and self.polygon_key:
            try:
                # Get stock volatility
                url = f"https://api.polygon.io/v2/aggs/ticker/{supplier_ticker}/range/1/day/2024-01-01/2024-12-31"
                params = {'apiKey': self.polygon_key}
                
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('results'):
                        # Calculate simple volatility
                        prices = [r['c'] for r in data['results']]
                        if len(prices) > 20:
                            returns = [(prices[i] - prices[i-1])/prices[i-1] 
                                     for i in range(1, len(prices))]
                            volatility = sum(abs(r) for r in returns) / len(returns)
                            
                            if volatility > 0.05:  # 5% daily volatility
                                risk_score += 0.2
                            elif volatility > 0.03:
                                risk_score += 0.1
                                
            except Exception as e:
                logger.debug(f"Error calculating stock volatility: {e}")
        
        return min(risk_score, 1.0)
    
    def get_market_news(self, query: str, days_back: int = 7) -> List[Dict[str, Any]]:
        """Get financial market news."""
        news = []
        
        if self.alpha_vantage_key:
            try:
                url = "https://www.alphavantage.co/query"
                params = {
                    'function': 'NEWS_SENTIMENT',
                    'tickers': query,
                    'apikey': self.alpha_vantage_key,
                    'limit': 20
                }
                
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    for article in data.get('feed', []):
                        news.append({
                            'title': article.get('title'),
                            'summary': article.get('summary'),
                            'url': article.get('url'),
                            'published': article.get('time_published'),
                            'sentiment_score': article.get('overall_sentiment_score', 0),
                            'sentiment_label': article.get('overall_sentiment_label'),
                            'source': article.get('source')
                        })
                        
            except Exception as e:
                logger.error(f"Error fetching market news: {e}")
        
        return news
