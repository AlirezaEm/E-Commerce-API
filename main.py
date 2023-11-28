from fastapi import FastAPI
from Routes import orders

app = FastAPI()
app.include_router(orders.router)

