from typing import Annotated
from fastapi import APIRouter, HTTPException, Header
from jose import JWTError, jwt
from Models.Item import Item
from Models.ShoppingCart import ShoppingCart
from DB.fakeDB import get_ddb_instance
import uuid

router = APIRouter()
ddb = get_ddb_instance()

# POST /v1/orders : Create an empty shopping cart for the user
@router.post("/v1/orders", response_model=ShoppingCart)
async def create_shopping_cart(auth_token: Annotated[str, Header()]):
    try:
        payload = jwt.decode(auth_token, "secret", algorithms="HS256")
        user_id: str = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="The provided token does not have user id, please try logging in again.")
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

    shopping_cart = ShoppingCart(cart_id=str(uuid.uuid4()), owner_id=user_id)

    try:
        ddb.put_item(Item=shopping_cart.dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    return shopping_cart
   
# DELETE /v1/orders/uuid
@router.delete("/v1/orders/{uuid}")
def delete_shopping_cart(uuid: str, auth_token: Annotated[str, Header()]):
    try:
        payload = jwt.decode(auth_token, "secret", algorithms="HS256")
        user_id: str = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="The provided token does not have user id, please try logging in again.")
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    
    existing_item = ddb.get_item(Key={"cart_id": uuid})
    
    if not existing_item.get("Item"):
        raise HTTPException(status_code=404, detail="Shopping cart was not found for this user")
    
    if existing_item.get("Item").get("owner_id") != user_id:
        raise HTTPException(status_code=403, detail="You are not authorized to delete this shopping cart")
    
    try:
        ddb.delete_item(Key={"cart_id": uuid})
    except Exception as e: 
        raise HTTPException(status_code=500, detail=str(e))
    return None    

# POST /v1/orders/uuid/checkout : Checkout an entire shopping cart that changes the state to PAID and freezes it to go through shipment
@router.post("/v1/orders/{uuid}/checkout")
def checkout_shopping_cart(uuid: str, auth_token: Annotated[str, Header()]):
    try:
        payload = jwt.decode(auth_token, "secret", algorithms="HS256")
        user_id: str = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="The provided token does not have user id, please try logging in again.")
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
        
# PATCH /v1/orders/uuid : Add/remove an item to/from the cart
@router.patch("/v1/orders/{uuid}")
def update_shopping_cart(uuid: str, items: list[Item], auth_token: Annotated[str, Header()]):
    try:
        payload = jwt.decode(auth_token, "secret", algorithms="HS256")
        user_id: str = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="The provided token does not have user id, please try logging in again.")
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    
    try:
        existing_item = ddb.get_item(Key={"cart_id": uuid})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    if not existing_item.get("Item"):
        raise HTTPException(status_code=404, detail="Shopping cart was not found for this user")
    
    if existing_item.get("Item").get("owner_id") != user_id:
        raise HTTPException(status_code=403, detail="You are not authorized to checkout this shopping cart")
    
    if existing_item.get("Item").get("state") == "PAID":
        raise HTTPException(status_code=400, detail="Shopping cart is already checked out")

    # Additional logic for processing payment, billing, and freezing the cart for shipment can be added here.

    try:
        updated_item = ddb.update_item(Key={"cart_id": uuid},
                                        UpdateExpression="SET #state = :new_state",
                                        ExpressionAttributeNames={'#state': 'state'},
                                        ExpressionAttributeValues={':new_state': 'PAID'},
                                        ReturnValues='ALL_NEW'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    return updated_item.get("Attributes")
