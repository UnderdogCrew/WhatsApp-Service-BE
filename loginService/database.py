from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId

class MongoDB:
    def __init__(self):
        self.client = MongoClient('your_mongodb_atlas_connection_string')
        self.db = self.client['your_database_name']
        self.users = self.db['users']

    def create_user(self, user_data):
        user_data['created_at'] = datetime.utcnow()
        user_data['updated_at'] = datetime.utcnow()
        result = self.users.insert_one(user_data)
        return str(result.inserted_id)

    def find_user_by_email(self, email):
        return self.users.find_one({'email': email})

    def find_user_by_id(self, user_id):
        return self.users.find_one({'_id': ObjectId(user_id)}) 