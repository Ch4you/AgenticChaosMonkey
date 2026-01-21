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
    python -m agent_chaos_sdk.tools.mock_server

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
    version="1.0.0",
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

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        """Validate date format."""
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")

    @field_validator("origin", "destination")
    @classmethod
    def validate_airport_code(cls, v: str) -> str:
        """Validate airport code format."""
        if not re.match(r"^[A-Z]{3}$", v.upper()):
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


class HotelSearchRequest(BaseModel):
    """Request model for hotel search."""

    city: str = Field(..., description="City name")
    checkin_date: str = Field(..., description="Check-in date in YYYY-MM-DD format")
    checkout_date: str = Field(..., description="Check-out date in YYYY-MM-DD format")
    guests: int = Field(default=1, ge=1, le=10, description="Number of guests")
    budget_max: Optional[float] = Field(default=None, gt=0, description="Maximum budget per night")

    @field_validator("checkin_date", "checkout_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")


class Hotel(BaseModel):
    """Hotel model."""

    hotel_id: str
    name: str
    city: str
    stars: int
    price_per_night: float
    amenities: List[str]
    rating: float


class HotelSearchResponse(BaseModel):
    """Response model for hotel search."""

    hotels: List[Hotel]
    total_results: int
    search_params: Dict[str, any]


class BookHotelRequest(BaseModel):
    """Request model for hotel booking."""

    hotel_id: str = Field(..., description="Hotel ID to book")
    checkin_date: str = Field(..., description="Check-in date in YYYY-MM-DD format")
    checkout_date: str = Field(..., description="Check-out date in YYYY-MM-DD format")
    guests: int = Field(default=1, ge=1, le=10, description="Number of guests")


class BookHotelResponse(BaseModel):
    """Response model for hotel booking."""

    booking_id: str
    hotel_id: str
    hotel_name: str
    status: str
    confirmation_code: str
    total_price: float
    checkin_date: str
    checkout_date: str
    guests: int
    message: str


class CarSearchRequest(BaseModel):
    """Request model for car rental search."""

    pickup_city: str = Field(..., description="City for car pickup")
    pickup_date: str = Field(..., description="Pickup date in YYYY-MM-DD format")
    dropoff_date: str = Field(..., description="Dropoff date in YYYY-MM-DD format")
    passengers: int = Field(default=1, ge=1, le=9, description="Number of passengers")

    @field_validator("pickup_date", "dropoff_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")


class Car(BaseModel):
    """Car rental model."""

    car_id: str
    model: str
    category: str  # economy, compact, standard, luxury
    seats: int
    transmission: str  # automatic, manual
    price_per_day: float
    features: List[str]


class CarSearchResponse(BaseModel):
    """Response model for car rental search."""

    cars: List[Car]
    total_results: int
    search_params: Dict[str, any]


class BookCarRequest(BaseModel):
    """Request model for car booking."""

    car_id: str = Field(..., description="Car ID to book")
    pickup_date: str = Field(..., description="Pickup date in YYYY-MM-DD format")
    dropoff_date: str = Field(..., description="Dropoff date in YYYY-MM-DD format")


class BookCarResponse(BaseModel):
    """Response model for car booking."""

    booking_id: str
    car_id: str
    car_model: str
    status: str
    confirmation_code: str
    total_price: float
    pickup_date: str
    dropoff_date: str
    message: str


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
_hotel_bookings: Dict[str, Dict] = {}
_car_bookings: Dict[str, Dict] = {}


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

    for _ in range(num_flights):
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
            available_seats=available_seats,
        )

        flights.append(flight)
        _flights_db[flight_id] = flight

    return flights


def generate_mock_hotels(city: str, budget_max: Optional[float] = None) -> List[Hotel]:
    """
    Generate mock hotel data.

    Args:
        city: City name
        budget_max: Maximum budget per night (optional)

    Returns:
        List of mock Hotel objects
    """
    hotel_names = [
        "Grand Plaza Hotel", "City Center Inn", "Riverside Resort", "Mountain View Lodge",
        "Downtown Suites", "Airport Express", "Business Traveler Hotel", "Luxury Palace",
        "Budget Stay Inn", "Executive Suites"
    ]

    amenities_options = [
        ["WiFi", "Pool", "Gym", "Breakfast"],
        ["WiFi", "Parking", "Restaurant", "Bar"],
        ["WiFi", "Spa", "Room Service", "Concierge"],
        ["WiFi", "Laundry", "Business Center", "Airport Shuttle"],
        ["WiFi", "Pool", "Kids Club", "Restaurant"]
    ]

    hotels = []
    num_hotels = random.randint(4, 8)

    for _ in range(num_hotels):
        hotel_id = f"HT-{uuid4().hex[:8].upper()}"
        name = random.choice(hotel_names)
        stars = random.randint(2, 5)
        base_price = stars * 50 + random.randint(20, 100)  # 2-star: ~$120-200, 5-star: ~$270-400

        # Apply budget filter
        if budget_max and base_price > budget_max:
            continue

        rating = round(random.uniform(3.5, 5.0), 1)
        amenities = random.choice(amenities_options)

        hotel = Hotel(
            hotel_id=hotel_id,
            name=name,
            city=city,
            stars=stars,
            price_per_night=float(base_price),
            amenities=amenities,
            rating=rating
        )

        hotels.append(hotel)

    return hotels


