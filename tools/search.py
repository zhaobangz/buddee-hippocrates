import requests
from googlesearch import search as google_search
from core.config import Config

from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words

class WebSearch:
    def __init__(self, num_results=3, search_engine='google', summarization=True, cache=True):
        self.num_results = num_results
        self.search_engine = search_engine
        self.summarization = summarization
        self.cache = cache
        self.search_results = {}

    def summarize_results(self, results):
        # Combine all the results into a single text
        text = '\n\n'.join(results)

        # Summarize the text using LSA
        parser = PlaintextParser.from_string(text, Tokenizer('english'))
        stemmer = Stemmer("english")
        summarizer = LsaSummarizer(stemmer)
        summarizer.stop_words = get_stop_words('english')
        summary = summarizer(parser.document, 2)  # summarize to 2 sentences

        # Join the summary sentences into a single string
        summary_text = ' '.join([sent.sentences[0] for sent in summary])

        return summary_text

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
                    summary = summarize_results(self, results)
                    self.search_results[query] = summary
                    return summary
                else:
                    self.search_results[query] = results
                    return f"Here are the top {self.num_results} results for '{query}':\n\n" + '\n'.join(results)
            else:
                return f"No results found for '{query}'"
        except Exception as e:
            return f"Search failed: {str(e)}"