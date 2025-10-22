from fastapi import FastAPI
from mangum import Mangum
import strings

app = FastAPI()

app.include_router(strings.router)

@app.get("/")
def home():
    return {"details":"HNG Stage 1 Task"}

handler = Mangum(app)