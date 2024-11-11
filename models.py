from flask_login import UserMixin
from db import mongo
from bson import ObjectId

class User(UserMixin):
    def __init__(self, user_id, username, password):
        self.id = user_id  # This needs to be a string
        self.username = username
        self.password = password  # In production, this should be hashed!

    @staticmethod
    def get(user_id):
        """Retrieve user from MongoDB by user_id."""
        try:
            user_data = mongo.db.users.find_one({"_id": ObjectId(user_id)})
            if user_data:
                return User(str(user_data["_id"]), user_data["username"], user_data["password"])
        except:
            return None
        return None

    @staticmethod
    def find_by_username(username):
        """Retrieve user from MongoDB by username."""
        user_data = mongo.db.users.find_one({"username": username})
        if user_data:
            return User(str(user_data["_id"]), user_data["username"], user_data["password"])
        return None