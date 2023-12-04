from typing import Annotated
from fastapi import APIRouter, HTTPException, Header
from jose import JWTError, jwt
from Models.ShoppingCart import ShoppingCart
from DB.fakeDB import get_ddb_instance

router = APIRouter()

ddb = get_ddb_instance()
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
    
    try:
        existing_item = ddb.get_item(Key={"cart_id": user_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    if existing_item.get("Item"):
        raise HTTPException(status_code=400, detail="Shopping cart already exists for the user")

    shopping_cart = ShoppingCart(cart_id=user_id)

    try:
        ddb.put_item(Item=shopping_cart.dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    return shopping_cart
   
# DELETE /v1/orders/uuid
@router.delete("/v1/orders/{uuid}")
def delete_shopping_cart(uuid: str):
    existing_item = ddb.get_item(Key={"cart_id": uuid})
    
    if not existing_item.get("Item"):
        raise HTTPException(status_code=404, detail="Shopping cart was not found for this user")
    
    try:
        ddb.delete_item(Key={"cart_id": uuid})
    except Exception as e: 
        raise HTTPException(status_code=500, detail=str(e))
    return None    
