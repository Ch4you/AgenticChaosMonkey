#!/usr/bin/env python3
"""
Multi-Agent Communication Server

This FastAPI server handles inter-agent communication for chaos testing.
All messages between agents go through this server, which can be targeted
by chaos strategies to test agent-to-agent communication reliability.

Usage:
    python communication_server.py

The server runs on http://localhost:8002
"""

import asyncio
import time
from typing import Dict, List, Any, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent_chaos_sdk.common.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="Multi-Agent Communication Server",
    description="Handles inter-agent communication for chaos testing",
    version="1.0.0",
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Data Models
class MessagePayload(BaseModel):
    sender: str
    receiver: str
    message_type: str
    payload: Dict[str, Any]
    message_id: Optional[str] = None
    timestamp: Optional[str] = None


class AgentRegistration(BaseModel):
    agent_id: str
    agent_type: str
    capabilities: List[str]


# In-memory storage (in production, use database)
registered_agents: Dict[str, Dict[str, Any]] = {}
message_queue: Dict[str, List[Dict[str, Any]]] = {}
message_history: List[Dict[str, Any]] = []


@app.get("/")
async def root():
    """API information."""
    return {
        "service": "Multi-Agent Communication Server",
        "version": "1.0.0",
        "endpoints": {
            "register_agent": "POST /agents/register",
            "send_message": "POST /agents/{agent_id}/messages",
            "get_messages": "GET /agents/{agent_id}/messages",
            "health": "GET /health",
        },
        "registered_agents": list(registered_agents.keys()),
    }


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "healthy",
        "registered_agents": len(registered_agents),
        "pending_messages": sum(len(queue) for queue in message_queue.values()),
    }


@app.post("/agents/register")
async def register_agent(registration: AgentRegistration):
    """Register an agent with the communication server."""
    agent_id = registration.agent_id

    if agent_id in registered_agents:
        raise HTTPException(status_code=409, detail=f"Agent {agent_id} already registered")

    registered_agents[agent_id] = {
        "agent_type": registration.agent_type,
        "capabilities": registration.capabilities,
        "registered_at": datetime.now().isoformat(),
        "status": "active",
    }

    message_queue[agent_id] = []

    logger.info(f"Registered agent: {agent_id} ({registration.agent_type})")
    return {
        "status": "registered",
        "agent_id": agent_id,
        "message": f"Agent {agent_id} registered successfully",
    }


@app.post("/agents/{agent_id}/messages")
async def send_message(agent_id: str, message: MessagePayload):
    """Send a message to an agent."""
    if agent_id not in registered_agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not registered")

    # Validate sender is registered (optional)
    if message.sender not in registered_agents:
        logger.warning(f"Sender {message.sender} not registered, but allowing message")

    # Create message record
    message_record = {
        "message_id": message.message_id or f"msg_{int(time.time() * 1000)}",
        "sender": message.sender,
        "receiver": message.receiver,
        "message_type": message.message_type,
        "payload": message.payload,
        "timestamp": message.timestamp or datetime.now().isoformat(),
        "delivered_at": datetime.now().isoformat(),
        "status": "delivered",
    }

    # Add to receiver's queue
    if message.receiver not in message_queue:
        message_queue[message.receiver] = []

    message_queue[message.receiver].append(message_record)
    message_history.append(message_record)

    # Simulate processing delay (for chaos testing)
    await asyncio.sleep(0.01)

    logger.info(f"Message delivered: {message.sender} -> {message.receiver} ({message.message_type})")

    return {
        "status": "delivered",
        "message_id": message_record["message_id"],
        "delivered_to": message.receiver,
    }


@app.get("/agents/{agent_id}/messages")
async def get_messages(agent_id: str):
    """Get pending messages for an agent."""
    if agent_id not in registered_agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not registered")

    messages = message_queue.get(agent_id, [])
    message_queue[agent_id] = []  # Clear queue after retrieval

    return {
        "agent_id": agent_id,
        "messages": messages,
        "count": len(messages),
    }


@app.get("/agents/{agent_id}/status")
async def get_agent_status(agent_id: str):
    """Get agent status and information."""
    if agent_id not in registered_agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not registered")

    agent_info = registered_agents[agent_id].copy()
    agent_info["pending_messages"] = len(message_queue.get(agent_id, []))

    return agent_info


@app.get("/messages/history")
async def get_message_history(limit: int = 50, agent_id: Optional[str] = None):
    """Get message history (for debugging and monitoring)."""
    history = message_history

    if agent_id:
        history = [msg for msg in history if msg["sender"] == agent_id or msg["receiver"] == agent_id]

    return {
        "messages": history[-limit:],
        "total_count": len(history),
        "returned_count": min(limit, len(history)),
    }


@app.delete("/agents/{agent_id}")
async def unregister_agent(agent_id: str):
    """Unregister an agent."""
    if agent_id not in registered_agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not registered")

    # Clean up
    if agent_id in message_queue:
        del message_queue[agent_id]
    del registered_agents[agent_id]

    logger.info(f"Unregistered agent: {agent_id}")
    return {
        "status": "unregistered",
        "agent_id": agent_id,
    }


@app.get("/stats")
async def get_stats():
    """Get communication server statistics."""
    total_messages = len(message_history)
    agent_count = len(registered_agents)
    pending_messages = sum(len(queue) for queue in message_queue.values())

    # Calculate message types distribution
    message_types = {}
    for msg in message_history[-1000:]:  # Last 1000 messages
        msg_type = msg["message_type"]
        message_types[msg_type] = message_types.get(msg_type, 0) + 1

    return {
        "total_agents": agent_count,
        "total_messages": total_messages,
        "pending_messages": pending_messages,
        "message_types": message_types,
        "registered_agents": list(registered_agents.keys()),
    }


# Cleanup task to remove old messages
@app.on_event("startup")
async def startup_event():
    """Initialize the server."""
    logger.info("Multi-Agent Communication Server starting...")

    # Periodic cleanup of old messages (keep last 24 hours)
    async def cleanup_old_messages():
        while True:
            await asyncio.sleep(3600)  # Run every hour
            cutoff_time = time.time() - (24 * 3600)  # 24 hours ago

            # Clean up message history
            global message_history
            message_history = [
                msg for msg in message_history
                if datetime.fromisoformat(msg["timestamp"]).timestamp() > cutoff_time
            ]

            logger.info(f"Cleaned up old messages. Current history size: {len(message_history)}")

    # Start cleanup task
    asyncio.create_task(cleanup_old_messages())


if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Multi-Agent Communication Server on http://localhost:8002")
    uvicorn.run(app, host="127.0.0.1", port=8002)