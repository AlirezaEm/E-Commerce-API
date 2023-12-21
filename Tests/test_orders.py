import pytest
from jose import jwt 
from fastapi import HTTPException, status
from Routes.orders import get_current_user
from fastapi.testclient import TestClient
from moto import mock_dynamodb
import boto3
from main import app  

client = TestClient(app)

# get_current_user tests: (JWT/Auth test)
def generate_token(user_id, isAdmin=False, secret_key="test_secret_key"):
    payload = {"user_id": user_id, "isAdmin": isAdmin}
    return jwt.encode(payload, secret_key, algorithm="HS256")

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test_secret_key")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-2")

def test_valid_token(mock_env):
    user_id = "123"
    token = generate_token(user_id, True)
    assert get_current_user(token) == (user_id, True)

def test_invalid_token(mock_env):
    with pytest.raises(HTTPException) as exc_info:
        get_current_user("invalid_token")
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Could not validate credentials" in str(exc_info.value.detail)

def test_token_with_missing_user_id(mock_env):
    token = jwt.encode({}, "test_secret_key", algorithm="HS256")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid token" in str(exc_info.value.detail)

def test_token_with_no_admin_field(mock_env):
    user_id = "123"
    token = generate_token(user_id, secret_key="test_secret_key")
    assert get_current_user(token) == (user_id, False)

def test_jwt_error(mock_env, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "wrong_secret_key")
    token = generate_token("123", True)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Could not validate credentials" in str(exc_info.value.detail)

#-----------------------------------------------------------------------------------------------------------------------------
# Mock DynamoDB setup
@mock_dynamodb
def dynamodb_setup():
    ddb = boto3.resource('dynamodb', region_name='ap-southeast-2')
    ddb.create_table(
        TableName='e-commerce',
        KeySchema=[
            {
                'AttributeName': 'cart_id',
                'KeyType': 'HASH'
            }
        ],
        AttributeDefinitions=[
            {
                'AttributeName': 'cart_id',
                'AttributeType': 'S'
            },
            {
                'AttributeName': 'owner_id',
                'AttributeType': 'S'
            },
            {
                'AttributeName': 'state',
                'AttributeType': 'S'  
            }
        ],
        ProvisionedThroughput={
            'ReadCapacityUnits': 10,
            'WriteCapacityUnits': 10
        },
        GlobalSecondaryIndexes=[
            {
                'IndexName': 'owner_id-state-index',
                'KeySchema': [
                    {
                        'AttributeName': 'owner_id',
                        'KeyType': 'HASH'  
                    },
                    {
                        'AttributeName': 'state',
                        'KeyType': 'RANGE'  
                    }
                ],
                'Projection': {
                    'ProjectionType': 'ALL'  
                },
                'ProvisionedThroughput': {
                    'ReadCapacityUnits': 10,
                    'WriteCapacityUnits': 10
                }
            },
            {
                'IndexName': 'state-index',
                'KeySchema': [
                    {
                        'AttributeName': 'state',
                        'KeyType': 'HASH'  
                    }
                ],
                'Projection': {
                    'ProjectionType': 'ALL'
                },
                'ProvisionedThroughput': {
                    'ReadCapacityUnits': 10,
                    'WriteCapacityUnits': 10
                }
            }
        ]
    )
    return ddb.Table('e-commerce')

# Create shopping cart tests: (POST /v1/orders)
@mock_dynamodb
def test_create_valid_shopping_cart(mock_env):
    dynamodb_setup()
    response = client.post("/v1/orders", headers={"Auth-Token": generate_token('id5', True)})
    assert response.status_code == 200
    data = response.json()
    assert data['owner_id'] == "id5"
    assert 'cart_id' in data
    assert data['items'] == []
    assert data['state'] == "open"

