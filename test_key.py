from trading.api.utils import generate_token
from trading.config import ConfigManager

cfg = ConfigManager().load()
token = generate_token(user_id="test", api_key=cfg["api_key"])
print(token)
