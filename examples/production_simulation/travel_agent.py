#!/usr/bin/env python3
"""
Production-Like Travel Agent - HTTP-Based Tool Communication

This script demonstrates a production-like agent that communicates via HTTP,
mimicking an AWS Bedrock Agent architecture. All tool calls are made through
HTTP requests rather than direct Python function calls.

Key Features:
- Tools are HTTP clients (httpx) that call external services
- All requests go through the chaos proxy (localhost:8080)
- Strictly network-layer communication
- Validates sidecar proxy capabilities

Architecture:
    User Request
        ↓
    LangChain Agent (ChatOllama)
        ↓
    Tool Call Generated
        ↓
    HTTP Client (httpx with proxy)
        ↓
    Chaos Proxy (localhost:8080) ← Chaos interception happens here
        ↓
    Mock Server (localhost:8001)
        ↓
    Response (or error)
        ↓
    Agent Processing
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

# Add project root to path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# CRITICAL: Configure proxy for ALL HTTP requests
# This ensures all tool calls go through the chaos proxy
os.environ["HTTP_PROXY"] = "http://localhost:8080"
os.environ["HTTPS_PROXY"] = "http://localhost:8080"
os.environ["NO_PROXY"] = ""  # Ensure localhost goes through proxy

try:
    from langchain_core.tools import tool
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    from langchain_ollama import ChatOllama
    from langchain_core.output_parsers import StrOutputParser
    import httpx
    import yaml
    LANGCHAIN_AVAILABLE = True
except ImportError as e:
    LANGCHAIN_AVAILABLE = False
    print(f"Warning: Required dependencies not available: {e}")
    print("Please install: langchain, langchain-ollama, httpx")


class HTTPToolWrapper:
    """
    Wrapper for HTTP-based tools that use httpx with proxy configuration.
    
    This ensures all HTTP requests go through the chaos proxy (localhost:8080)
    and validates sidecar capabilities.
    """
    
    def __init__(self, base_url: str = "http://127.0.0.1:8001", validation_rules: Optional[Dict[str, Any]] = None):
        """
        Initialize HTTP tool wrapper.
        
        Args:
            base_url: Base URL for the mock server
        """
        self.base_url = base_url
        self.validation_rules = validation_rules or {}
        # CRITICAL: Create httpx client with proxy configuration
        # All requests will go through localhost:8080 (chaos proxy)
        # Note: httpx 0.28+ uses 'proxy' (singular) parameter, not 'proxies'
        proxy_url = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or "http://localhost:8080"
        self.client = httpx.Client(
            proxy=proxy_url,  # Single proxy URL for all requests
            headers={
                "Content-Type": "application/json",
                "X-Agent-Role": "TravelAgent",  # For group-based chaos strategies
            },
            timeout=30.0,
            trust_env=False,  # IMPORTANT: do not honor NO_PROXY so localhost also goes through proxy
        )
        self.metrics = {
            "tool_calls": 0,
            "tool_success": 0,
            "tool_errors": 0,
            "validation_errors": 0,
            "validation_fixed": 0,
            "retries": 0,
            "retries_success": 0,
        }
        self.last_flight_ids: list[str] = []
        print(f"✓ HTTP client configured with proxy: {os.environ.get('HTTP_PROXY', 'http://localhost:8080')}")
        print(f"✓ Target server: {base_url}")

    def _record(self, key: str, inc: int = 1) -> None:
        self.metrics[key] = self.metrics.get(key, 0) + inc

    def _normalize_airport_code(self, value: str, fallback: str) -> tuple[str, bool]:
        if not value:
            return fallback, True
        cleaned = "".join(ch for ch in value.upper() if ch.isalpha())
        regex = self.validation_rules.get("airport_code_regex", r"^[A-Z]{3}$")
        if len(cleaned) >= 3:
            candidate = cleaned[:3]
            if re.match(regex, candidate):
                return candidate, candidate != value.upper()
        return fallback, True

    def _normalize_date(self, value: str) -> tuple[str, bool]:
        try:
            fmt = self.validation_rules.get("date_format", "%Y-%m-%d")
            parsed = datetime.strptime(value, fmt)
            min_days = int(self.validation_rules.get("min_days_ahead", 1))
            max_days = int(self.validation_rules.get("max_days_ahead", 365))
            today = datetime.utcnow().date()
            if parsed.date() < (today + timedelta(days=min_days)):
                fixed_date = (today + timedelta(days=min_days + 6)).strftime(fmt)
                return fixed_date, True
            if parsed.date() > (today + timedelta(days=max_days)):
                fixed_date = (today + timedelta(days=min_days + 6)).strftime(fmt)
                return fixed_date, True
            return value, False
        except Exception:
            fmt = self.validation_rules.get("date_format", "%Y-%m-%d")
            fixed_date = (datetime.utcnow() + timedelta(days=7)).strftime(fmt)
            return fixed_date, True

    def _normalize_flight_id(self, value: str) -> tuple[str, bool]:
        if value and value in self.last_flight_ids:
            return value, False
        if self.last_flight_ids:
            return self.last_flight_ids[0], True
        return value, False

    def _log_validation_fix(self, field: str, original: str, fixed: str) -> None:
        if original != fixed:
            self._record("validation_fixed")
            print(f"[Validation] {field} fixed: '{original}' -> '{fixed}'")
    
    def search_flights(self, origin: str, destination: str, date: str) -> str:
        """
        Search for flights via HTTP request.
        
        This is an HTTP client call, not a Python function. It mimics
        how AWS Bedrock Agent would call external services.
        
        Args:
            origin: Origin airport code (e.g., "JFK")
            destination: Destination airport code (e.g., "LAX")
            date: Flight date in YYYY-MM-DD format
            
        Returns:
            JSON string with flight search results
        """
        url = f"{self.base_url}/search_flights"
        
        self._record("tool_calls")
        origin_fixed, origin_changed = self._normalize_airport_code(origin, self.validation_rules.get("default_origin", "JFK"))
        destination_fixed, destination_changed = self._normalize_airport_code(destination, self.validation_rules.get("default_destination", "LAX"))
        date_fixed, date_changed = self._normalize_date(date)
        if origin_changed or destination_changed or date_changed:
            self._record("validation_errors")
            self._log_validation_fix("origin", origin, origin_fixed)
            self._log_validation_fix("destination", destination, destination_fixed)
            self._log_validation_fix("date", date, date_fixed)

        payload = {
            "origin": origin_fixed,
            "destination": destination_fixed,
            "date": date_fixed,
        }
        
        try:
            print(f"\n[HTTP Tool] POST {url}")
            print(f"  Payload: {json.dumps(payload, indent=2)}")
            print(f"  → Request going through proxy: {os.environ.get('HTTP_PROXY')}")
            
            # HTTP request goes through proxy (localhost:8080)
            # Chaos interception happens here if proxy is configured
            response = self.client.post(url, json=payload)
            retried = False
            if response.status_code in (400, 422):
                self._record("retries")
                retried = True
                retry_payload = {
                    "origin": "JFK",
                    "destination": "LAX",
                    "date": self._normalize_date(date_fixed)[0],
                }
                print("[Validation] Retrying search with safe defaults.")
                response = self.client.post(url, json=retry_payload)
            
            print(f"  ← Response: {response.status_code}")
            
            # Log error if non-200 response
            if response.status_code >= 400:
                self._record("tool_errors")
                import logging
                logger = logging.getLogger("travel_agent")
                from agent_chaos_sdk.common.file_logger import log_error
                error_detail = response.json().get("detail", "Unknown error") if response.content else "Unknown error"
                log_error(
                    logger,
                    error_type=f"http_{response.status_code}",
                    message=f"Tool call failed: {error_detail}",
                    url=url
                )
            
            if response.status_code == 200:
                self._record("tool_success")
                if retried:
                    self._record("retries_success")
                result = response.json()
                self.last_flight_ids = [f["flight_id"] for f in result.get("flights", []) if "flight_id" in f]
                # Format response for agent
                flights_str = "\n".join([
                    f"Flight {f['flight_id']}: {f['airline']} "
                    f"{f['origin']} → {f['destination']} "
                    f"${f['price']:.2f} ({f['available_seats']} seats)"
                    for f in result.get("flights", [])
                ])
                return f"Found {result.get('total_results', 0)} flights:\n{flights_str}"
            else:
                error_detail = response.json().get("detail", "Unknown error")
                return f"Error {response.status_code}: {error_detail}"
        
        except httpx.TimeoutException:
            import logging
            logger = logging.getLogger("travel_agent")
            from agent_chaos_sdk.common.file_logger import log_error
            log_error(logger, error_type="timeout", message=f"Request timed out: {url}")
            return "Error: Request timed out. The external service may be slow or unavailable."
        except httpx.RequestError as e:
            import logging
            logger = logging.getLogger("travel_agent")
            from agent_chaos_sdk.common.file_logger import log_error
            log_error(logger, error_type="network_error", message=f"Network request failed: {str(e)}", url=url)
            return f"Error: Network request failed - {str(e)}"
        except Exception as e:
            import logging
            logger = logging.getLogger("travel_agent")
            from agent_chaos_sdk.common.file_logger import log_error
            log_error(logger, error_type="exception", message=str(e), url=url)
            return f"Error: {str(e)}"
    
    def search_hotels(self, city: str, checkin_date: str, checkout_date: str, guests: int = 1, budget_max: Optional[float] = None) -> str:
        """
        Search for hotels in a city.

        Args:
            city: City name (e.g., "New York", "Los Angeles")
            checkin_date: Check-in date in YYYY-MM-DD format
            checkout_date: Check-out date in YYYY-MM-DD format
            guests: Number of guests
            budget_max: Maximum budget per night (optional)

        Returns:
            String with hotel search results
        """
        url = f"{self.base_url}/search_hotels"

        self._record("tool_calls")
        payload = {
            "city": city,
            "checkin_date": checkin_date,
            "checkout_date": checkout_date,
            "guests": guests,
            "budget_max": budget_max
        }

        try:
            print(f"\n[HTTP Tool] POST {url}")
            print(f"  Payload: {json.dumps(payload, indent=2)}")
            print(f"  → Request going through proxy: {os.environ.get('HTTP_PROXY')}")

            response = self.client.post(url, json=payload)
            print(f"  ← Response: {response.status_code}")

            if response.status_code == 200:
                self._record("tool_success")
                result = response.json()
                hotels = result.get("hotels", [])
                hotels_str = "\n".join([
                    f"Hotel {h['hotel_id']}: {h['name']} "
                    f"({h['stars']}★) - ${h['price_per_night']:.2f}/night "
                    f"({h['amenities'][:50]}...)"  # Truncate amenities
                    for h in hotels
                ])
                return f"Found {len(hotels)} hotels in {city}:\n{hotels_str}"
            else:
                error_detail = response.json().get("detail", "Unknown error") if response.content else "Unknown error"
                return f"Error {response.status_code}: {error_detail}"

        except httpx.TimeoutException:
            return "Error: Hotel search request timed out."
        except httpx.RequestError as e:
            return f"Error: Hotel search network request failed - {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"

    def book_hotel(self, hotel_id: str, checkin_date: str, checkout_date: str, guests: int = 1) -> str:
        """
        Book a hotel room.

        Args:
            hotel_id: Hotel ID from search results
            checkin_date: Check-in date in YYYY-MM-DD format
            checkout_date: Check-out date in YYYY-MM-DD format
            guests: Number of guests

        Returns:
            String with booking confirmation
        """
        url = f"{self.base_url}/book_hotel"

        self._record("tool_calls")
        payload = {
            "hotel_id": hotel_id,
            "checkin_date": checkin_date,
            "checkout_date": checkout_date,
            "guests": guests
        }

        try:
            print(f"\n[HTTP Tool] POST {url}")
            print(f"  Payload: {json.dumps(payload, indent=2)}")
            print(f"  → Request going through proxy: {os.environ.get('HTTP_PROXY')}")

            response = self.client.post(url, json=payload)
            print(f"  ← Response: {response.status_code}")

            if response.status_code == 200:
                self._record("tool_success")
                result = response.json()
                return f"Hotel booking confirmed: {result.get('confirmation_id', 'N/A')} for {result.get('hotel_name', 'Unknown')}"
            else:
                error_detail = response.json().get("detail", "Unknown error") if response.content else "Unknown error"
                return f"Error {response.status_code}: {error_detail}"

        except httpx.TimeoutException:
            return "Error: Hotel booking request timed out."
        except httpx.RequestError as e:
            return f"Error: Hotel booking network request failed - {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"

    def search_cars(self, pickup_city: str, pickup_date: str, dropoff_date: str, passengers: int = 1) -> str:
        """
        Search for car rentals.

        Args:
            pickup_city: City for car pickup
            pickup_date: Pickup date in YYYY-MM-DD format
            dropoff_date: Dropoff date in YYYY-MM-DD format
            passengers: Number of passengers

        Returns:
            String with car rental search results
        """
        url = f"{self.base_url}/search_cars"

        self._record("tool_calls")
        payload = {
            "pickup_city": pickup_city,
            "pickup_date": pickup_date,
            "dropoff_date": dropoff_date,
            "passengers": passengers
        }

        try:
            print(f"\n[HTTP Tool] POST {url}")
            print(f"  Payload: {json.dumps(payload, indent=2)}")
            print(f"  → Request going through proxy: {os.environ.get('HTTP_PROXY')}")

            response = self.client.post(url, json=payload)
            print(f"  ← Response: {response.status_code}")

            if response.status_code == 200:
                self._record("tool_success")
                result = response.json()
                cars = result.get("cars", [])
                cars_str = "\n".join([
                    f"Car {c['car_id']}: {c['model']} "
                    f"({c['category']}) - ${c['price_per_day']:.2f}/day "
                    f"({c['seats']} seats, {c['transmission']})"
                    for c in cars
                ])
                return f"Found {len(cars)} cars in {pickup_city}:\n{cars_str}"
            else:
                error_detail = response.json().get("detail", "Unknown error") if response.content else "Unknown error"
                return f"Error {response.status_code}: {error_detail}"

        except httpx.TimeoutException:
            return "Error: Car search request timed out."
        except httpx.RequestError as e:
            return f"Error: Car search network request failed - {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"

    def book_car(self, car_id: str, pickup_date: str, dropoff_date: str) -> str:
        """
        Book a rental car.

        Args:
            car_id: Car ID from search results
            pickup_date: Pickup date in YYYY-MM-DD format
            dropoff_date: Dropoff date in YYYY-MM-DD format

        Returns:
            String with booking confirmation
        """
        url = f"{self.base_url}/book_car"

        self._record("tool_calls")
        payload = {
            "car_id": car_id,
            "pickup_date": pickup_date,
            "dropoff_date": dropoff_date
        }

        try:
            print(f"\n[HTTP Tool] POST {url}")
            print(f"  Payload: {json.dumps(payload, indent=2)}")
            print(f"  → Request going through proxy: {os.environ.get('HTTP_PROXY')}")

            response = self.client.post(url, json=payload)
            print(f"  ← Response: {response.status_code}")

            if response.status_code == 200:
                self._record("tool_success")
                result = response.json()
                return f"Car booking confirmed: {result.get('confirmation_id', 'N/A')} for {result.get('car_model', 'Unknown')}"
            else:
                error_detail = response.json().get("detail", "Unknown error") if response.content else "Unknown error"
                return f"Error {response.status_code}: {error_detail}"

        except httpx.TimeoutException:
            return "Error: Car booking request timed out."
        except httpx.RequestError as e:
            return f"Error: Car booking network request failed - {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"

    def book_ticket(self, flight_id: str) -> str:
        """
        Book a flight ticket via HTTP request.
        
        Args:
            flight_id: Flight ID to book
            
        Returns:
            JSON string with booking confirmation
        """
        url = f"{self.base_url}/book_ticket"
        
        self._record("tool_calls")
        normalized_flight_id, changed = self._normalize_flight_id(flight_id)
        if changed:
            self._record("validation_errors")
            self._log_validation_fix("flight_id", flight_id, normalized_flight_id)

        payload = {"flight_id": normalized_flight_id}
        
        try:
            print(f"\n[HTTP Tool] POST {url}")
            print(f"  Payload: {json.dumps(payload, indent=2)}")
            print(f"  → Request going through proxy: {os.environ.get('HTTP_PROXY')}")
            
            # HTTP request goes through proxy
            response = self.client.post(url, json=payload)
            retried = False
            if response.status_code in (400, 404, 422) and self.last_flight_ids:
                self._record("retries")
                retried = True
                retry_payload = {"flight_id": self.last_flight_ids[0]}
                print("[Validation] Retrying booking with last known flight_id.")
                response = self.client.post(url, json=retry_payload)
            
            print(f"  ← Response: {response.status_code}")
            
            if response.status_code == 200:
                self._record("tool_success")
                if retried:
                    self._record("retries_success")
                result = response.json()
                return (
                    f"Booking confirmed!\n"
                    f"Booking ID: {result.get('booking_id')}\n"
                    f"Confirmation Code: {result.get('confirmation_code')}\n"
                    f"Status: {result.get('status')}"
                )
            else:
                self._record("tool_errors")
                error_detail = response.json().get("detail", "Unknown error")
                return f"Error {response.status_code}: {error_detail}"
        
        except httpx.TimeoutException:
            return "Error: Request timed out. The booking service may be slow or unavailable."
        except httpx.RequestError as e:
            return f"Error: Network request failed - {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def close(self):
        """Close the HTTP client."""
        self.client.close()
        metrics_path = os.getenv("AGENT_METRICS_PATH")
        if metrics_path:
            try:
                with open(metrics_path, "w", encoding="utf-8") as metrics_file:
                    json.dump(self.metrics, metrics_file, ensure_ascii=False, indent=2)
            except Exception:
                pass


def _load_validation_rules() -> Dict[str, Any]:
    rules_path = os.getenv("AGENT_VALIDATION_RULES")
    if not rules_path:
        return {}
    try:
        with open(rules_path, "r", encoding="utf-8") as rules_file:
            rules = yaml.safe_load(rules_file) or {}
            return rules if isinstance(rules, dict) else {}
    except Exception:
        return {}


def create_http_tools(http_wrapper: HTTPToolWrapper):
    """
    Create LangChain tools that use HTTP client calls.
    
    These tools are wrappers around HTTP requests, not Python functions.
    This mimics how AWS Bedrock Agent would handle tool calls.
    
    Args:
        http_wrapper: HTTPToolWrapper instance
        
    Returns:
        List of LangChain tools
    """
    @tool
    def search_flights(origin: str, destination: str, date: str) -> str:
        """
        Search for flights between two cities.
        
        Use this tool when the user wants to find flights.
        
        Args:
            origin: Origin airport code (3 letters, e.g., "JFK", "LAX")
            destination: Destination airport code (3 letters)
            date: Flight date in YYYY-MM-DD format (e.g., "2024-12-25")
            
        Returns:
            String with flight search results
        """
        return http_wrapper.search_flights(origin, destination, date)
    
    @tool
    def book_ticket(flight_id: str) -> str:
        """
        Book a flight ticket.

        Use this tool when the user wants to book a specific flight.
        You need the flight_id from search_flights results.

        Args:
            flight_id: Flight ID (e.g., "FL-ABC12345")

        Returns:
            String with booking confirmation
        """
        return http_wrapper.book_ticket(flight_id)

    @tool
    def search_hotels(city: str, checkin_date: str, checkout_date: str, guests: int = 1, budget_max: Optional[float] = None) -> str:
        """
        Search for hotels in a city.

        Use this tool when the user needs accommodation options.

        Args:
            city: City name (e.g., "New York", "Los Angeles")
            checkin_date: Check-in date in YYYY-MM-DD format
            checkout_date: Check-out date in YYYY-MM-DD format
            guests: Number of guests (default: 1)
            budget_max: Maximum budget per night (optional)

        Returns:
            String with hotel search results
        """
        return http_wrapper.search_hotels(city, checkin_date, checkout_date, guests, budget_max)

    @tool
    def book_hotel(hotel_id: str, checkin_date: str, checkout_date: str, guests: int = 1) -> str:
        """
        Book a hotel room.

        Use this tool when the user wants to book a specific hotel.

        Args:
            hotel_id: Hotel ID from search_hotels results
            checkin_date: Check-in date in YYYY-MM-DD format
            checkout_date: Check-out date in YYYY-MM-DD format
            guests: Number of guests (default: 1)

        Returns:
            String with hotel booking confirmation
        """
        return http_wrapper.book_hotel(hotel_id, checkin_date, checkout_date, guests)

    @tool
    def search_cars(pickup_city: str, pickup_date: str, dropoff_date: str, passengers: int = 1) -> str:
        """
        Search for rental cars.

        Use this tool when the user needs transportation options.

        Args:
            pickup_city: City for car pickup
            pickup_date: Pickup date in YYYY-MM-DD format
            dropoff_date: Dropoff date in YYYY-MM-DD format
            passengers: Number of passengers (default: 1)

        Returns:
            String with car rental search results
        """
        return http_wrapper.search_cars(pickup_city, pickup_date, dropoff_date, passengers)

    @tool
    def book_car(car_id: str, pickup_date: str, dropoff_date: str) -> str:
        """
        Book a rental car.

        Use this tool when the user wants to book a specific car.

        Args:
            car_id: Car ID from search_cars results
            pickup_date: Pickup date in YYYY-MM-DD format
            dropoff_date: Dropoff date in YYYY-MM-DD format

        Returns:
            String with car booking confirmation
        """
        return http_wrapper.book_car(car_id, pickup_date, dropoff_date)

    return [search_flights, book_ticket, search_hotels, book_hotel, search_cars, book_car]


class TravelAgent:
    """
    Production-like travel agent that uses HTTP-based tools.
    
    This agent mimics AWS Bedrock Agent architecture where:
    - LLM generates tool calls
    - Tools execute via HTTP requests
    - All requests go through sidecar proxy
    """
    
    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = "http://127.0.0.1:11434",
        mock_server_url: str = "http://localhost:8001",
        max_tool_retries: int = 2,
    ):
        """
        Initialize the travel agent.
        
        Args:
            model: LLM model name
            base_url: Ollama base URL
            mock_server_url: Mock server base URL
        """
        if not LANGCHAIN_AVAILABLE:
            raise ImportError("LangChain dependencies not available")

        self._check_llm_health(base_url)
        
        # Create HTTP tool wrapper (configures proxy)
        validation_rules = _load_validation_rules()
        self.http_wrapper = HTTPToolWrapper(base_url=mock_server_url, validation_rules=validation_rules)
        self.max_tool_retries = max_tool_retries
        self.llm_corrections = 0
        self.llm_correction_success = 0
        
        # Create HTTP-based tools
        self.tools = create_http_tools(self.http_wrapper)
        
        # Initialize LLM
        self.llm = ChatOllama(
            model=model,
            base_url=base_url,
            temperature=0.7,
        )
        
        # Bind tools to LLM (enables tool calling)
        self.llm = self.llm.bind_tools(self.tools)
        
        # Create prompt template with enhanced capabilities
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an advanced travel planning assistant that helps users with comprehensive travel arrangements.

You have access to multiple tools for flights, hotels, car rentals, and travel planning. All tools communicate via HTTP with external services.

CAPABILITIES:
1. ✈️ FLIGHT BOOKING - Search and book flights with budget optimization
2. 🏨 HOTEL RESERVATIONS - Find and book accommodations
3. 🚗 CAR RENTALS - Arrange transportation
4. 🌍 MULTI-CITY ITINERARIES - Plan complex travel routes
5. 💰 BUDGET OPTIMIZATION - Find best deals within user budget
6. 🎯 PREFERENCE MATCHING - Match user preferences (luxury, budget, business, leisure)

FLIGHT OPERATIONS:
- Use search_flights to find available flights
- IMPORTANT: Date parameter MUST be in YYYY-MM-DD format (e.g., "2025-12-25")
- Always use the exact year mentioned by the user, or the current/future year if not specified
- Never use past dates
- For multi-city trips, plan connections and layovers

HOTEL OPERATIONS:
- Use search_hotels to find accommodations
- Consider location, price, amenities, and user preferences
- Match hotel class to user budget (budget/luxury/business)

CAR RENTAL OPERATIONS:
- Use search_cars to find rental options
- Consider pickup/dropoff locations and dates
- Match vehicle type to group size and preferences

MULTI-CITY PLANNING:
- Break down complex itineraries into manageable segments
- Optimize for time, cost, and convenience
- Consider layover times, connection cities, and alternative routes

BUDGET OPTIMIZATION:
- Always check user budget constraints
- Compare multiple options to find best value
- Suggest alternatives if preferred options exceed budget
- Provide cost breakdowns for all recommendations

PREFERENCE MATCHING:
- Ask about travel purpose (business/leisure/family)
- Consider amenities preferences (pool, gym, breakfast, etc.)
- Match service level to user expectations
- Respect special requirements (accessibility, pet-friendly, etc.)

RESPONSE FORMAT:
- Present options clearly with prices and key details
- Explain your recommendations and why they fit user needs
- For complex itineraries, provide day-by-day breakdown
- Always confirm before making bookings
- Provide total cost summaries

Always use the tools to interact with external services. Never make up information."""),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

    def _is_input_error(self, text: str) -> bool:
        return any(code in text for code in ["Error 400", "Error 404", "Error 422"])

    def _repair_tool_args(self, tool_name: str, tool_args: Dict[str, Any], error_text: str) -> Optional[Dict[str, Any]]:
        """
        Ask the LLM to repair tool arguments based on error feedback.
        """
        prompt = (
            "You are repairing tool call arguments for a travel agent.\n"
            f"Tool: {tool_name}\n"
            f"Error: {error_text}\n"
            f"Current args: {json.dumps(tool_args, ensure_ascii=False)}\n"
            "Return ONLY a JSON object with corrected args. No extra text."
        )
        try:
            self.llm_corrections += 1
            response = self.llm.invoke(prompt)
            raw = response.content if hasattr(response, "content") else str(response)
            fixed = json.loads(raw)
            if isinstance(fixed, dict):
                return fixed
        except Exception:
            return None
        return None

    @staticmethod
    def _check_llm_health(base_url: str) -> None:
        """
        Fail fast if the local LLM server is not reachable.
        """
        if os.getenv("CHAOS_LLM_HEALTH_SKIP", "false").lower() == "true":
            return
        health_url = f"{base_url.rstrip('/')}/api/tags"
        try:
            # Bypass proxy env so LLM health check doesn't go through chaos proxy.
            with httpx.Client(timeout=3.0, trust_env=False, proxy=None) as client:
                response = client.get(health_url)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Local LLM health check failed ({response.status_code}). "
                    f"Please ensure Ollama is running at {base_url}."
                )
        except httpx.RequestError as e:
            raise RuntimeError(
                f"Local LLM is not reachable at {base_url}. "
                "Please start Ollama before running the agent."
            ) from e
    
    def process(self, user_input: str) -> str:
        """
        Process user input and generate response using HTTP-based tools.
        
        Args:
            user_input: User's request
            
        Returns:
            Agent's response
        """
        print(f"\n{'='*70}")
        print(f"User Request: {user_input}")
        print(f"{'='*70}\n")
        
        # Create agent chain
        chain = self.prompt | self.llm
        
        # Initial invocation
        messages = [HumanMessage(content=user_input)]
        max_iterations = 5
        iteration = 0
        
        while iteration < max_iterations:
            # Get LLM response (may include tool calls)
            response = chain.invoke({"input": user_input, "agent_scratchpad": messages})
            messages.append(response)
            
            # Check if LLM wants to call tools
            if hasattr(response, 'tool_calls') and response.tool_calls:
                print(f"[Agent] Generated {len(response.tool_calls)} tool call(s)")
                
                # Execute each tool call (via HTTP)
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    
                    print(f"\n[Agent] Calling tool: {tool_name}")
                    print(f"  Args: {json.dumps(tool_args, indent=2)}")
                    
                    # Find and execute the tool
                    tool = next((t for t in self.tools if t.name == tool_name), None)
                    if tool:
                        try:
                            attempt = 0
                            tool_result = None
                            current_args = tool_args
                            while attempt <= self.max_tool_retries:
                                # CRITICAL: Tool execution makes HTTP request
                                # This goes through proxy (localhost:8080)
                                tool_result = tool.invoke(current_args)
                                print(f"  Result: {str(tool_result)[:200]}...")
                                if isinstance(tool_result, str) and self._is_input_error(tool_result):
                                    if attempt >= self.max_tool_retries:
                                        break
                                    corrected = self._repair_tool_args(tool_name, current_args, tool_result)
                                    if not corrected:
                                        break
                                    current_args = corrected
                                    attempt += 1
                                    continue
                                break
                            if attempt > 0 and tool_result and not self._is_input_error(str(tool_result)):
                                self.llm_correction_success += 1

                            # Add tool result to messages
                            messages.append(AIMessage(
                                content=f"Tool {tool_name} returned: {tool_result}"
                            ))
                        except Exception as e:
                            error_msg = f"Error executing tool {tool_name}: {str(e)}"
                            print(f"  Error: {error_msg}")
                            messages.append(AIMessage(content=error_msg))
                    else:
                        error_msg = f"Tool {tool_name} not found"
                        print(f"  Error: {error_msg}")
                        messages.append(AIMessage(content=error_msg))
                
                iteration += 1
                continue
            else:
                # No more tool calls, return final response
                print(f"\n[Agent] Final response:")
                print(f"  {response.content}")
                print(f"\n{'='*70}\n")
                
                # Log successful completion
                import logging
                logger = logging.getLogger("travel_agent")
                from agent_chaos_sdk.common.file_logger import log_completion
                log_completion(logger, success=True)
                
                return response.content
        
        # Max iterations reached
        print(f"\n[Agent] Reached max iterations ({max_iterations})")
        
        # Log incomplete completion
        import logging
        logger = logging.getLogger("travel_agent")
        from agent_chaos_sdk.common.file_logger import log_completion
        log_completion(logger, success=False, reason="max_iterations")
        
        return messages[-1].content if messages else "Agent processing incomplete"
    
    def close(self):
        """Clean up resources."""
        self.http_wrapper.metrics["llm_corrections"] = self.llm_corrections
        self.http_wrapper.metrics["llm_correction_success"] = self.llm_correction_success
        self.http_wrapper.close()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Production-Like Travel Agent with HTTP-based Tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python examples/production_simulation/travel_agent.py \\
    --query "Book a flight from New York to Los Angeles on December 25th"
  
  # Custom model
  python examples/production_simulation/travel_agent.py \\
    --model llama3.1 \\
    --query "Search for flights from JFK to LAX"
        """
    )
    
    parser.add_argument(
        "--query",
        type=str,
        default="Book a flight from New York to Los Angeles on December 25th",
        help="User query for the travel agent"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="llama3.2",
        help="Ollama model name"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://127.0.0.1:11434",
        help="Ollama base URL"
    )
    parser.add_argument(
        "--mock-server-url",
        type=str,
        default="http://localhost:8001",
        help="Mock server URL"
    )
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Disable proxy (for testing without chaos proxy)"
    )
    
    args = parser.parse_args()
    
    # Disable proxy if requested
    if args.no_proxy:
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("HTTPS_PROXY", None)
        print("⚠️  Proxy disabled (--no-proxy flag)")
    else:
        proxy = os.environ.get("HTTP_PROXY", "http://localhost:8080")
        print(f"🌐 Proxy configured: {proxy}")
        print("   (All HTTP requests will go through chaos proxy)")
        print("   (Make sure chaos proxy is running: mitmdump -s agent_chaos_sdk/proxy/addon.py)\n")
    
    print(f"📡 Mock server: {args.mock_server_url}")
    print(f"🤖 LLM model: {args.model}\n")
    
    try:
        # Create agent
        agent = TravelAgent(
            model=args.model,
            base_url=args.base_url,
            mock_server_url=args.mock_server_url
        )
        
        # Process query
        response = agent.process(args.query)
        
        # Cleanup
        agent.close()
        
        print("✅ Agent processing complete!")
        print("\n📊 Check Jaeger (http://localhost:16686) for traces")
        print("📈 Check Grafana (http://localhost:3000) for metrics\n")
        if hasattr(agent, "http_wrapper"):
            metrics = agent.http_wrapper.metrics
            print("🔎 Tool Reliability Summary")
            print(f"  Tool Calls: {metrics.get('tool_calls', 0)}")
            print(f"  Tool Success: {metrics.get('tool_success', 0)}")
            print(f"  Tool Errors: {metrics.get('tool_errors', 0)}")
            print(f"  Validation Errors: {metrics.get('validation_errors', 0)}")
            print(f"  Validation Fixed: {metrics.get('validation_fixed', 0)}")
            print(f"  Retries: {metrics.get('retries', 0)}")
            print(f"  Retry Success: {metrics.get('retries_success', 0)}")
            print(f"  LLM Corrections: {metrics.get('llm_corrections', 0)}")
            print(f"  LLM Correction Success: {metrics.get('llm_correction_success', 0)}")
            print()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        # Log crash
        import logging
        logger = logging.getLogger("travel_agent")
        from agent_chaos_sdk.common.file_logger import log_completion
        log_completion(logger, success=False, reason="interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        # Log crash
        import logging
        logger = logging.getLogger("travel_agent")
        from agent_chaos_sdk.common.file_logger import log_completion, log_error
        log_error(logger, error_type="crash", message=str(e))
        log_completion(logger, success=False, reason="exception")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

