from app.ai.gemini import GeminiEngine

engine = GeminiEngine()
result = engine.generate('Return this exact JSON: {"msg": "hi"}')
print(result)