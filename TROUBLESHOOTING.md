# Buddi Clinical Agent - Troubleshooting Guide

Common issues and clinical system fixes.

## Clinical System Issues

### Issue: "ModuleNotFoundError: No module named 'sumy' or 'nltk'"
**Problem:** Missing dependencies for clinical summarization.
**Solution:**
```bash
pip install -r requirements.txt
python -c "import nltk; nltk.download('punkt')"
```

### Issue: "PyAudio installation error" (macOS)
**Problem:** Missing PortAudio system dependency.
**Solution:**
```bash
brew install portaudio
pip install pyaudio
```

### Issue: "Tesseract not found" (EHR Reader)
**Problem:** The OCR engine for scanning patient records is missing.
**Solution:**
```bash
brew install tesseract
```

## Dashboard & Connectivity

### Issue: "API Offline" in the Dashboard
**Problem:** Backend FastAPI server is not reachable.
**Solution:**
1. Verify backend is running: `curl http://localhost:8000/api/health`
2. Ensure you're running the server from the project root.
3. Check `web/script.js` matches your backend port (default 8000).

### Issue: "CORS error" in Browser Console
**Problem:** Secure browser restriction on API calls.
**Solution:**
1. Ensure both servers are running.
2. Check `backend/api.py` allows origins for `localhost:5000`.

## Clinical Safety Layer

### Issue: Actions are being "Blocked"
**Problem:** The Safety Layer (core/safety.py) is triggered.
**Solution:**
- The system correctly blocks direct diagnosis or prescription commands. 
- To check why an action was blocked, review the Audit Log in the dashboard or `audit_log.json`.

---

**Next Steps**: If issues persist, run the dev launcher `./run-web-dev.sh` and check the logs in the `logs/` folder.
