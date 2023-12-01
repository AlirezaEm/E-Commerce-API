from typing import List
from pydantic import BaseModel
from Models.Item import Item

class ShoppingCart(BaseModel):
    cart_id: str
    items: List[Item] = []
    state: str = "open"
