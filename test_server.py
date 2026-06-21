from fastapi import FastAPI
import uvicorn
import sys

app = FastAPI()

@app.get('/')
def root():
    return {'status': 'ok'}

if __name__ == '__main__':
    print('SERVER_STARTING')
    sys.stdout.flush()
    uvicorn.run(app, host='127.0.0.1', port=8000)
