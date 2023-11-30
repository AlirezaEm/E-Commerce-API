from pydantic import BaseModel

class DynamoModel(BaseModel):
    def model_to_dynamodb(self, model: BaseModel) -> dict:
        return {k: {'S': str(v)} for k, v in model.dict().items()}
