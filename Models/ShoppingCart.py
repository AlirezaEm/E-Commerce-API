from typing import List
from pydantic import BaseModel
from Models.Item import Item

class ShoppingCart(BaseModel):
    cart_id: str
    items: List[Item] = []
    state: str = "open"

    @classmethod
    def from_dynamodb_item(cls, dynamodb_item: dict):
        item_data = dynamodb_item.get('Item', {})
        cart_id = item_data.get('cart_id', {}).get('S', '')
        
        # Extracting items if available
        items_raw = item_data.get('items', {}).get('L', [])
        items_list = []
        for item in items_raw:
            item_data = item['M']
            items_list.append(Item(
                item_id=item_data['item_id']['S'],
                name=item_data['name']['S'],
                description=item_data.get('description', {}).get('S'),
                price=float(item_data['price']['N']),
                quantity=int(item_data['quantity']['N'])
            ))
        items = items_list

        # Extracting state if available
        state = item_data.get('state', {}).get('S', 'open')

        return cls(cart_id=cart_id, items=items, state=state)