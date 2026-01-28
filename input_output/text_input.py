# for the console input 
import readline  # for better handling with history 

def get_text_input(prompt="You: "):
    """get text input from console with basic command history
    
    args:
        prompt (str): the prompt to display to the user

    returns: str:user input text 
    
    """
    try:
        #read input with prompt 
        u_input = input(prompt).strip()
        return u_input
    except EOFError:
        #handle ctrl d (EOF)
        return 'exit'
    except KeyboardInterrupt:
        #handle ctrl c
        print()
        return 'exit'
    except Exception as e:
        print(f"Error getting input: {e}")
        return ""
    
    #Command history functionality 
def setup_input_history(history_file = ".input_history", max_history = 100):
    """setup inut history ffrom a file"""
    try:
        readline.set_history_length(max_history)
        try:
            with open(history_file, 'r') as f:
                for line in f:
                    readline.add_history(line.strip())
        except FileNotFoundError:
            pass # no history file was found, ignore

        # save history on exit 
        import atexit 
        atexit.register(save_input_history, history_file)
    
    except ImportError:
        pass # readline can't read onany platform 


def save_input_history(history_file = ".input-history"):
    """save command history to file"""

    try:
        with open(history_file, 'w') as f:
            for i in range(1, readline.get_current_history_length() +1):
                f.write(readline.get_history_item(i) + '\n')
    except:
        for e in Exception:
            print (f"file isn';t saved correectly {e}, please try again")



##initiaize input history on module load 
setup_input_history()

                


    


