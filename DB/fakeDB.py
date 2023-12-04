import os
import boto3
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')

load_dotenv(dotenv_path)

class Config:
    DB_REGION_NAME = os.getenv('AWS_DEFAULT_REGION')
    DB_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    DB_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')

def get_ddb_instance():
    return boto3.resource('dynamodb',
                          region_name=Config.DB_REGION_NAME,
                          aws_access_key_id=Config.DB_ACCESS_KEY_ID,
                          aws_secret_access_key=Config.DB_SECRET_ACCESS_KEY).Table('e-commerce')
