#!/usr/bin/env python3
"""
Multi-Agent Communication Layer

This module provides communication mechanisms between different travel agents:
- TravelCoordinator (main coordinator)
- HotelAgent (hotel bookings)
- CarRentalAgent (car rentals)
- FlightAgent (flight bookings)

Supports both direct method calls and HTTP-based communication for chaos testing.
"""

import json
import time
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from abc import ABC, abstractmethod

from agent_chaos_sdk.common.logger import get_logger

logger = get_logger(__name__)


class Message:
    """Message structure for inter-agent communication."""

    def __init__(
        self,
        sender: str,
        receiver: str,
        message_type: str,
        payload: Dict[str, Any],
        message_id: Optional[str] = None,
        timestamp: Optional[str] = None
    ):
        self.sender = sender
        self.receiver = receiver
        self.message_type = message_type
        self.payload = payload
        self.message_id = message_id or f"msg_{int(time.time() * 1000)}"
        self.timestamp = timestamp or datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sender": self.sender,
            "receiver": self.receiver,
            "message_type": self.message_type,
            "payload": self.payload,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        return cls(
            sender=data["sender"],
            receiver=data["receiver"],
            message_type=data["message_type"],
            payload=data["payload"],
            message_id=data.get("message_id"),
            timestamp=data.get("timestamp"),
        )


