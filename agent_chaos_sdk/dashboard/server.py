"""
Dashboard WebSocket Server for Real-Time Visualization.

This module provides a WebSocket server that pushes real-time events
to connected dashboard clients for visualizing agent traffic and chaos injection.
"""

import asyncio
import json
import logging
import os
from typing import Set, Optional, Dict, Any
from pathlib import Path
import uuid
from datetime import datetime

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.responses import HTMLResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPI = None
    WebSocket = None
    WebSocketDisconnect = None
    HTMLResponse = None
    FileResponse = None
    StaticFiles = None
    uvicorn = None

from agent_chaos_sdk.dashboard.events import DashboardEvent

logger = logging.getLogger(__name__)


class DashboardServer:
    """
    WebSocket server for real-time dashboard visualization.
    
    This server runs in a separate async task and pushes events
    to connected clients via WebSocket.
    """
    
    def __init__(self, port: int = 8081, host: str = "127.0.0.1"):
        """
        Initialize the dashboard server.
        
        Args:
            port: Port to listen on (default: 8081).
            host: Host to bind to (default: 127.0.0.1).
        """
        if not FASTAPI_AVAILABLE:
            raise ImportError(
                "FastAPI and uvicorn are required for dashboard. "
                "Install with: pip install fastapi uvicorn"
            )
        
        self.port = port
        self.host = host
        
        # CRITICAL: Disable proxy for dashboard server
        # The dashboard server should NOT go through the chaos proxy
        # Save original proxy settings
        self._original_http_proxy = os.environ.get('HTTP_PROXY')
        self._original_https_proxy = os.environ.get('HTTPS_PROXY')
        self._original_no_proxy = os.environ.get('NO_PROXY', '')
        
        # Temporarily disable proxy for uvicorn
        if 'HTTP_PROXY' in os.environ:
            del os.environ['HTTP_PROXY']
        if 'HTTPS_PROXY' in os.environ:
            del os.environ['HTTPS_PROXY']
        # Add localhost to NO_PROXY
        no_proxy_list = self._original_no_proxy.split(',') if self._original_no_proxy else []
        no_proxy_list.extend(['127.0.0.1', 'localhost', f'127.0.0.1:{port}', f'localhost:{port}'])
        os.environ['NO_PROXY'] = ','.join(filter(None, no_proxy_list))
        
        self.app = FastAPI(title="Agent Chaos Dashboard")
        self.connected_clients: Set[WebSocket] = set()
        self._server_task: Optional[asyncio.Task] = None
        self._server_running = False
        self._uvicorn_server: Optional[uvicorn.Server] = None
        
        # Setup routes
        self._setup_routes()
        
        logger.info(f"DashboardServer initialized: {host}:{port} (proxy disabled for dashboard)")
    
    def _setup_routes(self) -> None:
        """Setup FastAPI routes."""
        runs_dir = Path(os.getenv("CHAOS_RUNS_DIR", "runs"))
        
        @self.app.get("/", response_class=HTMLResponse)
        async def get_dashboard():
            """Serve the dashboard HTML."""
            # Try multiple possible paths
            possible_paths = [
                Path(__file__).parent.parent.parent / "src" / "dashboard" / "index.html",
                Path(__file__).parent.parent / ".." / "src" / "dashboard" / "index.html",
                Path.cwd() / "src" / "dashboard" / "index.html",
            ]
            
            for dashboard_path in possible_paths:
                if dashboard_path.exists():
                    return FileResponse(dashboard_path)
            
            # Fallback: return embedded HTML
            return HTMLResponse(content=self._get_embedded_html())

        @self.app.get("/api/runs")
        async def list_runs():
            """List available run directories for history view."""
            if not runs_dir.exists():
                return {"runs": []}
            run_dirs = [d for d in runs_dir.iterdir() if d.is_dir()]
            run_dirs.sort(key=lambda d: d.name, reverse=True)
            runs = []
            for d in run_dirs:
                log_path = d / "logs" / "proxy.log"
                runs.append({
                    "id": d.name,
                    "has_log": log_path.exists(),
                })
            return {"runs": runs}

        @self.app.get("/api/runs/{run_id}/summary")
        async def get_run_summary(run_id: str):
            """Return summary metrics for a historical run."""
            log_path = runs_dir / run_id / "logs" / "proxy.log"
            if not log_path.exists():
                raise HTTPException(status_code=404, detail="Run log not found")

            total_requests = 0
            error_requests = 0
            chaos_injections = 0
            chaos_requests = 0
            tool_requests = 0
            tool_errors = 0
            llm_requests = 0
            llm_errors = 0
            input_validation_errors = 0

            try:
                with open(log_path, "r", encoding="utf-8") as log_file:
                    for line in log_file:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        total_requests += 1
                        status_code = entry.get("status_code")
                        if isinstance(status_code, int) and status_code >= 400:
                            error_requests += 1
                        chaos_applied = entry.get("chaos_applied") or []
                        if isinstance(chaos_applied, str):
                            chaos_list = [item for item in chaos_applied.split(",") if item]
                        elif isinstance(chaos_applied, list):
                            chaos_list = chaos_applied
                        else:
                            chaos_list = []
                        chaos_injections += len(chaos_list)
                        if chaos_list:
                            chaos_requests += 1

                        traffic_type = entry.get("traffic_type")
                        if traffic_type == "TOOL_CALL":
                            tool_requests += 1
                            if isinstance(status_code, int) and status_code >= 400:
                                tool_errors += 1
                        elif traffic_type == "LLM_API":
                            llm_requests += 1
                            if isinstance(status_code, int) and status_code >= 400:
                                llm_errors += 1
                        if status_code in (400, 422):
                            input_validation_errors += 1
            except Exception as e:
                logger.debug(f"Failed to read run summary {log_path}: {e}")

            error_rate = (error_requests / total_requests) if total_requests else 0.0
            tool_error_rate = (tool_errors / tool_requests) if tool_requests else 0.0
            llm_error_rate = (llm_errors / llm_requests) if llm_requests else 0.0
            success_rate = ((total_requests - error_requests) / total_requests) if total_requests else 0.0
            chaos_hit_rate = (chaos_requests / total_requests) if total_requests else 0.0
            input_error_rate = (input_validation_errors / total_requests) if total_requests else 0.0
            agent_metrics = {}
            metrics_path = runs_dir / run_id / "logs" / "agent_metrics.json"
            if metrics_path.exists():
                try:
                    with open(metrics_path, "r", encoding="utf-8") as metrics_file:
                        agent_metrics = json.load(metrics_file) or {}
                except Exception:
                    agent_metrics = {}
            return {
                "run_id": run_id,
                "total_requests": total_requests,
                "error_requests": error_requests,
                "error_rate": error_rate,
                "chaos_injections": chaos_injections,
                "tool_requests": tool_requests,
                "tool_errors": tool_errors,
                "tool_error_rate": tool_error_rate,
                "llm_requests": llm_requests,
                "llm_errors": llm_errors,
                "llm_error_rate": llm_error_rate,
                "success_rate": success_rate,
                "chaos_requests": chaos_requests,
                "chaos_hit_rate": chaos_hit_rate,
                "input_validation_errors": input_validation_errors,
                "input_error_rate": input_error_rate,
                "agent_metrics": agent_metrics,
            }

        @self.app.get("/api/runs/{run_id}/events")
        async def get_run_events(run_id: str):
            """Return normalized dashboard events for a historical run."""
            log_path = runs_dir / run_id / "logs" / "proxy.log"
            if not log_path.exists():
                raise HTTPException(status_code=404, detail="Run log not found")

            events = []
            try:
                with open(log_path, "r", encoding="utf-8") as log_file:
                    for idx, line in enumerate(log_file):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        request_id = f"run_{run_id}_{idx}"
                        method = entry.get("method")
                        url = entry.get("url")
                        traffic_type = entry.get("traffic_type")
                        traffic_subtype = entry.get("traffic_subtype")
                        status_code = entry.get("status_code")
                        chaos_applied = entry.get("chaos_applied") or []
                        if isinstance(chaos_applied, str):
                            chaos_applied = [item for item in chaos_applied.split(",") if item]

                        events.append({
                            "event_type": "request_started",
                            "request_id": request_id,
                            "method": method,
                            "url": url,
                            "agent_role": entry.get("agent_role"),
                            "traffic_type": traffic_type,
                            "traffic_subtype": traffic_subtype,
                            "timestamp": entry.get("timestamp"),
                        })

                        for strategy_name in chaos_applied:
                            events.append({
                                "event_type": "chaos_injected",
                                "request_id": request_id,
                                "strategy_name": strategy_name,
                                "phase": "response",
                                "details": {},
                                "timestamp": entry.get("timestamp"),
                            })

                        if status_code is not None:
                            events.append({
                                "event_type": "response_received",
                                "request_id": request_id,
                                "status_code": status_code,
                                "success": int(status_code) < 400,
                                "response_size": None,
                                "latency_ms": None,
                                "timestamp": entry.get("timestamp"),
                            })
            except Exception as e:
                logger.debug(f"Failed to read run log {log_path}: {e}")

            return {"events": events}
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time events."""
            await websocket.accept()
            self.connected_clients.add(websocket)
            logger.info(f"Dashboard client connected (total: {len(self.connected_clients)})")
            
            try:
                # Send welcome message
                await websocket.send_json({
                    "event_type": "connected",
                    "timestamp": datetime.now().isoformat(),
                    "message": "Connected to Agent Chaos Dashboard"
                })
                
                # Keep connection alive
                while True:
                    # Wait for ping or disconnect
                    try:
                        data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                        # Echo ping/pong
                        if data == "ping":
                            await websocket.send_json({"type": "pong"})
                    except asyncio.TimeoutError:
                        # Send keepalive
                        await websocket.send_json({
                            "event_type": "keepalive",
                            "timestamp": datetime.now().isoformat()
                        })
            except WebSocketDisconnect:
                pass
            finally:
                self.connected_clients.discard(websocket)
                logger.info(f"Dashboard client disconnected (remaining: {len(self.connected_clients)})")

    def _restore_proxy_env(self) -> None:
        """Restore proxy-related environment variables to their original values."""
        if self._original_http_proxy is None:
            os.environ.pop("HTTP_PROXY", None)
        else:
            os.environ["HTTP_PROXY"] = self._original_http_proxy

        if self._original_https_proxy is None:
            os.environ.pop("HTTPS_PROXY", None)
        else:
            os.environ["HTTPS_PROXY"] = self._original_https_proxy

        if self._original_no_proxy is None:
            os.environ.pop("NO_PROXY", None)
        else:
            os.environ["NO_PROXY"] = self._original_no_proxy
    
    def _get_embedded_html(self) -> str:
        """Get embedded HTML if file doesn't exist."""
        # This will be replaced by actual file
        return "<html><body>Dashboard HTML not found</body></html>"
    
    async def broadcast_event(self, event: DashboardEvent) -> None:
        """
        Broadcast an event to all connected clients.
        
        Args:
            event: DashboardEvent instance to broadcast.
        """
        if not self.connected_clients:
            return
        
        message = event.to_dict()
        message_json = json.dumps(message, ensure_ascii=False)
        
        # Broadcast to all clients
        disconnected = set()
        for client in self.connected_clients:
            try:
                await client.send_text(message_json)
            except Exception as e:
                logger.debug(f"Error sending to client: {e}")
                disconnected.add(client)
        
        # Remove disconnected clients
        for client in disconnected:
            self.connected_clients.discard(client)
    
    async def start(self) -> None:
        """Start the dashboard server in background."""
        if self._server_running:
            return
        
        try:
            config = uvicorn.Config(
                self.app,
                host=self.host,
                port=self.port,
                log_level="warning",  # Reduce noise
                access_log=False,  # Disable access logs
            )
            server = uvicorn.Server(config)
            
            # Start server in background task
            self._server_task = asyncio.create_task(server.serve())
            self._server_running = True
            
            # Wait a bit for server to actually start
            await asyncio.sleep(0.5)
            
            logger.info(f"Dashboard server started: http://{self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to start dashboard server: {e}", exc_info=True)
            self._server_running = False
            raise
    
    async def stop(self) -> None:
        """Stop the dashboard server."""
        # Always restore proxy environment variables on shutdown
        self._restore_proxy_env()
        if not self._server_running:
            return
        
        # Close all connections
        for client in list(self.connected_clients):
            try:
                await client.close()
            except Exception:
                pass
        self.connected_clients.clear()
        
        # Stop server
        if self._uvicorn_server:
            self._uvicorn_server.should_exit = True
        
        if self._server_task:
            self._server_task.cancel()
            try:
                await asyncio.wait_for(self._server_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        
        self._server_running = False
        logger.info("Dashboard server stopped")
    
    def get_url(self) -> str:
        """Get the dashboard URL."""
        return f"http://{self.host}:{self.port}"


# Global dashboard server instance (singleton)
_dashboard_server: Optional[DashboardServer] = None


def get_dashboard_server(port: int = 8081, host: str = "127.0.0.1") -> DashboardServer:
    """
    Get the global DashboardServer instance.
    
    Args:
        port: Port to listen on.
        host: Host to bind to.
        
    Returns:
        DashboardServer instance.
    """
    global _dashboard_server
    if _dashboard_server is None:
        _dashboard_server = DashboardServer(port=port, host=host)
    return _dashboard_server


def set_dashboard_server(server: DashboardServer) -> None:
    """
    Set the global DashboardServer instance.
    
    Args:
        server: DashboardServer instance to use.
    """
    global _dashboard_server
    _dashboard_server = server

