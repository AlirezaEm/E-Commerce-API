from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from DB.fakeDB import shopping_carts_db
from Models.ShoppingCart import ShoppingCart

router = APIRouter()

class Id(BaseModel):
    id: str

# POST /v1/orders : Create an empty shopping cart for the user
@router.post("/v1/orders", response_model=ShoppingCart)
async def create_shopping_cart(user_id: Id):
    if user_id.id in shopping_carts_db:
        raise HTTPException(status_code=400, detail="Shopping cart already exists for this user")
    
    shopping_cart = ShoppingCart(cart_id=user_id.id)
    shopping_carts_db[user_id.id] = shopping_cart
    return shopping_cart
   