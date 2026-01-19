#!/usr/bin/env python3
"""
Mock Server - Simulates External World / Upstream Services

This FastAPI server simulates external APIs that agents rely on, such as:
- Flight search APIs
- Booking services
- Other upstream services

It includes realistic features like:
- Request validation
- Random processing delays (simulating real API latency)
- Error responses for invalid inputs
- Structured JSON responses

Usage:
    python src/tools/mock_server.py

The server runs on http://localhost:8001
"""

import asyncio
import random
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

app = FastAPI(
    title="Mock External Services API",
    description="Simulates external APIs for agent testing",
    version="1.0.0"
)

# Enable CORS for all origins (useful for testing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models
class FlightSearchRequest(BaseModel):
    """Request model for flight search."""
    origin: str = Field(..., description="Origin airport code (e.g., 'JFK', 'LAX')")
    destination: str = Field(..., description="Destination airport code")
    date: str = Field(..., description="Flight date in YYYY-MM-DD format")
    
    @field_validator('date')
    @classmethod
    def validate_date(cls, v: str) -> str:
        """Validate date format."""
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
    
    @field_validator('origin', 'destination')
    @classmethod
    def validate_airport_code(cls, v: str) -> str:
        """Validate airport code format."""
        if not re.match(r'^[A-Z]{3}$', v.upper()):
            raise ValueError("Airport code must be 3 uppercase letters")
        return v.upper()


class Flight(BaseModel):
    """Flight model."""
    flight_id: str
    airline: str
    origin: str
    destination: str
    departure_time: str
    arrival_time: str
    price: float
    available_seats: int


class FlightSearchResponse(BaseModel):
    """Response model for flight search."""
    flights: List[Flight]
    total_results: int
    search_params: Dict[str, str]


class BookTicketRequest(BaseModel):
    """Request model for ticket booking."""
    flight_id: str = Field(..., description="Flight ID to book")


class BookTicketResponse(BaseModel):
    """Response model for ticket booking."""
    booking_id: str
    flight_id: str
    status: str
    confirmation_code: str
    message: str


# Mock Data Storage
_bookings: Dict[str, Dict] = {}
_flights_db: Dict[str, Flight] = {}


def generate_mock_flights(origin: str, destination: str, date: str) -> List[Flight]:
    """
    Generate mock flight data.
    
    Args:
        origin: Origin airport code
        destination: Destination airport code
        date: Flight date
        
    Returns:
        List of mock Flight objects
    """
    airlines = ["Delta", "United", "American", "Southwest", "JetBlue"]
    flights = []
    
    # Generate 3-5 random flights
    num_flights = random.randint(3, 5)
    
    for i in range(num_flights):
        flight_id = f"FL-{uuid4().hex[:8].upper()}"
        airline = random.choice(airlines)
        
        # Generate departure times (morning to evening)
        hour = random.randint(6, 22)
        minute = random.choice([0, 15, 30, 45])
        departure_time = f"{date}T{hour:02d}:{minute:02d}:00"
        
        # Arrival is 2-6 hours later
        flight_duration = random.randint(2, 6)
        arrival_hour = (hour + flight_duration) % 24
        arrival_time = f"{date}T{arrival_hour:02d}:{minute:02d}:00"
        
        # Price between $200-$800
        price = round(random.uniform(200, 800), 2)
        
        # Available seats
        available_seats = random.randint(5, 50)
        
        flight = Flight(
            flight_id=flight_id,
            airline=airline,
            origin=origin,
            destination=destination,
            departure_time=departure_time,
            arrival_time=arrival_time,
            price=price,
            available_seats=available_seats
        )
        
        flights.append(flight)
        _flights_db[flight_id] = flight
    
    return flights


async def simulate_processing_delay(min_delay: float = 0.1, max_delay: float = 0.5):
    """
    Simulate real API processing delay.
    
    Args:
        min_delay: Minimum delay in seconds
        max_delay: Maximum delay in seconds
    """
    delay = random.uniform(min_delay, max_delay)
    await asyncio.sleep(delay)


@app.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "service": "Mock External Services API",
        "version": "1.0.0",
        "endpoints": {
            "search_flights": "POST /search_flights",
            "book_ticket": "POST /book_ticket",
            "health": "GET /health"
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "mock_server"}


