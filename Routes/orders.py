from typing import Annotated
from fastapi import APIRouter, HTTPException, Header
from jose import JWTError, jwt
from Models.ShoppingCart import ShoppingCart
from DB.fakeDB import get_ddb_instance
from Models.DynamoModel import DynamoModel

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
    
    existing_item = ddb.get_item(TableName="e-commerce", Key={"cart_id": {"S": user_id}})
    if existing_item.get("Item"):
        raise HTTPException(status_code=400, detail="Shopping cart already exists for the user")

    shopping_cart = ShoppingCart(cart_id=user_id)
    item = DynamoModel().model_to_dynamodb(shopping_cart)
    ddb.put_item(TableName="e-commerce", Item=item)   
    

    return shopping_cart
   