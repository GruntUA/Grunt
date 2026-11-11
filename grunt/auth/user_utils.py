from grunt.api.context import whitelist
from grunt.auth.current import acting_user


@whitelist()
async def ping(message: str = "pong"):
    """Simple ping-pong whitelisted method."""
    return {"message": message, "user": acting_user(), "status": "success"}
