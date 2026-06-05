import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TAVILY_API_KEY")

response = requests.post(
    "https://api.tavily.com/search",
    json={
        "api_key": API_KEY,
        "query": "yash singh programming",
        "search_depth": "basic",
        "max_results": 5
    }
)

print(response.json()) 