@mock_dynamodb
def test_create_shopping_cart_invalid_token(mock_env):
    dynamodb_setup()
    response = client.post("/v1/orders", headers={"Auth-Token": "invalid"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}

@mock_dynamodb
def test_create_shopping_cart_DB_error(mock_env):
    dynamodb_setup().delete() # delete table to simulate DB error 
    response = client.post("/v1/orders", headers={"Auth-Token": generate_token('id10', True)})
    assert response.status_code == 500
 
#-----------------------------------------------------------------------------------------------------------------------------
# Delete shopping cart tests: (DELETE /v1/orders/{cart_id})
@mock_dynamodb
def test_delete_shopping_cart_valid(mock_env):
    ddb = dynamodb_setup()
    ddb.put_item(Item={'cart_id': '10', 'owner_id': 'id5', 'state': 'full'})
    response = client.delete("/v1/orders/10", headers={"Auth-Token": generate_token('id5', True)})
    assert ddb.get_item(Key={'cart_id': '10'}).get('Item') is None
    assert response.status_code == 200
    assert response.json() == {"detail": "Shopping cart deleted successfully"}

@mock_dynamodb
def test_delete_shopping_cart_not_found(mock_env):
    dynamodb_setup()
    response = client.delete("/v1/orders/10", headers={"Auth-Token": generate_token('id10', True)})
    assert response.status_code == 404
    assert response.json() == {"detail": "Shopping cart not found."}

@mock_dynamodb
def test_delete_shopping_cart_not_authorized(mock_env):
    ddb = dynamodb_setup()
    ddb.put_item(Item={'cart_id': '10', 'owner_id': 'id555', 'state': 'full'})
    response = client.delete("/v1/orders/10", headers={"Auth-Token": generate_token('id10', True)})
    assert response.status_code == 403
    assert response.json() == {"detail": "You are not authorized to delete this shopping cart."}

@mock_dynamodb
def test_delete_shopping_cart_DB_error(mock_env):
    dynamodb_setup().delete() # delete table to simulate DB error 
    response = client.delete("/v1/orders/10", headers={"Auth-Token": generate_token('id10', True)})
    assert response.status_code == 500

#-----------------------------------------------------------------------------------------------------------------------------
# Checkout an entire shopping cart that changes the state to PAID: (POST /v1/orders/uuid/checkout)
@mock_dynamodb
def test_checkout_shopping_cart_valid(mock_env):
    ddb = dynamodb_setup()
    ddb.put_item(Item={'cart_id': 'CartID100', 'owner_id': 'OwnerID100', 'state': 'OPEN'})
    response = client.post("/v1/orders/CartID100/checkout", headers={"Auth-Token": generate_token('OwnerID100')})
    assert response.status_code == 200
    data = response.json()
    assert data['state'] == "PAID"

@mock_dynamodb
def test_checkout_shopping_cart_not_found(mock_env):
    dynamodb_setup()
    response = client.post("/v1/orders/CartID100/checkout", headers={"Auth-Token": generate_token('OwnerID100')})
    assert response.status_code == 404
    assert response.json() == {"detail": "Shopping cart not found"}

@mock_dynamodb
def test_checkout_shopping_cart_not_authorized(mock_env):
    ddb = dynamodb_setup()
    ddb.put_item(Item={'cart_id': 'CartID100', 'owner_id': 'OwnerID100', 'state': 'OPEN'})
    response = client.post("/v1/orders/CartID100/checkout", headers={"Auth-Token": generate_token('OwnerID200')})
    assert response.status_code == 401
    assert response.json() == {"detail": "You are not authorized to checkout this shopping cart"}

@mock_dynamodb
def test_checkout_shopping_cart_already_paid(mock_env):
    ddb = dynamodb_setup()
    ddb.put_item(Item={'cart_id': 'CartID100', 'owner_id': 'OwnerID100', 'state': 'PAID'})
    response = client.post("/v1/orders/CartID100/checkout", headers={"Auth-Token": generate_token('OwnerID100')})
    assert response.status_code == 400
    assert response.json() == {"detail": "Shopping cart is already checked out"}

@mock_dynamodb
def test_checkout_shopping_cart_DB_error(mock_env):
    dynamodb_setup().delete() # delete table to simulate DB error 
    response = client.post("/v1/orders/CartID100/checkout", headers={"Auth-Token": generate_token('OwnerID100')})
    assert response.status_code == 500

#-----------------------------------------------------------------------------------------------------------------------------
# Add/remove an item to/from the cart: PATCH /v1/orders/uuid
@mock_dynamodb
def test_update_shopping_cart_valid(mock_env):
    ddb = dynamodb_setup()
    ddb.put_item(Item={'cart_id': 'CartID100', 'owner_id': 'OwnerID100', 'state': 'OPEN', 'items': [{'item_id': 'Old10', 'name':'Old', 'price': '1', 'quantity':'10'}]})
    response = client.patch("/v1/orders/CartID100", headers={"Auth-Token": generate_token('OwnerID100')}, json=[{'item_id': 'item10', 'name':'tv', 'price': '12500.52', 'quantity':'80'}, {'item_id': 'item20', 'name':'tv2', 'price': '12500.52', 'quantity':'80'}])
    assert response.status_code == 200
    data = response.json()
    assert len(data['items']) == 2
    assert data['items'][0]['item_id'] == "item10"
    assert data['items'][1]['name'] == "tv2"

@mock_dynamodb
def test_update_shopping_cart_not_found(mock_env):
    dynamodb_setup()
    response = client.patch("/v1/orders/CartID100", headers={"Auth-Token": generate_token('OwnerID100')}, json=[{'item_id': 'item10', 'name':'tv', 'price': '12500.52', 'quantity':'80'}, {'item_id': 'item20', 'name':'tv2', 'price': '12500.52', 'quantity':'80'}])
    assert response.status_code == 404
    assert response.json() == {"detail": "Shopping cart not found"}

@mock_dynamodb
def test_update_shopping_cart_not_authorized(mock_env):
    ddb = dynamodb_setup()
    Item = {'cart_id': 'CartID100', 'owner_id': 'OwnerID100', 'state': 'OPEN', 'items': [{'item_id': 'Old10', 'name':'Old', 'price': '1', 'quantity':'10'}]}
    ddb.put_item(Item = Item)
    response = client.patch("/v1/orders/CartID100", headers={"Auth-Token": generate_token('NotOwnerID')}, json=[{'item_id': 'item10', 'name':'tv', 'price': '12500.52', 'quantity':'80'}, {'item_id': 'item20', 'name':'tv2', 'price': '12500.52', 'quantity':'80'}])
    assert response.status_code == 401
    assert response.json() == {"detail": "You are not authorized to use this shopping cart"}
    assert ddb.get_item(Key={'cart_id': 'CartID100'}).get('Item') == Item

@mock_dynamodb
def test_update_shopping_cart_DB_error(mock_env):
    dynamodb_setup().delete() # delete table to simulate DB error 
    response = client.patch("/v1/orders/CartID100", headers={"Auth-Token": generate_token('OwnerID100')}, json=[{'item_id': 'XXXXXX', 'name':'tv', 'price': '12500.52', 'quantity':'80'}, {'item_id': 'XXXXXX', 'name':'tv2', 'price': '12500.52', 'quantity':'80'}])
    assert response.status_code == 500

#-----------------------------------------------------------------------------------------------------------------------------
# Get shopping cart based on valid user and/or state tests: (GET /v1/orders)
@mock_dynamodb
def test_get_orders_by_user_and_state_valid(mock_env):
    ddb = dynamodb_setup()
    ddb.put_item(Item={'cart_id': '10', 'owner_id': 'id5', 'state': 'SHIPPED', 'items':[ {'item_id': 'item10', 'name':'tv', 'price': '12500.52', 'quantity':'80'}, {'item_id': 'item20', 'name':'tv2', 'price': '12500.52', 'quantity':'80'} ]})
    # Valid with isAdmin = True
    response = client.get("/v1/orders?user=id5&state=SHIPPED", headers={"Auth-Token": generate_token('id10', True)}) 
    assert response.status_code == 200
    data = response.json()
    assert data[0]['items'][0]['item_id'] == 'item10'
    # Valid with owner_id == user and isAdmin = False
    ddb.put_item(Item={'cart_id': '10', 'owner_id': 'id10', 'state': 'SHIPPED', 'items':[ {'item_id': 'item10', 'name':'tv', 'price': '12500.52', 'quantity':'80'}, {'item_id': 'item20', 'name':'tv2', 'price': '12500.52', 'quantity':'80'} ]})
    response = client.get("/v1/orders?user=id10&state=SHIPPED", headers={"Auth-Token": generate_token('id10', False)})
    assert response.status_code == 200
    data = response.json()
    assert data[0]['items'][0]['item_id'] == 'item10'

# Get shopping cart based on invalid user and/or state tests: (GET /v1/orders)
@mock_dynamodb
def test_get_orders_by_user_and_state_invalid(mock_env):
    ddb = dynamodb_setup()
    ddb.put_item(Item={'cart_id': '10', 'owner_id': 'id5', 'state': 'SHIPPED', 'items':[ {'item_id': 'item10', 'name':'tv', 'price': '12500.52', 'quantity':'80'}, {'item_id': 'item20', 'name':'tv2', 'price': '12500.52', 'quantity':'80'} ]})
    # Invalid with isAdmin == False and owner_id != user
    response = client.get("/v1/orders?user=id5&state=SHIPPED", headers={"Auth-Token": generate_token('id10', False)}) 
    assert response.status_code == 401
    assert response.json() == {"detail": "You are not authorized to access this resource"}

@mock_dynamodb
def test_get_orders_by_user_and_state_DB_error(mock_env):
    dynamodb_setup().delete() # delete table to simulate DB error 
    response = client.get("/v1/orders?user=id5&state=SHIPPED", headers={"Auth-Token": generate_token('id10', True)})
    assert response.status_code == 500

# Get all orders of a user GET /v1/orders?user=uuid  
@mock_dynamodb
def test_get_orders_by_user_valid(mock_env):
    ddb = dynamodb_setup()
    ddb.put_item(Item={'cart_id': 'id1', 'owner_id': 'id100', 'state': 'SHIPPED', 'items':[ {'item_id': '123', 'name':'tv', 'price': '12500.52', 'quantity':'80'}, {'item_id': '456', 'name':'tv2', 'price': '12500.52', 'quantity':'80'} ]})
    ddb.put_item(Item={'cart_id': 'id2', 'owner_id': 'id100', 'state': 'SHIPPED', 'items':[ {'item_id': '2123', 'name':'tv', 'price': '12500.52', 'quantity':'80'}, {'item_id': '2456', 'name':'tv2', 'price': '12500.52', 'quantity':'80'} ]})
    # Valid with owner_id == user and isAdmin = False
    response = client.get("/v1/orders?user=id100", headers={"Auth-Token": generate_token('id100', False)})
    assert response.status_code == 200
    orders = response.json()
    assert len(orders) == 2
    assert orders[0]['items'][0]['item_id'] == '123'
    assert orders[1]['items'][1]['item_id'] == '2456'
    # Valid with isAdmin == True and owner_id != user
    response = client.get("/v1/orders?user=id100", headers={"Auth-Token": generate_token('notTheOwnerID', True)})
    assert response.status_code == 200
    orders = response.json()
    assert len(orders) == 2
    assert orders[0]['items'][0]['item_id'] == '123'
    assert orders[1]['items'][1]['item_id'] == '2456'

@mock_dynamodb
def test_get_orders_by_user_invalid(mock_env):
    # Invalid with isAdmin == False and owner_id != user
    response = client.get("/v1/orders?user=id100", headers={"Auth-Token": generate_token('notTheOwnerID', False)}) 
    assert response.status_code == 401
    assert response.json() == {"detail": "You are not authorized to access this resource"}

@mock_dynamodb
def test_get_orders_by_user_DB_error(mock_env):
    dynamodb_setup().delete() # delete table to simulate DB error
    response = client.get("/v1/orders?user=id100", headers={"Auth-Token": generate_token('id100', True)})
    assert response.status_code == 500

@mock_dynamodb
def test_get_orders_by_state_valid(mock_env):
    ddb = dynamodb_setup()
    ddb.put_item(Item={'cart_id': 'id1', 'owner_id': 'id100', 'state': 'PAID', 'items':[ {'item_id': '123', 'name':'tv', 'price': '12500.52', 'quantity':'80'}, {'item_id': '456', 'name':'tv2', 'price': '12500.52', 'quantity':'80'} ]})
    ddb.put_item(Item={'cart_id': 'id2', 'owner_id': 'id200', 'state': 'PAID', 'items':[ {'item_id': '2123', 'name':'tv', 'price': '12500.52', 'quantity':'80'}, {'item_id': '2456', 'name':'tv2', 'price': '12500.52', 'quantity':'80'} ]})
    response = client.get("/v1/orders?state=PAID", headers={"Auth-Token": generate_token('adminID', True)})
    assert response.status_code == 200
    orders = response.json()
    assert len(orders) == 2
    assert orders[0]['items'][0]['item_id'] == '123'
    assert orders[1]['items'][1]['item_id'] == '2456'

@mock_dynamodb
def test_get_orders_by_state_invalid(mock_env):
    ddb = dynamodb_setup()
    ddb.put_item(Item={'cart_id': 'id1', 'owner_id': 'id100', 'state': 'PAID', 'items':[ {'item_id': '123', 'name':'tv', 'price': '12500.52', 'quantity':'80'}, {'item_id': '456', 'name':'tv2', 'price': '12500.52', 'quantity':'80'} ]})
    ddb.put_item(Item={'cart_id': 'id2', 'owner_id': 'id200', 'state': 'PAID', 'items':[ {'item_id': '2123', 'name':'tv', 'price': '12500.52', 'quantity':'80'}, {'item_id': '2456', 'name':'tv2', 'price': '12500.52', 'quantity':'80'} ]})
    response = client.get("/v1/orders?state=PAID", headers={"Auth-Token": generate_token('normalUserID', False)})
    assert response.status_code == 401
    assert response.json() == {"detail": "You are not authorized to access this resource"}

@mock_dynamodb
def test_get_orders_by_state_DB_error(mock_env):
    dynamodb_setup().delete() # delete table to simulate DB error
    response = client.get("/v1/orders?state=PAID", headers={"Auth-Token": generate_token('adminID', True)})
    assert response.status_code == 500

@mock_dynamodb
def test_get_orders_bad_request(mock_env):
    dynamodb_setup()
    response = client.get("/v1/orders", headers={"Auth-Token": generate_token('adminID', True)})
    assert response.status_code == 400
    assert response.json() == {"detail": "Query parameter 'user' or 'state' is required."}