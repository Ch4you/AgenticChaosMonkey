# Dashboard Troubleshooting Guide

## Issue: Connection Refused (ERR_CONNECTION_REFUSED)

If you see "This site can't be reached" or "ERR_CONNECTION_REFUSED" when trying to access `http://127.0.0.1:8081`, follow these steps:

### 1. Check if Dashboard Server Started

When you run `agent-chaos run`, you should see:
```
✓ Dashboard available at http://127.0.0.1:8081
```

If you see a warning instead, the dashboard server failed to start.

### 2. Verify Port Availability

Check if port 8081 is already in use:

```bash
# macOS/Linux
lsof -i :8081

# Or using netstat
netstat -an | grep 8081
```

If the port is in use, either:
- Stop the process using the port
- Use a different port (modify the code or wait for config option)

### 3. Check Dashboard Server Logs

The dashboard server logs errors. Check the console output when running `agent-chaos run` for any error messages.

### 4. Manual Test

Test the dashboard server manually:

```python
import asyncio
import threading
import time
from agent_chaos_sdk.dashboard.server import DashboardServer

def run_server():
    server = DashboardServer(port=8081, host='127.0.0.1')
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(server.start())
        print('✅ Server started')
        loop.run_forever()  # Keep running
    except Exception as e:
        print(f'❌ Error: {e}')
        import traceback
        traceback.print_exc()

thread = threading.Thread(target=run_server, daemon=True)
thread.start()
time.sleep(3)

# Test connection
import urllib.request
try:
    response = urllib.request.urlopen('http://127.0.0.1:8081/', timeout=3)
    print(f'✅ Dashboard accessible: {response.status}')
except Exception as e:
    print(f'❌ Dashboard not accessible: {e}')
```

### 5. Check Dependencies

Ensure FastAPI and uvicorn are installed:

```bash
pip install fastapi uvicorn
```

### 6. Check HTML File

Verify the dashboard HTML file exists:

```bash
ls -la src/dashboard/index.html
```

If missing, the dashboard will show a fallback message.

### 7. Common Issues

**Issue**: Server starts but immediately stops
- **Cause**: Event loop not kept alive
- **Fix**: Ensure `loop.run_forever()` is called after `server.start()`

**Issue**: Port already in use
- **Cause**: Another process using port 8081
- **Fix**: Kill the process or use a different port

**Issue**: FastAPI/uvicorn not installed
- **Cause**: Missing dependencies
- **Fix**: `pip install fastapi uvicorn[standard]`

**Issue**: Dashboard HTML not found
- **Cause**: File path resolution issue
- **Fix**: Ensure `src/dashboard/index.html` exists relative to project root

### 8. Alternative: Standalone Dashboard Server

If the integrated dashboard doesn't work, you can run it standalone:

```python
# dashboard_standalone.py
import asyncio
from agent_chaos_sdk.dashboard.server import DashboardServer

async def main():
    server = DashboardServer(port=8081, host='127.0.0.1')
    await server.start()
    print(f"Dashboard running at http://127.0.0.1:8081")
    print("Press Ctrl+C to stop")
    try:
        await asyncio.Event().wait()  # Wait forever
    except KeyboardInterrupt:
        await server.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

Run with:
```bash
python dashboard_standalone.py
```

### 9. Debug Mode

Enable debug logging to see what's happening:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

This will show detailed logs from the dashboard server.

### 10. Network Issues

If you're behind a firewall or proxy:
- Try `localhost` instead of `127.0.0.1`
- Check firewall settings
- Ensure no proxy is intercepting localhost traffic

## Quick Fix Checklist

- [ ] FastAPI and uvicorn installed
- [ ] Port 8081 not in use
- [ ] `src/dashboard/index.html` exists
- [ ] Dashboard server thread is running (check with `ps aux | grep python`)
- [ ] No firewall blocking port 8081
- [ ] Browser can access `http://127.0.0.1:8081` (not `https://`)

## Still Not Working?

1. Check the full error message in the console
2. Verify all dependencies: `pip list | grep -E "fastapi|uvicorn"`
3. Try accessing `http://localhost:8081` instead
4. Check if the dashboard server process is actually running
5. Review the implementation in `agent_chaos_sdk/dashboard/server.py`

