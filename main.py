from fastapi import FastAPI
import strings

app = FastAPI()

app.include_router(strings.router)

@app.get("/")
def home():
    return {"details":"HNG Stage 1 Task"}