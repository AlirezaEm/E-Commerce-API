import os
from typing import Annotated, List
from fastapi import APIRouter, HTTPException, Header, status, Depends
from jose import JWTError, jwt
from Models.Item import Item
from Models.ShoppingCart import ShoppingCart
import uuid
from boto3.dynamodb.conditions import Key
import boto3
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()
def get_db_connection():
    ddb = boto3.resource('dynamodb').Table('e-commerce')
    return ddb

# Dependency for getting the current user
def get_current_user(auth_token: Annotated[str, Header()]) -> (str, bool):
    secret_key = os.environ.get("JWT_SECRET")
    try:
        payload = jwt.decode(auth_token, secret_key, algorithms=["HS256"])
        user_id = payload.get("user_id")
        isAdmin = payload.get("isAdmin", False)
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
        return user_id, isAdmin
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

# POST /v1/orders : Create an empty shopping cart for the user
@router.post("/v1/orders", response_model=ShoppingCart)
async def create_shopping_cart(user: tuple = Depends(get_current_user)):
    user_id, isAdmin = user
    cart_id = str(uuid.uuid4())
    shopping_cart = ShoppingCart(cart_id=cart_id, owner_id=user_id)
    
    ddb = get_db_connection()
    try:
        ddb.put_item(Item=shopping_cart.dict())
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    return shopping_cart
   
# DELETE /v1/orders/uuid
@router.delete("/v1/orders/{cart_id}", response_description="Shopping cart deleted successfully")
def delete_shopping_cart(cart_id: str, user: tuple = Depends(get_current_user)):
    user_id, isAdmin = user
    ddb = get_db_connection()
    try:    
        existing_item = ddb.get_item(Key={"cart_id": cart_id}).get("Item")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    if existing_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping cart not found.")
    
    if existing_item.get("owner_id") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not authorized to delete this shopping cart.")
    
    try:
        ddb.delete_item(Key={"cart_id": cart_id})
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    return {"detail": "Shopping cart deleted successfully"}

# POST /v1/orders/uuid/checkout : Checkout an entire shopping cart that changes the state to PAID and freezes it to go through shipment
@router.post("/v1/orders/{cart_id}/checkout", response_model=ShoppingCart)
def checkout_shopping_cart(cart_id: str, user: tuple = Depends(get_current_user)):
    user_id, isAdmin = user
    ddb = get_db_connection()
    try:
        existing_item = ddb.get_item(Key={"cart_id": cart_id}).get("Item")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
        
    if existing_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping cart not found")
    
    if existing_item.get("owner_id") != user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="You are not authorized to checkout this shopping cart")
    
    if existing_item.get("state") == "PAID":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shopping cart is already checked out")

    # Additional logic for processing payment, billing, and freezing the cart for shipment can be added here.

    try:
        updated_item = ddb.update_item(
            Key={"cart_id": cart_id},
            UpdateExpression="SET #state = :new_state",
            ExpressionAttributeNames={'#state': 'state'},
            ExpressionAttributeValues={':new_state': 'PAID'},
            ReturnValues='ALL_NEW'
        ).get("Attributes")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    return updated_item
        
# PATCH /v1/orders/uuid : Add/remove an item to/from the cart
@router.patch("/v1/orders/{cart_id}", response_model=ShoppingCart)
def update_shopping_cart(cart_id: str, items: List[Item], user: tuple = Depends(get_current_user)):
    user_id, isAdmin = user
    ddb = get_db_connection()
    try:
        existing_item = ddb.get_item(Key={"cart_id": cart_id}).get("Item")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
        
    if existing_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping cart not found")
    
    if existing_item.get("owner_id") != user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="You are not authorized to use this shopping cart")

    serialized_items = [item.dict() for item in items]
    try:
        updated_item = ddb.update_item(
            Key={"cart_id": cart_id},
            UpdateExpression="SET #items = :new_items",
            ExpressionAttributeNames={'#items': 'items'},
            ExpressionAttributeValues={":new_items": serialized_items},
            ReturnValues="ALL_NEW"
        ).get("Attributes")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    return updated_item

# Endpoint to get orders based on user and/or state
@router.get("/v1/orders")
def get_orders_by_user_and_state(userToken: tuple = Depends(get_current_user), state: str | None = None, user: str | None = None):
    user_id, isAdmin = userToken
    ddb = get_db_connection()
    #GET /v1/orders?user=uuid&state=SHIPPED|PAID|etc  Get all shipped orders for a user by state
    if user and state:
        if user_id != user and not isAdmin:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="You are not authorized to access this resource")
        try:
            filtered_orders = ddb.query(
                IndexName='owner_id-state-index', 
                KeyConditionExpression=Key('owner_id').eq(user) & Key('state').eq(state)
            ).get("Items")
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # GET /v1/orders?user=uuid  Get all orders of a user
    elif user:
        if user_id != user and not isAdmin:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="You are not authorized to access this resource")
        try:
            filtered_orders = ddb.query(
                IndexName='owner_id-state-index', 
                KeyConditionExpression=Key('owner_id').eq(user)
            ).get("Items")
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
        
    #GET /v1/orders?state=PAID  Get all “Paid” orders for ALL users
    elif state:
        if not isAdmin:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="You are not authorized to access this resource")
        try:
            filtered_orders = ddb.query(
                IndexName='state-index', 
                KeyConditionExpression=Key('state').eq(state)
            ).get("Items")
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query parameter 'user' or 'state' is required.")
    
    return filtered_orders
