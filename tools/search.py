# Unused import removed
from googlesearch import search as google_search  # type: ignore

# Optional: summarized content Extraction
try:
    from sumy.parsers.plaintext import PlaintextParser  # type: ignore
    from sumy.nlp.tokenizers import Tokenizer  # type: ignore
    from sumy.summarizers.lsa import LsaSummarizer  # type: ignore
    from sumy.nlp.stemmers import Stemmer  # type: ignore
    from sumy.utils import get_stop_words  # type: ignore
    _HAS_SUMY = True
except ImportError:
    PlaintextParser = None  # type: ignore
    Tokenizer = None  # type: ignore
    LsaSummarizer = None  # type: ignore
    Stemmer = None  # type: ignore
    get_stop_words = None  # type: ignore
    _HAS_SUMY = False


class WebSearch:
    def __init__(self, num_results=3, search_engine='google', summarization=True, cache=True):
        self.num_results = num_results
        self.search_engine = search_engine
        self.summarization = summarization
        self.cache = cache
        self.search_results = {}

    def summarize_results(self, results):  # type: ignore
        if not _HAS_SUMY:
            return '\n\n'.join(results)

        # Combine all the results into a single text
        text = '\n\n'.join(results)

        # Summarize the text using LSA
        parser = PlaintextParser.from_string(text, Tokenizer('english'))  # type: ignore
        stemmer = Stemmer("english")  # type: ignore
        summarizer = LsaSummarizer(stemmer)  # type: ignore
        summarizer.stop_words = get_stop_words('english')  # type: ignore
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

            if results:
                if self.summarization:
                    summary = self.summarize_results(results)
                    self.search_results[query] = summary
                    return summary
                else:
                    self.search_results[query] = results
                    return f"Here are the top {self.num_results} results for '{query}':\n\n" + '\n'.join(results)
            else:
                return f"No results found for '{query}'"
        except Exception as e:
            return f"Search failed: {str(e)}"