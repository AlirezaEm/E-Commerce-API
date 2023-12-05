from decimal import Decimal
from pydantic import BaseModel

class Item(BaseModel):
    item_id: str
    name: str
    description: str | None = None
    price: Decimal
    quantity: int