@app.post("/search_flights", response_model=FlightSearchResponse)
async def search_flights(request: FlightSearchRequest):
    """
    Search for flights between origin and destination.
    
    This endpoint simulates a flight search API. It validates the request,
    adds a random processing delay, and returns mock flight data.
    
    Args:
        request: Flight search request with origin, destination, and date
        
    Returns:
        FlightSearchResponse with list of available flights
        
    Raises:
        HTTPException: 400 if validation fails
    """
    # Simulate processing delay (real API latency)
    await simulate_processing_delay()
    
    # Validate date is not in the past
    try:
        flight_date = datetime.strptime(request.date, "%Y-%m-%d")
        if flight_date.date() < datetime.now().date():
            raise HTTPException(
                status_code=400,
                detail="Cannot search for flights in the past"
            )
    except ValueError:
        # This shouldn't happen due to Pydantic validation, but handle it anyway
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD"
        )
    
    # Generate mock flights
    flights = generate_mock_flights(request.origin, request.destination, request.date)
    
    return FlightSearchResponse(
        flights=flights,
        total_results=len(flights),
        search_params={
            "origin": request.origin,
            "destination": request.destination,
            "date": request.date
        }
    )


@app.post("/book_ticket", response_model=BookTicketResponse)
async def book_ticket(request: BookTicketRequest):
    """
    Book a flight ticket.
    
    This endpoint simulates a booking API. It validates the flight ID,
    adds a random processing delay, and returns booking confirmation.
    
    Args:
        request: Booking request with flight_id
        
    Returns:
        BookTicketResponse with booking confirmation
        
    Raises:
        HTTPException: 400 if flight not found, 409 if already booked
    """
    # Simulate processing delay (real API latency)
    await simulate_processing_delay()
    
    # Check if flight exists
    if request.flight_id not in _flights_db:
        raise HTTPException(
            status_code=404,
            detail=f"Flight {request.flight_id} not found"
        )
    
    flight = _flights_db[request.flight_id]
    
    # Check if already booked (simple check - in real API, this would be more complex)
    if request.flight_id in _bookings:
        raise HTTPException(
            status_code=409,
            detail=f"Flight {request.flight_id} is already booked"
        )
    
    # Check available seats
    if flight.available_seats <= 0:
        raise HTTPException(
            status_code=400,
            detail="No seats available for this flight"
        )
    
    # Create booking
    booking_id = f"BK-{uuid4().hex[:8].upper()}"
    confirmation_code = f"CONF-{random.randint(100000, 999999)}"
    
    booking = {
        "booking_id": booking_id,
        "flight_id": request.flight_id,
        "confirmation_code": confirmation_code,
        "status": "confirmed",
        "created_at": datetime.now().isoformat()
    }
    
    _bookings[request.flight_id] = booking
    
    # Decrease available seats
    flight.available_seats -= 1
    
    return BookTicketResponse(
        booking_id=booking_id,
        flight_id=request.flight_id,
        status="confirmed",
        confirmation_code=confirmation_code,
        message=f"Successfully booked flight {request.flight_id}. Confirmation: {confirmation_code}"
    )


@app.get("/bookings/{booking_id}")
async def get_booking(booking_id: str):
    """
    Get booking information by booking ID.
    
    Args:
        booking_id: Booking ID to look up
        
    Returns:
        Booking information
        
    Raises:
        HTTPException: 404 if booking not found
    """
    # Find booking by ID
    for flight_id, booking in _bookings.items():
        if booking["booking_id"] == booking_id:
            return booking
    
    raise HTTPException(
        status_code=404,
        detail=f"Booking {booking_id} not found"
    )


@app.get("/flights/{flight_id}")
async def get_flight(flight_id: str):
    """
    Get flight information by flight ID.
    
    Args:
        flight_id: Flight ID to look up
        
    Returns:
        Flight information
        
    Raises:
        HTTPException: 404 if flight not found
    """
    if flight_id not in _flights_db:
        raise HTTPException(
            status_code=404,
            detail=f"Flight {flight_id} not found"
        )
    
    return _flights_db[flight_id]


@app.delete("/bookings/{booking_id}")
async def cancel_booking(booking_id: str):
    """
    Cancel a booking.
    
    Args:
        booking_id: Booking ID to cancel
        
    Returns:
        Cancellation confirmation
        
    Raises:
        HTTPException: 404 if booking not found
    """
    # Find and remove booking
    for flight_id, booking in list(_bookings.items()):
        if booking["booking_id"] == booking_id:
            del _bookings[flight_id]
            # Restore seat
            if flight_id in _flights_db:
                _flights_db[flight_id].available_seats += 1
            return {
                "status": "cancelled",
                "booking_id": booking_id,
                "message": f"Booking {booking_id} has been cancelled"
            }
    
    raise HTTPException(
        status_code=404,
        detail=f"Booking {booking_id} not found"
    )


if __name__ == "__main__":
    import uvicorn
    
    print("=" * 70)
    print("Mock External Services API")
    print("=" * 70)
    print(f"Server starting on http://localhost:8001")
    print(f"API Documentation: http://localhost:8001/docs")
    print(f"Health Check: http://localhost:8001/health")
    print("=" * 70)
    print()
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )

