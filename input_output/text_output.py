import textwrap
from core.config import Config 

def send_text_output(text, width=80):
    """
    print formatted text output to console 
    
    args:
    text(str):text to diplay 
    width(int): maximum line width for wrapping 
    
    """
    if not text:
        return 
    
    #format the assiatant's name
    assistant_prefix = f"{Config.ASSISTANT_NAME}: "

    #wrap text to specified width
    wrapped_text = textwrap.fill(
        text,
        width = width - len(assistant_prefix),
        replace_whitespace = False
    )

    # add assistant prefix to first line indent subsequent lines
    lines = wrapped_text.split('\n')
    for i, line in enumerate(lines):
        if i == 0:
            print(assistant_prefix + line)
        else:
            print(' ' * len(assistant_prefix) + line)
    
    # Add a separator for better readability
    print('-' * min(width, 80))

    # optionally
    