import google.generativeai as genai
import os
import json
from pydantic import BaseModel, Field
from datetime import datetime, timedelta, timezone

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class RuleExtraction(BaseModel):
    is_rule: bool = Field(description="True if the text contains an architectural rule.")
    content: str = Field(description="The core rule formatted as a clear constraint.")
    ttl_days: int = Field(description="Days until this rule expires, default 3650.")

# Filter, format and structure CLI input
async def extract_rule(text: str) -> dict:
    model = genai.GenerativeModel("gemini-3.8-flash")
    response = await model.generate_content_async(  # Normalize data
        f"Extract any project rules from this text: {text}",
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=RuleExtraction          # Return only json data
        )
    )

    # Ignore random inputs
    data = json.loads(response.text)
    if not data.get("is_rule"):
        return None

    # Determine TTL from LLM response || set as 10 years
    expiration = datetime.now(timezone.utc) + timedelta(days=data.get("ttl_days", 3650))
    return {
        "content": data["content"],
        "expiresAt": expiration
    }

# Generate embedding for storage in Vector DB
async def generate_embedding(text: str) -> list:
    result = genai.embed_content(
        model="models/gemini-embedding-2",
        content=text,
        output_dimensionality=768
    )
    return result['embedding']

# Fetch relevant data from Vector DB and generate response
async def synthesize_answer(question: str, context_rules: list[str]) -> str:
    model = genai.GenerativeModel("gemini-3.8-flash")
    context_str = "\n".join([f"- {rule}" for rule in context_rules])
    prompt = f"""
    You are a project assistant. Answer the user's question based strictly on the following project rules.
    If the answer is not in the rules, state that you do not know.
    
    Rules:
    {context_str}
    
    Question: {question}
    """
    response = await model.generate_content_async(prompt)
    return response.text


class ConflictDetection(BaseModel):
    has_conflict: bool
    explanation: str
    conflicting_rules: list[str]

# Detect conflicts between to be inserted and existing set of rules
async def detect_conflict(new_rule: str, existing_rules: list[str]) -> dict:
    if not existing_rules:
        return {"has_conflict": False}
        
    model = genai.GenerativeModel("gemini-3.8-flash")
    context_str = "\n".join([f"- {rule}" for rule in existing_rules])
    
    prompt = f"""
    You are a strict architectural constraint checker. 
    Evaluate if the NEW RULE directly conflicts with or contradicts any of the EXISTING RULES.
    
    EXISTING RULES:
    {context_str}
    
    NEW RULE: {new_rule}
    """
    
    response = await model.generate_content_async(
        prompt,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=ConflictDetection
        )
    )
    return json.loads(response.text)