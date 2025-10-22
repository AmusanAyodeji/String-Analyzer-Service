from fastapi import FastAPI
import strings
import uvicorn
from pyngrok import ngrok
import threading

app = FastAPI()

app.include_router(strings.router)

@app.get("/")
def home():
    return {"details":"HNG Stage 1 Task"}

def start_ngrok():
    # Open a tunnel on the same port as uvicorn
    public_url = ngrok.connect(8000)
    print(f"\n🚀 Public URL: {public_url}\n")

def start_uvicorn():
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    threading.Thread(target=start_ngrok).start()
    start_uvicorn()