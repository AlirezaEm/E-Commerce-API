from typing import Annotated
from fastapi import APIRouter, HTTPException, Header
from jose import JWTError, jwt
from DB.fakeDB import shopping_carts_db
from Models.ShoppingCart import ShoppingCart

router = APIRouter()

# POST /v1/orders : Create an empty shopping cart for the user
@router.post("/v1/orders", response_model=ShoppingCart)
async def create_shopping_cart(auth_token: Annotated[str, Header()]):
    try:
        payload = jwt.decode(auth_token, "secret", algorithms="HS256")
        user_id: str = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=400, detail="The provided token does not have user id, please try logging in again.")
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    if user_id in shopping_carts_db:
        raise HTTPException(status_code=400, detail="Shopping cart already exists for this user")
    shopping_cart = ShoppingCart(cart_id=user_id)
    shopping_carts_db[user_id] = shopping_cart
    return shopping_cart
   