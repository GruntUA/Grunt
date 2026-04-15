import grunt

@grunt.whitelist()
async def ping(message: str = "pong"):
    """Simple ping-pong whitelisted method."""
    return {
        "message": message,
        "user": await grunt.get_current_user(),
        "status": "success"
    }
