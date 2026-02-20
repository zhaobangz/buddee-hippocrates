# the entry point. it loops. 
# takes a user input, process the information -> run through the tools and gives an output 
from core.agent import Agent
from core.config import Config 
from core.tracing import setup_tracing, get_tracer, shutdown_tracing
from input_output.text_input import get_text_input, speech_input 
from input_output.text_output import send_text_output, speech_output 
import time 

# Initialize tracing
setup_tracing(service_name="buddi-agent")
tracer = get_tracer(__name__) 

def main():
    with tracer.start_as_current_span("main") as span:
        agent = Agent()
        span.set_attribute("agent.initialized", True)
        print(f"{Config.ASSISTANT_NAME} is ready!")

        # Start optional perception (screenshots / audio) if enabled in config
        try:
            if Config.ENABLE_SCREEN_CAPTURE or Config.ENABLE_AUDIO:
                started = agent.start_perception()
                if started:
                    print("Perception: started background capture (screenshots/audio)")
                    span.set_attribute("perception.started", True)
                else:
                    print("Perception: unavailable or failed to start")
        except Exception:
            print("Perception: error starting perception (check optional dependencies and permissions)")
    if Config.USE_VOICE:
        print("Voice mode enabled. You may speak now")

        #warm up speech recognition engine
        print("Initializing speech recognition...")
        time.sleep(1)

    else:
        print("Text mode enabled. Type your input below.")

    while True:
        # Get user input based on mode
        if Config.USE_VOICE:
            user_input = speech_input.get_speech_input()
            if user_input is None:  # Timeout or no speech detected
                continue
            if user_input == "Speech recognition service is unavailable.":
                print("Falling back to text mode.")
                Config.USE_VOICE = False
                continue
        else:
            user_input = get_text_input()
        
        # Check for exit commands
        if user_input and user_input.lower() in ['quit', 'exit', 'bye', 'goodbye', 'stop']:
            response = "Goodbye! Have a great day!"
            send_text_output(response)
            if Config.USE_VOICE:
                speech_output.send_speech_output(response)
            break
            
        # Process the input
        if user_input and user_input.strip():
            with tracer.start_as_current_span("handle_user_input") as input_span:
                input_span.set_attribute("input.length", len(user_input))
                response = agent.handle(user_input)
                input_span.set_attribute("response.length", len(response))
            
            # Output the response
            send_text_output(response)
            if Config.USE_VOICE:
                speech_output.send_speech_output(response)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Config.ASSISTANT_NAME}: Goodbye!")
    finally:
        # Clean up resources
        if Config.USE_VOICE:
            speech_output.stop()
        # Stop perception if it was started
        try:
            # If this module created an agent earlier, stop its perception
            Agent.stop_perception()
        except Exception:
            pass
        # Shutdown tracing to ensure all spans are exported
        shutdown_tracing()