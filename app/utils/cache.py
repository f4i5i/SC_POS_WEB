"""
Caching utilities for the POS application
Uses Flask-Caching for improved performance
"""

from functools import wraps

# Try to import Flask-Caching
try:
    from flask_caching import Cache
    cache = Cache()
    CACHE_AVAILABLE = True
except ImportError:
    cache = None
    CACHE_AVAILABLE = False


def init_cache(app):
    """Initialize the cache with the Flask app"""
    if CACHE_AVAILABLE and cache:
        cache.init_app(app)
        app.logger.info(f"Cache initialized with type: {app.config.get('CACHE_TYPE', 'SimpleCache')}")
        return cache
    else:
        app.logger.warning("Flask-Caching not installed. Caching disabled.")
        return None


def cached_view(timeout=300, key_prefix='view'):
    """
    Decorator for caching view results.
    Falls back to no caching if Flask-Caching is not available.
    """
    def decorator(f):
        if CACHE_AVAILABLE and cache:
            return cache.cached(timeout=timeout, key_prefix=key_prefix)(f)
        return f
    return decorator


def cache_key_with_user(*args, **kwargs):
    """Generate cache key including current user ID"""
    from flask_login import current_user
    user_id = current_user.id if current_user.is_authenticated else 'anon'
    return f"user_{user_id}"


def invalidate_cache(key_prefix):
    """Invalidate cache entries with given prefix"""
    if CACHE_AVAILABLE and cache:
        cache.delete_memoized(key_prefix)


def clear_all_cache():
    """Clear all cached data"""
    if CACHE_AVAILABLE and cache:
        cache.clear()


# Cache decorators for common use cases
def cache_dashboard(timeout=300):
    """Cache dashboard data for 5 minutes"""
    return cached_view(timeout=timeout, key_prefix='dashboard')


def cache_product_list(timeout=120):
    """Cache product list for 2 minutes"""
    return cached_view(timeout=timeout, key_prefix='products')


def cache_report(timeout=600):
    """Cache report data for 10 minutes"""
    return cached_view(timeout=timeout, key_prefix='report')
