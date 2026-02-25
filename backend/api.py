"""
FastAPI backend for Buddi Agent
Exposes the agent functionality as REST API endpoints for the web interface
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import logging

# Import the agent from core
from core.agent import Agent
from core.config import Config
from core.tracing import setup_tracing, get_tracer, shutdown_tracing

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize tracing
setup_tracing(service_name="buddi-web-backend")
tracer = get_tracer(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Buddi Agent API",
    description="REST API for Buddi AI Agent",
    version="1.0.0"
)

# Add CORS middleware to allow web frontend to access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global agent instance
agent: Optional[Agent] = None


class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    message: str
    include_history: bool = False


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    response: str
    status: str = "success"
    message_id: Optional[str] = None


class StatusResponse(BaseModel):
    """Response model for status endpoint"""
    agent_running: bool
    assistant_name: str
    memory_enabled: bool
    use_voice: bool


@app.on_event("startup")
async def startup_event():
    """Initialize agent on startup"""
    global agent
    try:
        with tracer.start_as_current_span("startup") as span:
            logger.info("Initializing Buddi Agent...")
            agent = Agent()
            span.set_attribute("agent.initialized", True)
            logger.info(f"{Config.ASSISTANT_NAME} is ready!")
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    try:
        shutdown_tracing()
        logger.info("Agent shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


@app.get("/api/health")
async def health_check():
    """Health check endpoint - useful for deployment monitoring"""
    return {
        "status": "healthy",
        "service": "buddi-agent-api"
    }


@app.get("/api/status", response_model=StatusResponse)
async def get_status():
    """Get the current status of the agent"""
    return StatusResponse(
        agent_running=agent is not None,
        assistant_name=Config.ASSISTANT_NAME,
        memory_enabled=Config.MEMORY_ENABLED,
        use_voice=Config.USE_VOICE
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Send a message to the agent and get a response
    
    Args:
        request: ChatRequest containing the user message
        
    Returns:
        ChatResponse with the agent's response
    """
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    try:
        with tracer.start_as_current_span("chat_request") as span:
            span.set_attribute("input.length", len(request.message))
            span.set_attribute("include_history", request.include_history)
            
            # Process the input through the agent
            # This will use the agent's process() method or similar
            logger.info(f"Processing message: {request.message[:100]}")
            
            # TODO: Implement the actual agent processing
            # For now, return a placeholder response
            response_text = await process_user_input(request.message)
            
            span.set_attribute("response.length", len(response_text))
            
            return ChatResponse(
                response=response_text,
                status="success"
            )
    except Exception as e:
        logger.error(f"Error processing chat: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")


@app.post("/api/reset")
async def reset_agent():
    """Reset the agent's memory"""
    global agent
    
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        with tracer.start_as_current_span("reset_agent"):
            if agent.memory:
                agent.memory.clear_history()
                return {"status": "success", "message": "Agent memory cleared"}
            return {"status": "success", "message": "No memory to clear"}
    except Exception as e:
        logger.error(f"Error resetting agent: {e}")
        raise HTTPException(status_code=500, detail=f"Error resetting agent: {str(e)}")


async def process_user_input(user_input: str) -> str:
    """
    Process user input through the agent
    
    Args:
        user_input: The user's message
        
    Returns:
        The agent's response
        
    Note: This is a placeholder - implement based on your Agent.process() method
    """
    global agent
    
    if agent is None:
        return "Agent not initialized"
    
    try:
        # TODO: Call the appropriate method on agent based on your implementation
        # This might be something like:
        # response = agent.process(user_input)
        # or
        # response = agent.chat(user_input)
        
        # For now, return a simple response
        logger.info(f"Processing input: {user_input}")
        
        # Add logic to call your agent's methods here
        # Example (adjust based on your actual agent implementation):
        # response = agent.detect_intent(user_input)
        # # ... then process based on intent
        
        return f"Echo: {user_input}"  # Placeholder
        
    except Exception as e:
        logger.error(f"Error in process_user_input: {e}")
        raise


if __name__ == "__main__":
    import uvicorn
    
    # Run the server
    # For production, use: gunicorn -w 4 -k uvicorn.workers.UvicornWorker backend.api:app
    uvicorn.run(
        app,
        host="0.0.0.0",  # Listen on all network interfaces
        port=8000,       # Change this if needed
        log_level="info"
    )
