# runtime_flags.py - Runtime propagation mechanism
"""
SUPPRESS_EXCEPTIONS is CONFIGURED in config/settings.py.
bot_app.py sets runtime_flags.SUPPRESS_EXCEPTIONS at startup,
and all modules that import this see the current value.
"""
SUPPRESS_EXCEPTIONS = True  # Default; overridden by bot_app.py
