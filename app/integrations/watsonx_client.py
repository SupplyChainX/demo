"""
IBM watsonx.ai client for Granite model integration
"""
import logging
import json
from typing import Dict, List, Any, Optional
from flask import current_app
import requests

logger = logging.getLogger(__name__)

class WatsonxClient:
    """Client for IBM watsonx.ai API integration."""
    
    def __init__(self):
        import os
        # Get config directly from environment variables to avoid Flask context issues
        self.api_key = os.environ.get('WATSONX_API_KEY')
        self.project_id = os.environ.get('WATSONX_PROJECT_ID')
        self.base_url = os.environ.get('WATSONX_URL', 'https://us-south.ml.cloud.ibm.com')
        
        # Fallback to current_app config if available
        try:
            if current_app:
                self.api_key = self.api_key or current_app.config.get('WATSONX_API_KEY')
                self.project_id = self.project_id or current_app.config.get('WATSONX_PROJECT_ID')
                self.base_url = self.base_url or current_app.config.get('WATSONX_URL', 'https://us-south.ml.cloud.ibm.com')
        except RuntimeError:
            # No app context available, use environment variables
            pass
            
        self.auth_token = None
        self.token_expiry = None
        
        # Validate required configuration
        if not self.api_key:
            logger.error("WATSONX_API_KEY not found in configuration")
        if not self.project_id:
            logger.error("WATSONX_PROJECT_ID not found in configuration")
        
    def _get_auth_token(self) -> str:
        """Get or refresh authentication token."""
        # Check if we have a valid token
        if self.auth_token and self.token_expiry:
            from datetime import datetime
            if datetime.utcnow() < self.token_expiry:
                return self.auth_token
        
        # Get new token
        try:
            auth_url = "https://iam.cloud.ibm.com/identity/token"
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json"
            }
            data = {
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey": self.api_key
            }
            
            response = requests.post(auth_url, headers=headers, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            self.auth_token = token_data['access_token']
            
            # Set expiry (subtract 5 minutes for safety)
            from datetime import datetime, timedelta
            expires_in = token_data.get('expires_in', 3600)
            self.token_expiry = datetime.utcnow() + timedelta(seconds=expires_in - 300)
            
            return self.auth_token
            
        except Exception as e:
            logger.error(f"Error getting auth token: {e}")
            raise
    
    def generate(self, prompt: str, model_id: str = 'ibm/granite-3-2b-instruct',
                max_tokens: int = 500, temperature: float = 0.7,
                top_p: float = 0.95, stop_sequences: List[str] = None) -> str:
        """Generate text using watsonx.ai model."""
        try:
            token = self._get_auth_token()
            
            url = f"{self.base_url}/ml/v1/text/generation?version=2024-01-01"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            payload = {
                "model_id": model_id,
                "input": prompt,
                "parameters": {
                    "max_new_tokens": max_tokens,
                    "temperature": temperature,
                    "top_p": top_p,
                    "repetition_penalty": 1.1,
                    "truncate_input_tokens": 2048
                },
                "project_id": self.project_id
            }
            
            if stop_sequences:
                payload["parameters"]["stop_sequences"] = stop_sequences
            
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            generated_text = result['results'][0]['generated_text']
            
            # Log token usage
            logger.info(f"Generated {result['results'][0]['generated_token_count']} tokens")
            
            return generated_text
            
        except Exception as e:
            logger.error(f"Error generating text: {e}")
            # Return a fallback response
            return "Unable to generate AI response at this time."
    
    def generate_embeddings(self, texts: List[str], 
                          model_id: str = 'ibm/slate-125m-english-rtrvr') -> List[List[float]]:
        """Generate embeddings for texts."""
        try:
            token = self._get_auth_token()
            
            url = f"{self.base_url}/ml/v1/text/embeddings?version=2024-01-01"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            payload = {
                "model_id": model_id,
                "inputs": texts,
                "project_id": self.project_id
            }
            
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            embeddings = [r['embedding'] for r in result['results']]
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            # Return zero vectors as fallback
            return [[0.0] * 384 for _ in texts]
    
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment of text using Granite model."""
        try:
            prompt = f"""Analyze the sentiment of the following text and provide a JSON response with:
1. sentiment: positive, negative, or neutral
2. confidence: 0-1 score
3. key_phrases: list of important phrases
4. summary: one sentence summary

Text: {text}

Response:"""
            
            response = self.generate(
                prompt=prompt,
                temperature=0.3,
                max_tokens=200
            )
            
            # Parse JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            
            # Fallback
            return {
                "sentiment": "neutral",
                "confidence": 0.5,
                "key_phrases": [],
                "summary": "Unable to analyze"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return {
                "sentiment": "neutral",
                "confidence": 0.0,
                "key_phrases": [],
                "summary": "Analysis failed"
            }
    
    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract named entities from text."""
        try:
            prompt = f"""Extract named entities from the following text and categorize them:
- Organizations
- Locations
- Products
- Dates
- Money amounts

Text: {text}

Provide the response as a JSON object with these categories as keys."""
            
            response = self.generate(
                prompt=prompt,
                temperature=0.2,
                max_tokens=300
            )
            
            # Parse JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            
            return {}
            
        except Exception as e:
            logger.error(f"Error extracting entities: {e}")
            return {}
    
    def generate_summary(self, text: str, max_length: int = 100) -> str:
        """Generate a summary of the text."""
        try:
            prompt = f"""Summarize the following text in no more than {max_length} words:

{text}

Summary:"""
            
            response = self.generate(
                prompt=prompt,
                temperature=0.5,
                max_tokens=max_length * 2  # Approximate tokens
            )
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return "Summary generation failed."
    
    def classify_text(self, text: str, categories: List[str]) -> Dict[str, float]:
        """Classify text into given categories."""
        try:
            categories_str = ", ".join(categories)
            prompt = f"""Classify the following text into one or more of these categories: {categories_str}

Text: {text}

For each relevant category, provide a confidence score (0-1). 
Response format: {{"category1": 0.8, "category2": 0.3}}"""
            
            response = self.generate(
                prompt=prompt,
                temperature=0.3,
                max_tokens=100
            )
            
            # Parse JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                scores = json.loads(json_match.group())
                # Normalize to provided categories
                return {cat: scores.get(cat, 0.0) for cat in categories}
            
            return {cat: 0.0 for cat in categories}
            
        except Exception as e:
            logger.error(f"Error classifying text: {e}")
            return {cat: 0.0 for cat in categories}
