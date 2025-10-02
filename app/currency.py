"""Currency conversion service for Splittchen."""

import requests
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from typing import Dict, Optional, List, Tuple
from flask import current_app

from app import db
from app.models import ExchangeRate


# Supported currencies with their symbols and names
SUPPORTED_CURRENCIES = {
    'USD': {'symbol': '$', 'name': 'US Dollar'},
    'EUR': {'symbol': '€', 'name': 'Euro'},
    'GBP': {'symbol': '£', 'name': 'British Pound'},
    'JPY': {'symbol': '¥', 'name': 'Japanese Yen'},
    'CAD': {'symbol': 'C$', 'name': 'Canadian Dollar'},
    'AUD': {'symbol': 'A$', 'name': 'Australian Dollar'},
    'CHF': {'symbol': 'CHF', 'name': 'Swiss Franc'},
    'CNY': {'symbol': '¥', 'name': 'Chinese Yuan'},
    'SEK': {'symbol': 'kr', 'name': 'Swedish Krona'},
    'NOK': {'symbol': 'kr', 'name': 'Norwegian Krone'},
    'DKK': {'symbol': 'kr', 'name': 'Danish Krone'},
    'PLN': {'symbol': 'zł', 'name': 'Polish Złoty'},
    'CZK': {'symbol': 'Kč', 'name': 'Czech Koruna'},
    'HUF': {'symbol': 'Ft', 'name': 'Hungarian Forint'},
    'RUB': {'symbol': '₽', 'name': 'Russian Ruble'},
    'BRL': {'symbol': 'R$', 'name': 'Brazilian Real'},
    'MXN': {'symbol': '$', 'name': 'Mexican Peso'},
    'INR': {'symbol': '₹', 'name': 'Indian Rupee'},
    'KRW': {'symbol': '₩', 'name': 'South Korean Won'},
    'SGD': {'symbol': 'S$', 'name': 'Singapore Dollar'},
    'HKD': {'symbol': 'HK$', 'name': 'Hong Kong Dollar'},
    'NZD': {'symbol': 'NZ$', 'name': 'New Zealand Dollar'},
}