def generate_mock_cars(city: str) -> List[Car]:
    """
    Generate mock car rental data.

    Args:
        city: City for car pickup

    Returns:
        List of mock Car objects
    """
    car_models = [
        ("Toyota Corolla", "compact"),
        ("Honda Civic", "compact"),
        ("Ford Focus", "compact"),
        ("Chevrolet Cruze", "compact"),
        ("Toyota Camry", "standard"),
        ("Honda Accord", "standard"),
        ("Ford Taurus", "standard"),
        ("Chevrolet Malibu", "standard"),
        ("BMW 3 Series", "luxury"),
        ("Mercedes C-Class", "luxury"),
        ("Audi A4", "luxury"),
        ("Tesla Model 3", "luxury")
    ]

    features_options = [
        ["GPS", "Bluetooth", "USB Charging"],
        ["GPS", "Backup Camera", "Apple CarPlay"],
        ["GPS", "Heated Seats", "Sunroof"],
        ["GPS", "Leather Seats", "Premium Audio"],
        ["GPS", "Autopilot", "Supercharger Access"]
    ]

    cars = []
    num_cars = random.randint(5, 10)

    for _ in range(num_cars):
        car_id = f"CR-{uuid4().hex[:8].upper()}"
        model, category = random.choice(car_models)

        # Seats based on category
        if category == "compact":
            seats = random.randint(4, 5)
        elif category == "standard":
            seats = random.randint(5, 6)
        else:  # luxury
            seats = random.randint(4, 5)

        transmission = random.choice(["automatic", "automatic"])  # Most cars are automatic

        # Price based on category
        if category == "compact":
            price = random.randint(25, 45)
        elif category == "standard":
            price = random.randint(40, 70)
        else:  # luxury
            price = random.randint(80, 150)

        features = random.choice(features_options)

        car = Car(
            car_id=car_id,
            model=model,
            category=category,
            seats=seats,
            transmission=transmission,
            price_per_day=float(price),
            features=features
        )

        cars.append(car)

    return cars


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
            "search_hotels": "POST /search_hotels",
            "book_hotel": "POST /book_hotel",
            "search_cars": "POST /search_cars",
            "book_car": "POST /book_car",
            "health": "GET /health",
        },
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
                status_code=400, detail="Cannot search for flights in the past"
            )
    except ValueError:
        # This shouldn't happen due to Pydantic validation, but handle it anyway
        raise HTTPException(
            status_code=400, detail="Invalid date format. Use YYYY-MM-DD"
        )

    # Generate mock flights
    flights = generate_mock_flights(request.origin, request.destination, request.date)

    return FlightSearchResponse(
        flights=flights,
        total_results=len(flights),
        search_params={
            "origin": request.origin,
            "destination": request.destination,
            "date": request.date,
        },
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
            status_code=404, detail=f"Flight {request.flight_id} not found"
        )

    flight = _flights_db[request.flight_id]

    # Check if already booked (simple check - in real API, this would be more complex)
    if request.flight_id in _bookings:
        raise HTTPException(
            status_code=409, detail=f"Flight {request.flight_id} is already booked"
        )

    # Check available seats
    if flight.available_seats <= 0:
        raise HTTPException(status_code=400, detail="No seats available for this flight")

    # Create booking
    booking_id = f"BK-{uuid4().hex[:8].upper()}"
    confirmation_code = f"CONF-{random.randint(100000, 999999)}"

    booking = {
        "booking_id": booking_id,
        "flight_id": request.flight_id,
        "confirmation_code": confirmation_code,
        "status": "confirmed",
        "created_at": datetime.now().isoformat(),
    }

    _bookings[request.flight_id] = booking

    # Decrease available seats
    flight.available_seats -= 1

    return BookTicketResponse(
        booking_id=booking_id,
        flight_id=request.flight_id,
        status="confirmed",
        confirmation_code=confirmation_code,
        message=(
            f"Successfully booked flight {request.flight_id}. "
            f"Confirmation: {confirmation_code}"
        ),
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

    raise HTTPException(status_code=404, detail=f"Booking {booking_id} not found")


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
            status_code=404, detail=f"Flight {flight_id} not found"
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
                "message": f"Booking {booking_id} has been cancelled",
            }

    raise HTTPException(status_code=404, detail=f"Booking {booking_id} not found")


