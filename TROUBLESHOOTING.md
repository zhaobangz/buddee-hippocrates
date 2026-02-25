# Troubleshooting Guide - Buddi Agent Web Interface

Common issues and how to fix them.

## Setup & Installation Issues

### Issue: "Python is not installed"
**Solution:**
- Install Python 3.9+ from https://python.org
- Verify: `python3 --version`

### Issue: "ModuleNotFoundError: No module named 'fastapi'"
**Solution:**
```bash
pip install fastapi uvicorn[standard]
```

### Issue: "Permission denied" when running scripts
**Solution:**
```bash
chmod +x web-server.py run-web.sh run-web-dev.sh
```

### Issue: "Uvicorn not found"
**Solution:**
```bash
pip install uvicorn[standard]
# Note: The [standard] extras installs HTTP+WS dependencies
```

## Server Startup Issues

### Issue: "Address already in use" error
**Problem:** Port 8000 or 5000 is already in use

**Solution:**
1. Find what's using the port:
```bash
# macOS/Linux
lsof -i :8000
lsof -i :5000

# Windows
netstat -ano | findstr :8000
netstat -ano | findstr :5000
```

2. Kill the process:
```bash
# macOS/Linux
kill -9 <PID>

# Or use alternative ports
python3 -m uvicorn backend.api:app --port 8001
# Then update web/script.js API_BASE_URL
```

### Issue: Backend starts but keeps crashing
**Problem:** Usually an error in your agent code

**Solution:**
1. Check the error message in terminal
2. Look at `core/agent.py` initialization
3. Try running just the agent code:
```python
from core.agent import Agent
agent = Agent()  # Should not error
```

### Issue: Frontend loads but shows "API Offline"
**Problem:** Backend not running or not accessible

**Solution:**
1. Verify backend is running:
```bash
curl http://localhost:8000/api/health
```
2. Check firewall isn't blocking port 8000
3. Check `API_BASE_URL` in `web/script.js` is correct
4. Check browser console for errors (F12)

## Frontend Issues

### Issue: Web page loads but looks broken
**Problem:** CSS or JavaScript not loading

**Solution:**
1. Open browser console: F12 → Console tab
2. Check for "404 Not Found" errors
3. Verify files exist in `web/` directory:
   - index.html
   - style.css
   - script.js
4. Try hard refresh: Ctrl+F5 (or Cmd+Shift+R on Mac)

### Issue: Can't send messages
**Problem:** Usually backend not running or API connection issue

**Solution:**
1. Check status indicator shows "Connected"
2. Open browser console (F12)
3. Check for error messages
4. Verify API is running: `curl http://localhost:8000/api/health`
5. Check network tab in DevTools for failed requests

### Issue: Chat shows "Echo: ..." messages
**Problem:** Agent logic not implemented

**Solution:**
This is expected! The backend is set up but needs your agent logic:
1. Edit `backend/api.py`
2. Find `process_user_input()` function
3. Implement your actual agent call there
4. See WEB_INTERFACE_SUMMARY.md for details

### Issue: Messages aren't being saved
**Problem:** No database set up yet

**Solution:**
The web interface doesn't save history to a database. The agent can have memory if enabled. To persist across browser sessions, you'll need to:
1. Add a database (SQLite, PostgreSQL, etc.)
2. Add endpoints to save/load chat history
3. See CLOUD_DEPLOYMENT_GUIDE.md for databases

## API Issues

### Issue: "CORS error" in browser console
**Problem:** Frontend can't access backend due to CORS restrictions

**Error message example:**
```
Access to XMLHttpRequest at 'http://localhost:8000/api/chat' from origin 'http://localhost:5000' 
has been blocked by CORS policy
```

**Solution:**
1. Check backend is actually running
2. Check ports match (8000 for backend, 5000 for frontend)
3. In `backend/api.py`, ensure CORS middleware is added:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Issue: API returns 500 error
**Problem:** Server-side error in your agent code

**Solution:**
1. Check backend terminal for error stack trace
2. Most likely: agent initialization failed
3. Check `core/agent.py` for missing dependencies
4. Check `.env` file has all required variables

### Issue: API returns 400 "Message cannot be empty"
**Problem:** You sent an empty message

**Solution:**
Don't send empty messages. This is the API correctly rejecting bad input.