class AgentInterface(ABC):
    """Abstract interface for all travel agents."""

    def __init__(self, agent_id: str, agent_type: str):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.message_queue: List[Message] = []
        self.logger = get_logger(f"{agent_type}_{agent_id}")

    @abstractmethod
    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process a service request."""
        pass

    async def send_message(self, receiver: str, message_type: str, payload: Dict[str, Any]) -> None:
        """Send message to another agent."""
        message = Message(
            sender=self.agent_id,
            receiver=receiver,
            message_type=message_type,
            payload=payload
        )
        self.logger.info(f"Sending {message_type} to {receiver}")
        # In a real implementation, this would send via network/queue
        await self._deliver_message(message)

    async def receive_message(self, message: Message) -> None:
        """Receive message from another agent."""
        self.logger.info(f"Received {message.message_type} from {message.sender}")
        self.message_queue.append(message)
        await self._process_message(message)

    @abstractmethod
    async def _deliver_message(self, message: Message) -> None:
        """Deliver message to recipient (implementation specific)."""
        pass

    @abstractmethod
    async def _process_message(self, message: Message) -> None:
        """Process incoming message."""
        pass


class HTTPCommunicationLayer:
    """HTTP-based communication layer for chaos testing."""

    def __init__(self, base_url: str = "http://localhost:8002"):
        self.base_url = base_url.rstrip('/')
        self.agents: Dict[str, AgentInterface] = {}
        self.use_http_communication = True  # Enable HTTP-based communication

    def register_agent(self, agent: AgentInterface) -> None:
        """Register an agent with the communication layer."""
        self.agents[agent.agent_id] = agent

        # Register with communication server if using HTTP
        if self.use_http_communication:
            asyncio.create_task(self._register_with_server(agent))

        logger.info(f"Registered agent: {agent.agent_id} ({agent.agent_type})")

    async def _register_with_server(self, agent: AgentInterface) -> None:
        """Register agent with the communication server."""
        try:
            import httpx
            registration_data = {
                "agent_id": agent.agent_id,
                "agent_type": agent.agent_type,
                "capabilities": getattr(agent, 'capabilities', ["communication"])
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/agents/register",
                    json=registration_data
                )

                if response.status_code == 200:
                    logger.info(f"Agent {agent.agent_id} registered with communication server")
                else:
                    logger.warning(f"Failed to register agent {agent.agent_id} with server: {response.status_code}")

        except Exception as e:
            logger.error(f"Error registering agent {agent.agent_id} with server: {e}")

    async def send_message_http(self, message: Message) -> Dict[str, Any]:
        """Send message via HTTP (for chaos testing)."""
        try:
            import httpx
            url = f"{self.base_url}/agents/{message.receiver}/messages"
            payload = message.to_dict()

            # This goes through chaos proxy for testing
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"HTTP message delivery failed: {response.status_code}")
                    return {"status": "error", "error": f"HTTP {response.status_code}"}

        except Exception as e:
            logger.error(f"HTTP communication error: {e}")
            return {"status": "error", "error": str(e)}

    async def route_message(self, message: Message) -> bool:
        """Route message to appropriate agent."""
        if self.use_http_communication:
            # Use HTTP communication (goes through chaos proxy)
            result = await self.send_message_http(message)
            return result.get("status") == "delivered"
        else:
            # Use direct in-memory communication
            if message.receiver in self.agents:
                await self.agents[message.receiver].receive_message(message)
                return True
            else:
                logger.warning(f"No agent found for receiver: {message.receiver}")
                return False


# Global communication layer instance
communication_layer = HTTPCommunicationLayer()


class TravelCoordinatorAgent(AgentInterface):
    """Main coordinator agent that orchestrates travel planning."""

    def __init__(self, agent_id: str = "coordinator_001"):
        super().__init__(agent_id, "coordinator")
        self.itineraries: Dict[str, Dict[str, Any]] = {}
        self.capabilities = ["travel_planning", "coordination", "itinerary_management"]

    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process a complete travel planning request."""
        itinerary_id = f"itinerary_{int(time.time())}"

        self.logger.info(f"Processing travel request: {itinerary_id}")

        # Extract travel requirements
        origin = request.get("origin", "NYC")
        destination = request.get("destination", "LAX")
        departure_date = request.get("departure_date")
        return_date = request.get("return_date")
        travelers = request.get("travelers", 1)
        budget = request.get("budget")
        preferences = request.get("preferences", {})

        # Create itinerary
        itinerary = {
            "id": itinerary_id,
            "status": "planning",
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "return_date": return_date,
            "travelers": travelers,
            "budget": budget,
            "preferences": preferences,
            "components": {
                "flights": None,
                "hotels": None,
                "cars": None,
            },
            "total_cost": 0,
        }

        self.itineraries[itinerary_id] = itinerary

        try:
            # Coordinate with other agents
            results = await self._coordinate_booking(itinerary)
            itinerary.update(results)
            itinerary["status"] = "completed"

            return {
                "status": "success",
                "itinerary_id": itinerary_id,
                "itinerary": itinerary,
            }

        except Exception as e:
            itinerary["status"] = "failed"
            itinerary["error"] = str(e)
            return {
                "status": "error",
                "itinerary_id": itinerary_id,
                "error": str(e),
            }

    async def _coordinate_booking(self, itinerary: Dict[str, Any]) -> Dict[str, Any]:
        """Coordinate booking across different services."""
        results = {}

        # Book flights
        flight_request = {
            "origin": itinerary["origin"],
            "destination": itinerary["destination"],
            "date": itinerary["departure_date"],
            "passengers": itinerary["travelers"],
        }

        try:
            await self.send_message(
                "flight_agent_001",
                "book_flight",
                flight_request
            )
            # In real implementation, wait for response
            results["flights"] = {"status": "booked", "flight_id": "FL-TEST001"}
        except Exception as e:
            results["flights"] = {"status": "failed", "error": str(e)}

        # Book hotels
        hotel_request = {
            "city": itinerary["destination"],
            "checkin_date": itinerary["departure_date"],
            "checkout_date": itinerary["return_date"],
            "guests": itinerary["travelers"],
            "budget_max": itinerary.get("budget", {}).get("hotel_max"),
        }

        try:
            await self.send_message(
                "hotel_agent_001",
                "book_hotel",
                hotel_request
            )
            results["hotels"] = {"status": "booked", "hotel_id": "HT-TEST001"}
        except Exception as e:
            results["hotels"] = {"status": "failed", "error": str(e)}

        # Book cars if needed
        if itinerary.get("preferences", {}).get("needs_car", False):
            car_request = {
                "pickup_city": itinerary["destination"],
                "pickup_date": itinerary["departure_date"],
                "dropoff_date": itinerary["return_date"],
                "passengers": itinerary["travelers"],
            }

            try:
                await self.send_message(
                    "car_agent_001",
                    "book_car",
                    car_request
                )
                results["cars"] = {"status": "booked", "car_id": "CR-TEST001"}
            except Exception as e:
                results["cars"] = {"status": "failed", "error": str(e)}

        return results

    async def _deliver_message(self, message: Message) -> None:
        """Deliver message via communication layer."""
        await communication_layer.route_message(message)

    async def _process_message(self, message: Message) -> None:
        """Process incoming messages."""
        if message.message_type == "booking_confirmation":
            # Handle booking confirmations from other agents
            itinerary_id = message.payload.get("itinerary_id")
            if itinerary_id in self.itineraries:
                # Update itinerary with confirmation details
                pass
        elif message.message_type == "booking_failure":
            # Handle booking failures
            pass


