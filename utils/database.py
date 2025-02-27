import os
import sys
import django
current_path = os.path.abspath(os.getcwd())
base_path = os.path.dirname(current_path)  # This will give you /opt/whatsapp_service/WhatsApp-Service-BE
print(f"base_path: {base_path}")

# Set up Django environment
sys.path.append(base_path)  # Adjust this path accordingly
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'UnderdogCrew.settings')
django.setup()

from pymongo import MongoClient
from datetime import datetime
from UnderdogCrew import settings


class MongoDB:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDB, cls).__new__(cls)
            cls._instance.client = MongoClient(settings.MONGODB_ATLAS_CLUSTER_URI)
            cls._instance.db = cls._instance.client[settings.MONGODB_NAME]
        return cls._instance

    def get_collection(self, collection_name):
        return self.db[collection_name]

    def create_document(self, collection_name, document):
        collection = self.get_collection(collection_name)
        document['created_at'] = datetime.utcnow()
        document['updated_at'] = datetime.utcnow()
        result = collection.insert_one(document)
        return str(result.inserted_id)

    def find_document(self, collection_name, query):
        collection = self.get_collection(collection_name)
        return collection.find_one(query)

    def find_documents(self, collection_name, query, sort=None, skip=None, limit=None, projection=None):
        collection = self.get_collection(collection_name)
        cursor = collection.find(query, projection)
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)  # Apply sorting if provided
        return list(cursor)
    
    def update_document(self, collection_name, query, update_data):
        collection = self.get_collection(collection_name)
        update_data['updated_at'] = datetime.utcnow()
        return collection.update_one(query, {'$set': update_data})