class CurrencyService:
    """Service for handling currency conversions and exchange rates."""
    
    def __init__(self):
        self.api_base_url = "https://open.er-api.com/v6"
        self.cache_duration = 3600  # 1 hour in seconds
    
    def get_supported_currencies(self) -> Dict[str, Dict[str, str]]:
        """Get list of supported currencies."""
        return SUPPORTED_CURRENCIES
    
    def get_currency_choices(self) -> List[Tuple[str, str]]:
        """Get currency choices for form dropdowns."""
        return [(code, f"{data['symbol']} {code} - {data['name']}") 
                for code, data in SUPPORTED_CURRENCIES.items()]
    
    def get_exchange_rate(self, from_currency: str, to_currency: str) -> Optional[Decimal]:
        """Get exchange rate from cache or API.
        
        Args:
            from_currency: Source currency code (e.g., 'USD')
            to_currency: Target currency code (e.g., 'EUR')
            
        Returns:
            Exchange rate as Decimal, or None if unavailable
        """
        if from_currency == to_currency:
            return Decimal('1.0')
        
        # Check cache first
        cached_rate = self._get_cached_rate(from_currency, to_currency)
        if cached_rate and not cached_rate.is_stale:
            return cached_rate.rate
        
        # Fetch from API
        try:
            rate = self._fetch_rate_from_api(from_currency, to_currency)
            if rate:
                # Update cache
                self._update_cache(from_currency, to_currency, rate)
                return rate
        except Exception as e:
            current_app.logger.error(f"Failed to fetch exchange rate {from_currency}/{to_currency}: {e}")
        
        # Return stale cache if API fails
        if cached_rate:
            current_app.logger.warning(f"Using stale exchange rate for {from_currency}/{to_currency}")
            return cached_rate.rate
        
        return None
    
    def convert_amount(self, amount: Decimal, from_currency: str, to_currency: str) -> Optional[Decimal]:
        """Convert amount from one currency to another.
        
        Args:
            amount: Amount to convert
            from_currency: Source currency code (e.g., 'USD')
            to_currency: Target currency code (e.g., 'EUR')
            
        Returns:
            Converted amount as Decimal, or None if conversion fails
        """
        if from_currency == to_currency:
            return amount
        
        rate = self.get_exchange_rate(from_currency, to_currency)
        if rate is None:
            return None
        
        # Perform conversion with proper rounding
        converted = amount * rate
        return converted.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def format_amount(self, amount: Decimal, currency: str) -> str:
        """Format amount with appropriate currency symbol."""
        if currency not in SUPPORTED_CURRENCIES:
            return f"{amount:.2f} {currency}"
        
        symbol = SUPPORTED_CURRENCIES[currency]['symbol']
        
        # Handle different formatting for different currencies
        if currency == 'JPY' or currency == 'KRW':
            # No decimal places for these currencies
            return f"{symbol}{amount:.0f}"
        else:
            return f"{symbol}{amount:.2f}"
    
    def _get_cached_rate(self, from_currency: str, to_currency: str) -> Optional[ExchangeRate]:
        """Get cached exchange rate from database."""
        return ExchangeRate.query.filter_by(
            from_currency=from_currency,
            to_currency=to_currency
        ).first()
    
    def _fetch_rate_from_api(self, from_currency: str, to_currency: str) -> Optional[Decimal]:
        """Fetch exchange rate from external API."""
        try:
            # Using open.er-api.com - free API without key requirement
            url = f"{self.api_base_url}/latest/{from_currency}"
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get('result') == 'success' and 'rates' in data:
                rates = data['rates']
                if to_currency in rates:
                    rate = Decimal(str(rates[to_currency]))
                    current_app.logger.info(f"Fetched exchange rate {from_currency}/{to_currency}: {rate}")
                    return rate
                else:
                    current_app.logger.error(f"Currency {to_currency} not found in rates")
                    return None
            else:
                current_app.logger.error(f"API returned error: {data}")
                return None
                
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Request failed for {from_currency}/{to_currency}: {e}")
            return None
        except (ValueError, KeyError) as e:
            current_app.logger.error(f"Failed to parse API response: {e}")
            return None
    
    def _update_cache(self, from_currency: str, to_currency: str, rate: Decimal) -> None:
        """Update exchange rate cache in database."""
        try:
            cached_rate = self._get_cached_rate(from_currency, to_currency)
            
            if cached_rate:
                cached_rate.rate = rate
                cached_rate.updated_at = datetime.now(timezone.utc)
            else:
                cached_rate = ExchangeRate()
                cached_rate.from_currency = from_currency
                cached_rate.to_currency = to_currency
                cached_rate.rate = rate
                cached_rate.updated_at = datetime.now(timezone.utc)
                db.session.add(cached_rate)
            
            db.session.commit()
            current_app.logger.info(f"Updated exchange rate cache {from_currency}/{to_currency}: {rate}")
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to update exchange rate cache: {e}")
    
    def get_latest_rates(self, base_currency: str = 'USD') -> Dict[str, Decimal]:
        """Get latest rates for all supported currencies."""
        rates = {}
        
        for currency in SUPPORTED_CURRENCIES.keys():
            if currency != base_currency:
                rate = self.get_exchange_rate(base_currency, currency)
                if rate:
                    rates[currency] = rate
        
        return rates
    
    def clean_stale_rates(self) -> None:
        """Clean up stale exchange rates from cache (older than 24 hours)."""
        try:
            stale_cutoff = datetime.now(timezone.utc).timestamp() - (24 * 3600)
            stale_rates = ExchangeRate.query.filter(
                ExchangeRate.updated_at < datetime.fromtimestamp(stale_cutoff, timezone.utc)
            ).all()
            
            for rate in stale_rates:
                db.session.delete(rate)
            
            db.session.commit()
            current_app.logger.info(f"Cleaned {len(stale_rates)} stale exchange rates")
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to clean stale exchange rates: {e}")


# Global currency service instance
currency_service = CurrencyService()