class HotelAgent(AgentInterface):
    """Specialized agent for hotel bookings."""

    def __init__(self, agent_id: str = "hotel_agent_001"):
        super().__init__(agent_id, "hotel_agent")
        self.capabilities = ["hotel_search", "hotel_booking", "accommodation"]

    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process hotel booking request."""
        # Implementation would call hotel APIs
        return {
            "status": "success",
            "booking_id": f"HB-{int(time.time())}",
            "hotel_name": "Test Hotel",
            "confirmation_code": f"HCONF-{int(time.time())}",
        }

    async def _deliver_message(self, message: Message) -> None:
        await communication_layer.route_message(message)

    async def _process_message(self, message: Message) -> None:
        if message.message_type == "book_hotel":
            # Process hotel booking request
            result = await self.process_request(message.payload)
            # Send confirmation back
            await self.send_message(
                message.sender,
                "hotel_booked",
                {
                    "original_request": message.payload,
                    "booking_result": result,
                }
            )


class CarRentalAgent(AgentInterface):
    """Specialized agent for car rentals."""

    def __init__(self, agent_id: str = "car_agent_001"):
        super().__init__(agent_id, "car_agent")
        self.capabilities = ["car_rental", "vehicle_booking", "transportation"]

    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process car rental request."""
        # Implementation would call car rental APIs
        return {
            "status": "success",
            "booking_id": f"CB-{int(time.time())}",
            "car_model": "Test Car",
            "confirmation_code": f"CCONF-{int(time.time())}",
        }

    async def _deliver_message(self, message: Message) -> None:
        await communication_layer.route_message(message)

    async def _process_message(self, message: Message) -> None:
        if message.message_type == "book_car":
            # Process car booking request
            result = await self.process_request(message.payload)
            # Send confirmation back
            await self.send_message(
                message.sender,
                "car_booked",
                {
                    "original_request": message.payload,
                    "booking_result": result,
                }
            )


class FlightAgent(AgentInterface):
    """Specialized agent for flight bookings."""

    def __init__(self, agent_id: str = "flight_agent_001"):
        super().__init__(agent_id, "flight_agent")
        self.capabilities = ["flight_search", "flight_booking", "airfare"]

    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process flight booking request."""
        # Implementation would call flight APIs
        return {
            "status": "success",
            "booking_id": f"FB-{int(time.time())}",
            "flight_id": "FL-TEST001",
            "confirmation_code": f"FCONF-{int(time.time())}",
        }

    async def _deliver_message(self, message: Message) -> None:
        await communication_layer.route_message(message)

    async def _process_message(self, message: Message) -> None:
        if message.message_type == "book_flight":
            # Process flight booking request
            result = await self.process_request(message.payload)
            # Send confirmation back
            await self.send_message(
                message.sender,
                "flight_booked",
                {
                    "original_request": message.payload,
                    "booking_result": result,
                }
            )


def create_multi_agent_system() -> Dict[str, AgentInterface]:
    """Create and configure the complete multi-agent system."""
    # Create agents
    coordinator = TravelCoordinatorAgent()
    hotel_agent = HotelAgent()
    car_agent = CarRentalAgent()
    flight_agent = FlightAgent()

    # Register with communication layer
    communication_layer.register_agent(coordinator)
    communication_layer.register_agent(hotel_agent)
    communication_layer.register_agent(car_agent)
    communication_layer.register_agent(flight_agent)

    return {
        "coordinator": coordinator,
        "hotel_agent": hotel_agent,
        "car_agent": car_agent,
        "flight_agent": flight_agent,
    }