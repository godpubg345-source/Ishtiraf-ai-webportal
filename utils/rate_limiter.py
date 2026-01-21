"""
IshtirafAI - API Rate Limiter
==============================
Protect API endpoints from abuse.
"""

from functools import wraps
from flask import request, jsonify, g
from datetime import datetime, timedelta
import time

# In-memory rate limit storage (use Redis in production)
_rate_limits = {}


class RateLimiter:
    """Simple in-memory rate limiter. Use Redis for production."""
    
    def __init__(self, app=None):
        self.app = app
        self.enabled = True
        self.default_limit = 100  # requests per window
        self.default_window = 60  # seconds
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask app."""
        self.app = app
        self.enabled = app.config.get('RATE_LIMIT_ENABLED', True)
        self.default_limit = app.config.get('RATE_LIMIT_DEFAULT', 100)
        self.default_window = app.config.get('RATE_LIMIT_WINDOW', 60)
        
        # Try to use Redis if available
        self.use_redis = False
        redis_url = app.config.get('REDIS_URL')
        if redis_url:
            try:
                import redis
                self.redis = redis.from_url(redis_url)
                self.use_redis = True
                print("✅ Rate Limiter using Redis")
            except Exception as e:
                print(f"⚠️ Redis not available, using memory: {e}")
        
        print(f"✅ Rate Limiter: {self.default_limit} req / {self.default_window}s")
    
    def _get_key(self, identifier: str, endpoint: str) -> str:
        """Generate rate limit key."""
        return f"ratelimit:{endpoint}:{identifier}"
    
    def _get_identifier(self) -> str:
        """Get unique identifier for the request (IP or user ID)."""
        from flask_login import current_user
        
        if current_user.is_authenticated:
            return f"user:{current_user.id}"
        return f"ip:{request.remote_addr}"
    
    def is_allowed(self, endpoint: str, limit: int = None, window: int = None) -> tuple:
        """
        Check if request is allowed.
        
        Returns: (allowed: bool, remaining: int, reset_time: int)
        """
        if not self.enabled:
            return True, -1, 0
        
        limit = limit or self.default_limit
        window = window or self.default_window
        
        identifier = self._get_identifier()
        key = self._get_key(identifier, endpoint)
        now = time.time()
        
        if self.use_redis:
            return self._check_redis(key, limit, window, now)
        else:
            return self._check_memory(key, limit, window, now)
    
    def _check_memory(self, key: str, limit: int, window: int, now: float) -> tuple:
        """Check rate limit using in-memory storage."""
        global _rate_limits
        
        if key not in _rate_limits:
            _rate_limits[key] = {'count': 0, 'window_start': now}
        
        data = _rate_limits[key]
        
        # Reset window if expired
        if now - data['window_start'] > window:
            data['count'] = 0
            data['window_start'] = now
        
        # Check limit
        if data['count'] >= limit:
            reset_time = int(data['window_start'] + window - now)
            return False, 0, reset_time
        
        # Increment counter
        data['count'] += 1
        remaining = limit - data['count']
        reset_time = int(data['window_start'] + window - now)
        
        return True, remaining, reset_time
    
    def _check_redis(self, key: str, limit: int, window: int, now: float) -> tuple:
        """Check rate limit using Redis."""
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        results = pipe.execute()
        
        count = results[0]
        remaining = max(0, limit - count)
        
        if count > limit:
            ttl = self.redis.ttl(key)
            return False, 0, ttl
        
        return True, remaining, window
    
    def limit(self, limit: int = None, window: int = None, error_message: str = None):
        """
        Decorator to apply rate limiting to a route.
        
        Usage:
            @app.route('/api/diagnoses', methods=['POST'])
            @rate_limiter.limit(30, 60)  # 30 requests per 60 seconds
            def create_diagnosis():
                ...
        """
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                endpoint = f.__name__
                allowed, remaining, reset_time = self.is_allowed(endpoint, limit, window)
                
                # Add rate limit headers
                g.rate_limit_remaining = remaining
                g.rate_limit_reset = reset_time
                
                if not allowed:
                    return jsonify({
                        'error': 'Rate limit exceeded',
                        'message': error_message or f'Too many requests. Try again in {reset_time} seconds.',
                        'retry_after': reset_time
                    }), 429
                
                return f(*args, **kwargs)
            return decorated_function
        return decorator


# Global instance
rate_limiter = RateLimiter()


def init_rate_limiter(app):
    """Initialize rate limiter with app."""
    rate_limiter.init_app(app)
    
    # Add rate limit headers to all responses
    @app.after_request
    def add_rate_limit_headers(response):
        if hasattr(g, 'rate_limit_remaining'):
            response.headers['X-RateLimit-Remaining'] = str(g.rate_limit_remaining)
            response.headers['X-RateLimit-Reset'] = str(g.rate_limit_reset)
        return response
    
    return rate_limiter


# Convenience decorators for common limits
def limit_auth(f):
    """5 requests per minute for auth endpoints."""
    return rate_limiter.limit(5, 60, "Too many login attempts. Please wait.")(f)


def limit_api(f):
    """100 requests per minute for general API."""
    return rate_limiter.limit(100, 60)(f)


def limit_export(f):
    """10 exports per hour."""
    return rate_limiter.limit(10, 3600, "Export limit reached. Try again later.")(f)
