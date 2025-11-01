import requests
from googlesearch import search as google_search
from core.config import Config

class WebSearch:
    def __init__(self, num_results=3, search_engine='google', summarization=True, cache=True):
        self.num_results = num_results
        self.search_engine = search_engine
        self.summarization = summarization
        self.cache = cache
        self.search_results = {}

    def search(self, query):
        if self.cache and query in self.search_results:
            return self.search_results[query]

        try:
            # Get search results
            results = list(google_search(query, num_results=self.num_results))

            # For a more advanced implementation, you could:
            # 1. Scrape each page and summarize content
            # 2. Use a search API instead
            # 3. Integrate with the LLM to process results

            if results:
                if self.summarization:
                    # Use a summarization algorithm to condense the results into a shorter, more digestible form
                    summary = summarize_results(results)
                    self.search_results[query] = summary
                    return summary
                else:
                    self.search_results[query] = results
                    return f"Here are the top {self.num_results} results for '{query}':\n\n" + '\n'.join(results)
            else:
                return f"No results found for '{query}'"
        except Exception as e:
            return f"Search failed: {str(e)}"