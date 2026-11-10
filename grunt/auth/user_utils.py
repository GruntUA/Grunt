import grunt
from grunt.api.context import whitelist


@whitelist()
async def ping(message: str = "pong"):
    """Simple ping-pong whitelisted method."""
    return {"message": message, "user": grunt.get_user(), "status": "success"}
