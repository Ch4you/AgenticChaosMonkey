#!/usr/bin/env python3
"""
Multi-Agent Travel Planning Demo

This script demonstrates the multi-agent architecture for travel planning
with chaos testing capabilities.

Usage:
    python multi_agent_demo.py --query "Plan a 3-day trip from NYC to LA next month"

Features:
- TravelCoordinator: Main coordination agent
- HotelAgent: Hotel booking specialist
- CarRentalAgent: Car rental specialist
- FlightAgent: Flight booking specialist
- Inter-agent communication via HTTP (chaos testable)
"""

import os
import sys
import json
import asyncio
import argparse
from datetime import datetime, timedelta

# Add project root to path
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# CRITICAL: Configure proxy for ALL HTTP requests (including inter-agent communication)
os.environ["HTTP_PROXY"] = "http://localhost:8080"
os.environ["HTTPS_PROXY"] = "http://localhost:8080"
os.environ["NO_PROXY"] = ""  # Ensure localhost goes through proxy

from examples.production_simulation.multi_agent.communication import (
    create_multi_agent_system,
    TravelCoordinatorAgent,
    communication_layer
)


class MultiAgentTravelPlanner:
    """Multi-agent travel planning system."""

    def __init__(self):
        self.agents = create_multi_agent_system()
        self.coordinator: TravelCoordinatorAgent = self.agents["coordinator"]

    async def plan_trip(self, query: str) -> Dict[str, any]:
        """Plan a complete trip using the multi-agent system."""
        print("🌍 Starting multi-agent travel planning...")
        print(f"📝 Query: {query}")
        print()

        # Parse the query to extract travel requirements
        travel_request = self._parse_travel_query(query)

        print("📋 Extracted travel requirements:")
        for key, value in travel_request.items():
            print(f"   {key}: {value}")
        print()

        # Process the request through the coordinator agent
        print("🤖 Coordinating with specialized agents...")
        result = await self.coordinator.process_request(travel_request)

        return result

    def _parse_travel_query(self, query: str) -> Dict[str, any]:
        """Parse natural language travel query into structured request."""
        # Simple parsing - in production, this would use NLP
        query_lower = query.lower()

        # Default values
        request = {
            "origin": "NYC",
            "destination": "LAX",
            "travelers": 1,
            "budget": {"total_max": 5000, "flight_max": 2000, "hotel_max": 300, "car_max": 100},
            "preferences": {
                "accommodation": "hotel",
                "needs_car": False,
                "class": "economy",
                "special_requirements": []
            }
        }

        # Extract destination
        destinations = ["los angeles", "la", "lax", "san francisco", "sf", "chicago", "miami", "miami beach"]
        for dest in destinations:
            if dest in query_lower:
                if dest in ["los angeles", "la", "lax"]:
                    request["destination"] = "LAX"
                elif dest in ["san francisco", "sf"]:
                    request["destination"] = "SFO"
                elif dest == "chicago":
                    request["destination"] = "ORD"
                elif dest in ["miami", "miami beach"]:
                    request["destination"] = "MIA"
                break

        # Extract duration
        import re
        duration_match = re.search(r'(\d+)\s*(day|night|week)', query_lower)
        if duration_match:
            days = int(duration_match.group(1))
            if duration_match.group(2) in ['week']:
                days *= 7
            request["duration_days"] = days

        # Extract travelers
        traveler_match = re.search(r'(\d+)\s*(person|people|traveler)', query_lower)
        if traveler_match:
            request["travelers"] = int(traveler_match.group(1))

        # Check for car rental
        if any(word in query_lower for word in ['car', 'rental', 'rent', 'drive']):
            request["preferences"]["needs_car"] = True

        # Set dates (next month)
        today = datetime.now()
        next_month = today.replace(day=1) + timedelta(days=32)
        departure = next_month.replace(day=15)  # 15th of next month
        request["departure_date"] = departure.strftime("%Y-%m-%d")

        if "duration_days" in request:
            return_date = departure + timedelta(days=request["duration_days"])
            request["return_date"] = return_date.strftime("%Y-%m-%d")

        return request


async def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Travel Planning Demo")
    parser.add_argument(
        "--query",
        type=str,
        default="Plan a 3-day business trip from New York to Los Angeles next month with car rental",
        help="Travel planning query"
    )
    parser.add_argument(
        "--chaos-test",
        action="store_true",
        help="Enable chaos testing mode (ensure proxy is running)"
    )

    args = parser.parse_args()

    print("🐵 Multi-Agent Travel Planning Demo")
    print("=" * 50)

    if args.chaos_test:
        print("🔥 Chaos testing mode enabled!")
        print("   Make sure chaos proxy is running on localhost:8080")
        print("   Inter-agent communication will go through chaos proxy")
        print()

    try:
        # Create multi-agent system
        planner = MultiAgentTravelPlanner()

        # Plan the trip
        result = await planner.plan_trip(args.query)

        print("\n📊 Travel Planning Result:")
        print("=" * 30)

        if result["status"] == "success":
            itinerary = result["itinerary"]
            print(f"✅ Trip planned successfully!")
            print(f"📋 Itinerary ID: {result['itinerary_id']}")
            print(f"📍 Route: {itinerary['origin']} → {itinerary['destination']}")
            print(f"📅 Dates: {itinerary['departure_date']} to {itinerary.get('return_date', 'N/A')}")
            print(f"👥 Travelers: {itinerary['travelers']}")
            print(f"💰 Budget: ${itinerary.get('budget', {}).get('total_max', 'N/A')}")

            print("\n🏨 Booking Status:")
            components = itinerary.get("components", {})
            for service, booking in components.items():
                if booking:
                    status = booking.get("status", "unknown")
                    booking_id = booking.get("booking_id", "N/A") if "booking_id" in booking else booking.get(f"{service[:-1]}_id", "N/A")
                    print(f"   {service.title()}: {status} (ID: {booking_id})")
                else:
                    print(f"   {service.title()}: Not booked")

            print(f"\n💵 Total Estimated Cost: ${itinerary.get('total_cost', 0)}")

        else:
            print(f"❌ Planning failed: {result.get('error', 'Unknown error')}")

        print("\n🎯 Chaos Testing Notes:")
        print("   - Agent communication goes through proxy (chaos testable)")
        print("   - Each agent specializes in different travel services")
        print("   - Coordinator orchestrates the entire booking process")
        print("   - Failures in one agent don't break the entire system")

    except KeyboardInterrupt:
        print("\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())