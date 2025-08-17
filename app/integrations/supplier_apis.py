"""
Supplier data integration - OpenCorporates, SEC, public registries
"""
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from flask import current_app
import re

logger = logging.getLogger(__name__)

class SupplierIntegration:
    """Integration with supplier and company data sources."""
    
    def __init__(self):
        self.opencorporates_base = "https://api.opencorporates.com/v0.4"
        self.sec_edgar_base = "https://data.sec.gov"
        self.companies_house_base = "https://api.company-information.service.gov.uk"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'SupplyChainX/1.0 (supply-chain-monitoring)'
        })
    
    def search_opencorporates(self, company_name: str, 
                            jurisdiction: str = None) -> List[Dict[str, Any]]:
        """Search for company information in OpenCorporates."""
        try:
            params = {
                'q': company_name,
                'format': 'json',
                'order': 'score'
            }
            
            if jurisdiction:
                params['jurisdiction_code'] = jurisdiction
            
            response = self.session.get(
                f"{self.opencorporates_base}/companies/search",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            companies = []
            
            for company in data.get('results', {}).get('companies', []):
                company_data = company.get('company', {})
                companies.append({
                    'name': company_data.get('name'),
                    'company_number': company_data.get('company_number'),
                    'jurisdiction': company_data.get('jurisdiction_code'),
                    'incorporation_date': company_data.get('incorporation_date'),
                    'dissolution_date': company_data.get('dissolution_date'),
                    'company_type': company_data.get('company_type'),
                    'registry_url': company_data.get('registry_url'),
                    'current_status': company_data.get('current_status'),
                    'registered_address': company_data.get('registered_address', {}).get('in_full'),
                    'opencorporates_url': company_data.get('opencorporates_url'),
                    'source': 'opencorporates'
                })
            
            return companies
            
        except Exception as e:
            logger.error(f"Error searching OpenCorporates: {e}")
            return []
    
    def get_company_details(self, company_number: str, 
                          jurisdiction: str) -> Optional[Dict[str, Any]]:
        """Get detailed company information from OpenCorporates."""
        try:
            url = f"{self.opencorporates_base}/companies/{jurisdiction}/{company_number}"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            company = data.get('results', {}).get('company', {})
            
            # Extract officers
            officers = []
            for officer in company.get('officers', []):
                officers.append({
                    'name': officer.get('name'),
                    'position': officer.get('position'),
                    'start_date': officer.get('start_date'),
                    'end_date': officer.get('end_date')
                })
            
            # Extract filings
            filings = []
            for filing in company.get('filings', [])[:10]:  # Recent 10
                filings.append({
                    'title': filing.get('title'),
                    'date': filing.get('date'),
                    'description': filing.get('description')
                })
            
            return {
                'name': company.get('name'),
                'company_number': company.get('company_number'),
                'jurisdiction': company.get('jurisdiction_code'),
                'incorporation_date': company.get('incorporation_date'),
                'company_type': company.get('company_type'),
                'current_status': company.get('current_status'),
                'registered_address': company.get('registered_address', {}).get('in_full'),
                'officers': officers,
                'filings': filings,
                'industry_codes': company.get('industry_codes', []),
                'alternative_names': company.get('alternative_names', []),
                'source': 'opencorporates',
                'last_updated': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting company details: {e}")
            return None
    
    def get_sec_filings(self, ticker: str, filing_type: str = '10-K') -> List[Dict[str, Any]]:
        """Get SEC filings for a US company."""
        try:
            # First, get CIK from ticker
            cik = self._get_cik_from_ticker(ticker)
            if not cik:
                return []
            
            # Get submissions
            url = f"{self.sec_edgar_base}/submissions/CIK{cik:010d}.json"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            filings = []
            
            # Extract recent filings
            recent_filings = data.get('filings', {}).get('recent', {})
            
            forms = recent_filings.get('form', [])
            filing_dates = recent_filings.get('filingDate', [])
            accession_numbers = recent_filings.get('accessionNumber', [])
            
            for i in range(min(len(forms), 20)):  # Last 20 filings
                if filing_type and forms[i] != filing_type:
                    continue
                
                filings.append({
                    'form_type': forms[i],
                    'filing_date': filing_dates[i] if i < len(filing_dates) else None,
                    'accession_number': accession_numbers[i] if i < len(accession_numbers) else None,
                    'url': f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_numbers[i].replace('-', '')}/{accession_numbers[i]}-index.htm"
                })
            
            return filings
            
        except Exception as e:
            logger.error(f"Error getting SEC filings: {e}")
            return []
    
    def search_companies_house(self, company_name: str) -> List[Dict[str, Any]]:
        """Search UK Companies House (requires API key)."""
        try:
            api_key = current_app.config.get('COMPANIES_HOUSE_API_KEY')
            if not api_key:
                return []
            
            response = self.session.get(
                f"{self.companies_house_base}/search/companies",
                params={'q': company_name},
                auth=(api_key, ''),
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                companies = []
                
                for item in data.get('items', []):
                    companies.append({
                        'name': item.get('title'),
                        'company_number': item.get('company_number'),
                        'date_of_creation': item.get('date_of_creation'),
                        'company_status': item.get('company_status'),
                        'company_type': item.get('company_type'),
                        'registered_office_address': item.get('address_snippet'),
                        'source': 'companies_house'
                    })
                
                return companies
                
        except Exception as e:
            logger.error(f"Error searching Companies House: {e}")
        
        return []
    
    def assess_supplier_risk(self, company_name: str) -> Dict[str, Any]:
        """Assess supplier risk based on public data."""
        risk_assessment = {
            'company_name': company_name,
            'risk_score': 0.5,  # Default medium risk
            'risk_factors': [],
            'data_sources': [],
            'assessed_at': datetime.utcnow().isoformat()
        }
        
        try:
            # Search OpenCorporates
            oc_results = self.search_opencorporates(company_name)
            
            if oc_results:
                company = oc_results[0]
                risk_assessment['data_sources'].append('opencorporates')
                
                # Check dissolution
                if company.get('dissolution_date'):
                    risk_assessment['risk_factors'].append({
                        'type': 'dissolved',
                        'severity': 'critical',
                        'description': f"Company dissolved on {company['dissolution_date']}"
                    })
                    risk_assessment['risk_score'] = 1.0
                
                # Check status
                status = company.get('current_status', '').lower()
                if 'inactive' in status or 'dissolved' in status:
                    risk_assessment['risk_factors'].append({
                        'type': 'inactive',
                        'severity': 'high',
                        'description': f"Company status: {status}"
                    })
                    risk_assessment['risk_score'] = max(risk_assessment['risk_score'], 0.8)
                
                # Check age
                if company.get('incorporation_date'):
                    try:
                        inc_date = datetime.strptime(company['incorporation_date'], '%Y-%m-%d')
                        age_years = (datetime.utcnow() - inc_date).days / 365
                        
                        if age_years < 2:
                            risk_assessment['risk_factors'].append({
                                'type': 'new_company',
                                'severity': 'medium',
                                'description': f"Company age: {age_years:.1f} years"
                            })
                            risk_assessment['risk_score'] = max(risk_assessment['risk_score'], 0.6)
                    except:
                        pass
            
            # Get financial health indicators from SEC if US company
            ticker = self._extract_ticker(company_name)
            if ticker:
                sec_filings = self.get_sec_filings(ticker)
                if sec_filings:
                    risk_assessment['data_sources'].append('sec_edgar')
                    
                    # Check filing recency
                    if sec_filings:
                        latest_filing = sec_filings[0]
                        filing_date = datetime.strptime(latest_filing['filing_date'], '%Y-%m-%d')
                        days_old = (datetime.utcnow() - filing_date).days
                        
                        if days_old > 180:
                            risk_assessment['risk_factors'].append({
                                'type': 'stale_filings',
                                'severity': 'low',
                                'description': f"Latest filing {days_old} days old"
                            })
            
            # Calculate final risk score
            if risk_assessment['risk_factors']:
                severity_scores = {
                    'critical': 1.0,
                    'high': 0.8,
                    'medium': 0.5,
                    'low': 0.3
                }
                
                max_severity = max(
                    severity_scores.get(f['severity'], 0.5) 
                    for f in risk_assessment['risk_factors']
                )
                risk_assessment['risk_score'] = max_severity
            
            # Add risk level
            if risk_assessment['risk_score'] >= 0.8:
                risk_assessment['risk_level'] = 'critical'
            elif risk_assessment['risk_score'] >= 0.6:
                risk_assessment['risk_level'] = 'high'
            elif risk_assessment['risk_score'] >= 0.4:
                risk_assessment['risk_level'] = 'medium'
            else:
                risk_assessment['risk_level'] = 'low'
            
        except Exception as e:
            logger.error(f"Error assessing supplier risk: {e}")
            risk_assessment['error'] = str(e)
        
        return risk_assessment
    
    def get_company_news(self, company_name: str, days_back: int = 30) -> List[Dict[str, Any]]:
        """Get recent news about a company using GDELT."""
        try:
            from app.integrations.geopolitical_apis import GeopoliticalIntegration
            geo_api = GeopoliticalIntegration()
            
            # Query GDELT for company mentions
            events = geo_api.query_gdelt_events(company_name, timeframe=days_back*24)
            
            # Filter and enrich
            news_items = []
            for event in events:
                news_items.append({
                    'title': event.get('event_details', {}).get('title'),
                    'date': event.get('event_details', {}).get('date'),
                    'source': event.get('event_details', {}).get('domain'),
                    'url': event.get('event_details', {}).get('url'),
                    'tone': event.get('event_details', {}).get('tone'),
                    'themes': event.get('event_details', {}).get('themes', [])
                })
            
            return news_items
            
        except Exception as e:
            logger.error(f"Error getting company news: {e}")
            return []
    
    def normalize_company_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize company data to common format."""
        normalized = {
            'source': raw_data.get('source', 'unknown'),
            'timestamp': raw_data.get('timestamp', datetime.utcnow().isoformat()),
            'data_type': 'company_info',
            'license': self._get_data_license(raw_data.get('source'))
        }
        
        # Map fields based on source
        if raw_data.get('source') == 'opencorporates':
            normalized.update({
                'company_info': {
                    'name': raw_data.get('name'),
                    'registration_number': raw_data.get('company_number'),
                    'jurisdiction': raw_data.get('jurisdiction'),
                    'status': raw_data.get('current_status'),
                    'incorporation_date': raw_data.get('incorporation_date'),
                    'dissolution_date': raw_data.get('dissolution_date'),
                    'address': raw_data.get('registered_address'),
                    'type': raw_data.get('company_type')
                }
            })
        
        elif raw_data.get('source') == 'sec_edgar':
            normalized.update({
                'financial_filings': raw_data.get('filings', [])
            })
        
        elif raw_data.get('source') == 'companies_house':
            normalized.update({
                'company_info': {
                    'name': raw_data.get('name'),
                    'registration_number': raw_data.get('company_number'),
                    'status': raw_data.get('company_status'),
                    'incorporation_date': raw_data.get('date_of_creation'),
                    'address': raw_data.get('registered_office_address'),
                    'type': raw_data.get('company_type')
                }
            })
        
        return normalized
    
    # Helper methods
    def _get_cik_from_ticker(self, ticker: str) -> Optional[str]:
        """Get CIK number from ticker symbol."""
        try:
            # SEC maintains a ticker to CIK mapping
            url = "https://www.sec.gov/files/company_tickers.json"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            tickers = response.json()
            
            for entry in tickers.values():
                if entry.get('ticker', '').upper() == ticker.upper():
                    return entry.get('cik_str')
                    
        except Exception as e:
            logger.error(f"Error getting CIK from ticker: {e}")
        
        return None
    
    def _extract_ticker(self, company_name: str) -> Optional[str]:
        """Try to extract ticker from company name."""
        # Common patterns like "Apple Inc. (AAPL)"
        match = re.search(r'\(([A-Z]{1,5})\)', company_name)
        if match:
            return match.group(1)
        
        # Known mappings (simplified)
        known_tickers = {
            'apple': 'AAPL',
            'microsoft': 'MSFT',
            'amazon': 'AMZN',
            'google': 'GOOGL',
            'alphabet': 'GOOGL'
        }
        
        company_lower = company_name.lower()
        for key, ticker in known_tickers.items():
            if key in company_lower:
                return ticker
        
        return None
    
    def _get_data_license(self, source: str) -> str:
        """Get data license for source."""
        licenses = {
            'opencorporates': 'CC BY-SA 4.0',
            'sec_edgar': 'Public Domain',
            'companies_house': 'UK Open Government Licence',
            'sedar': 'SEDAR+ Terms of Use'
        }
        return licenses.get(source, 'Unknown')
