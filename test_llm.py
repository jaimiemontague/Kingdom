from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
try:
    client.chat.completions.create(
        model="gpt-5-nano",
        messages=[{"role": "user", "content": "hello"}],
        max_completion_tokens=10
    )
except Exception as e:
    print("EXCEPTION:", type(e), str(e))
