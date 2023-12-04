from pydantic import BaseModel

class Item(BaseModel):
    item_id: str
    name: str
    description: str | None = None
    price: float
    quantity: int