@app.post("/search_hotels", response_model=HotelSearchResponse)
async def search_hotels(request: HotelSearchRequest):
    """
    Search for hotels in a city.

    Args:
        request: Hotel search request

    Returns:
        HotelSearchResponse with available hotels
    """
    # Simulate processing delay
    await simulate_processing_delay()

    # Generate mock hotels
    hotels = generate_mock_hotels(request.city, request.budget_max)

    return HotelSearchResponse(
        hotels=hotels,
        total_results=len(hotels),
        search_params={
            "city": request.city,
            "checkin_date": request.checkin_date,
            "checkout_date": request.checkout_date,
            "guests": request.guests,
            "budget_max": request.budget_max,
        },
    )


@app.post("/book_hotel", response_model=BookHotelResponse)
async def book_hotel(request: BookHotelRequest):
    """
    Book a hotel room.

    Args:
        request: Hotel booking request

    Returns:
        BookHotelResponse with booking confirmation
    """
    # Simulate processing delay
    await simulate_processing_delay()

    # For demo purposes, we'll create a mock hotel if it doesn't exist
    hotel_name = f"Hotel in {request.checkin_date.split('-')[0]}"  # Simple mock

    # Calculate total price (mock)
    nights = (datetime.strptime(request.checkout_date, "%Y-%m-%d") -
              datetime.strptime(request.checkin_date, "%Y-%m-%d")).days
    price_per_night = random.randint(100, 300)
    total_price = price_per_night * nights

    # Create booking
    booking_id = f"HB-{uuid4().hex[:8].upper()}"
    confirmation_code = f"HCONF-{random.randint(100000, 999999)}"

    booking = {
        "booking_id": booking_id,
        "hotel_id": request.hotel_id,
        "confirmation_code": confirmation_code,
        "status": "confirmed",
        "total_price": total_price,
        "checkin_date": request.checkin_date,
        "checkout_date": request.checkout_date,
        "guests": request.guests,
        "created_at": datetime.now().isoformat(),
    }

    _hotel_bookings[request.hotel_id] = booking

    return BookHotelResponse(
        booking_id=booking_id,
        hotel_id=request.hotel_id,
        hotel_name=hotel_name,
        status="confirmed",
        confirmation_code=confirmation_code,
        total_price=float(total_price),
        checkin_date=request.checkin_date,
        checkout_date=request.checkout_date,
        guests=request.guests,
        message=f"Hotel booking confirmed. Total: ${total_price}",
    )


@app.post("/search_cars", response_model=CarSearchResponse)
async def search_cars(request: CarSearchRequest):
    """
    Search for rental cars.

    Args:
        request: Car rental search request

    Returns:
        CarSearchResponse with available cars
    """
    # Simulate processing delay
    await simulate_processing_delay()

    # Generate mock cars
    cars = generate_mock_cars(request.pickup_city)

    return CarSearchResponse(
        cars=cars,
        total_results=len(cars),
        search_params={
            "pickup_city": request.pickup_city,
            "pickup_date": request.pickup_date,
            "dropoff_date": request.dropoff_date,
            "passengers": request.passengers,
        },
    )


@app.post("/book_car", response_model=BookCarResponse)
async def book_car(request: BookCarRequest):
    """
    Book a rental car.

    Args:
        request: Car booking request

    Returns:
        BookCarResponse with booking confirmation
    """
    # Simulate processing delay
    await simulate_processing_delay()

    # For demo purposes, we'll create a mock car if it doesn't exist
    car_model = f"Car Model {request.pickup_date.split('-')[0]}"  # Simple mock

    # Calculate total price (mock)
    days = (datetime.strptime(request.dropoff_date, "%Y-%m-%d") -
            datetime.strptime(request.pickup_date, "%Y-%m-%d")).days
    price_per_day = random.randint(40, 100)
    total_price = price_per_day * days

    # Create booking
    booking_id = f"CB-{uuid4().hex[:8].upper()}"
    confirmation_code = f"CCONF-{random.randint(100000, 999999)}"

    booking = {
        "booking_id": booking_id,
        "car_id": request.car_id,
        "confirmation_code": confirmation_code,
        "status": "confirmed",
        "total_price": total_price,
        "pickup_date": request.pickup_date,
        "dropoff_date": request.dropoff_date,
        "created_at": datetime.now().isoformat(),
    }

    _car_bookings[request.car_id] = booking

    return BookCarResponse(
        booking_id=booking_id,
        car_id=request.car_id,
        car_model=car_model,
        status="confirmed",
        confirmation_code=confirmation_code,
        total_price=float(total_price),
        pickup_date=request.pickup_date,
        dropoff_date=request.dropoff_date,
        message=f"Car booking confirmed. Total: ${total_price}",
    )


if __name__ == "__main__":
    import uvicorn

    print("=" * 70)
    print("Mock External Services API")
    print("=" * 70)
    print("Server starting on http://localhost:8001")
    print("API Documentation: http://localhost:8001/docs")
    print("Health Check: http://localhost:8001/health")
    print("=" * 70)
    print()

    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
