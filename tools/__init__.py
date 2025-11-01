# tools/__init__.py
from .browser import open_website
from .system import shutdown, get_system_info
from .search import web_search

__all__ = ['open_website', 'shutdown', 'get_system_info', 'web_search']