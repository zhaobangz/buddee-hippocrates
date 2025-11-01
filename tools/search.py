# google search va brower (later upgrade to api)

import requests
from googlesearch import search as google_search
from core.config import Config

def web_search(query, num_results=3):
    """Perform a web search and return summarized results"""
    try:
        # Get search results
        results = list(google_search(query, num_results=num_results))
        
        # For a more advanced implementation, you could:
        # 1. Scrape each page and summarize content
        # 2. Use a search API instead
        # 3. Integrate with the LLM to process results
        
        if results:
            response = f"Here are the top {num_results} results for '{query}':\n\n"
            for i, result in enumerate(results, 1):
                response += f"{i}. {result}\n"
            return response
        else:
            return f"No results found for '{query}'"
    except Exception as e:
        return f"Search failed: {str(e)}"