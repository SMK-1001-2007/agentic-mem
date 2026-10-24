from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket
from pydantic import BaseModel
from contextlib import asynccontextmanager
from . import database, llm
import asyncio

connected_clients = set()

async def watch_changes():
    # Listen to the MongoDB Change Stream and broadcast new rules to local IDE files
    async with await database.collection.watch() as stream:
        async for change in stream:
            if change["operationType"] == "insert":
                rule_text = change["fullDocument"]["content"]
                for client in connected_clients:
                    await client.send_text(f"NEW_RULE:{rule_text}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    asyncio.create_task(watch_changes())
    yield

app = FastAPI(lifespan=lifespan)

class PromptRequest(BaseModel):
    text: str

@app.post("/remember")
async def remember_rule(request: PromptRequest):
    rule_data = await llm.extract_rule(request.text)
    if not rule_data:
        return {"status": "No rule detected", "type": "error"}
        
    embedding = await llm.generate_embedding(rule_data["content"])
    rule_data["embedding"] = embedding
    
    similar_docs = await database.search_memories(embedding)
    
    if similar_docs:
        existing_rules = [doc["content"] for doc in similar_docs]
        conflict_assessment = await llm.detect_conflict(rule_data["content"], existing_rules)
        
        if conflict_assessment.get("has_conflict"):
            return {
                "status": "Conflict detected", 
                "type": "conflict", 
                "explanation": conflict_assessment["explanation"],
                "conflicting_rules": conflict_assessment["conflicting_rules"]
            }
            
    await database.insert_memory(rule_data)
    return {"status": "Rule saved to shared memory", "type": "success"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        connected_clients.remove(websocket)
        

class AskRequest(BaseModel):
    question: str

@app.post("/ask")
async def ask_memory(request: AskRequest):
    query_vector = await llm.generate_embedding(request.question)
    results = await database.search_memories(query_vector)
    
    if not results:
        return {"answer": "No relevant project rules found in memory."}
        
    context_rules = [doc["content"] for doc in results]
    
    final_answer = await llm.synthesize_answer(request.question, context_rules)
    return {"answer": final_answer}


class DeleteRequest(BaseModel):
    content: str

@app.post("/forget")
async def forget_memory(request: DeleteRequest):
    query_vector = await llm.generate_embedding(request.content)
    results = await database.search_memories(query_vector)
    
    if not results:
        return {"status": "No relevant rules found in memory to delete."}
        
    target_rule = results[0]["content"]
    success = await database.delete_memory(target_rule)
    
    if success:
        for client in connected_clients:
            try:
                await client.send_text(f"DELETE_RULE:{target_rule}")
            except Exception:
                pass 
                
        return {"status": f"Semantically matched and deleted:\n- {target_rule}"}
        
    return {"status": "Rule matching process failed."}