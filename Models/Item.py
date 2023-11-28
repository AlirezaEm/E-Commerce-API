from pydantic import BaseModel

class Item(BaseModel):
    item_id: str
    name: str
    description: str = None
    price: float
    quantity: int