from fastapi import FastAPI
from Routes import orders
from mangum import Mangum

app = FastAPI()
app.include_router(orders.router)
handler = Mangum(app)