## Configuration Issues

### Issue: Agent not finding config files
**Problem:** Wrong working directory

**Solution:**
Always run from project root:
```bash
# Correct
cd ~/Desktop/IDEs/buddi
python3 web-server.py

# Wrong
cd ~/Desktop/IDEs/buddi/backend
python3 web-server.py
```

### Issue: Agent can't find credentials
**Problem:** Missing or wrong `.env` file

**Solution:**
1. Check `.env` file exists in project root
2. Check it has required variables:
```
OPENAI_API_KEY=xxx  # or your API key
GOOGLE_API_KEY=xxx
LLM_MODEL=deepseek-v1
# etc
```
3. Restart backend after changing `.env`

## Performance Issues

### Issue: Web interface is slow to load
**Problem:** Usually backend initialization or network

**Solution:**
1. Check internet connection
2. Check backend startup isn't hanging
3. Look for missing dependencies during agent init
4. Use development launcher with logging: `./run-web-dev.sh`

### Issue: Messages take very long to respond
**Problem:** Agent processing slow or model inference slow

**Solution:**
1. This is normal if using large LLMs locally
2. Check terminal for progress messages
3. Consider using smaller/faster models
4. Check system resources: `top` or Task Manager

## Browser Issues

### Issue: Works in one browser but not another
**Problem:** Browser compatibility or cached data

**Solution:**
1. Try different browser (Chrome, Firefox, Safari)
2. Clear browser cache: Ctrl+Shift+Del
3. Try private/incognito window
4. Check browser console for errors

### Issue: Mobile browser shows blank screen
**Problem:** Server not accessible or UI not responsive

**Solution:**
1. If on mobile, ensure backend is accessible from phone
2. Use full IP address: `http://192.168.1.100:5000` (not localhost)
3. Check firewall allows connections
4. See if browser console shows errors (F12)

## Logging & Debugging

### Enable detailed logging
For development, use the dev launcher:
```bash
./run-web-dev.sh
```

This creates logs in `logs/` directory:
- `logs/backend.log` - FastAPI logs
- `logs/frontend.log` - HTTP server logs

### Check logs in real-time
```bash
# Backend
tail -f logs/backend.log

# Frontend
tail -f logs/frontend.log

# Both
tail -f logs/*.log
```

### Browser developer tools
Press F12 to open:
- **Console**: See errors and messages
- **Network**: See API requests/responses
- **Application**: Check localStorage, etc.

### Test API directly
```bash
# Get status
curl http://localhost:8000/api/status

# Send message
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "test", "include_history": false}'

# Check API docs
# Open in browser: http://localhost:8000/docs
```

## Common Mistakes

### ❌ Running from wrong directory
```bash
# ❌ Don't do this
cd backend
python3 web-server.py

# ✅ Do this
cd buddi  # Project root
python3 web-server.py
```

### ❌ Forgetting to install dependencies
```bash
# ❌ This will fail
python3 web-server.py

# ✅ Do this first
pip install -r requirements.txt
python3 web-server.py
```

### ❌ Not connecting agent logic
The backend works but won't actually use your agent until you implement it. See WEB_INTERFACE_SUMMARY.md.

### ❌ Using localhost from another machine
```bash
# ❌ Won't work from another computer
http://localhost:5000

# ✅ Use the actual IP
http://192.168.1.100:5000
```

## Still Having Issues?

1. **Check the logs**: 
   - Backend: Terminal output or `logs/backend.log`
   - Frontend: Browser console (F12)

2. **Read the documentation**:
   - WEB_SETUP_GUIDE.md - Setup details
   - WEB_INTERFACE_SUMMARY.md - Implementation details
   - CLOUD_DEPLOYMENT_GUIDE.md - Deployment info

3. **Test each component separately**:
   - Is Python working? `python3 --version`
   - Is backend running? `curl http://localhost:8000/api/health`
   - Is frontend running? Can you open http://localhost:5000?
   - Is your agent working? Test directly with `core/agent.py`

4. **Search error messages**:
   - Copy the error message into Google
   - Include "FastAPI" or "uvicorn" for more relevant results

5. **Check your agent code**:
   - Most issues are in `core/agent.py` initialization
   - Try running agent alone: `python3 -c "from core.agent import Agent; Agent()"`

Good luck! 🚀
