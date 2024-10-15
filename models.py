from flask_login import UserMixin
from db import mongo

class User(UserMixin):
    def __init__(self, user_id, username, password):
        self.id = user_id
        self.username = username
        self.password = password

    @staticmethod
    def get(user_id):
        """Retrieve user from MongoDB by user_id."""
        user_data = mongo.db.users.find_one({"_id": user_id})
        if user_data:
            return User(str(user_data["_id"]), user_data["username"], user_data["password"])
        return None

    @staticmethod
    def find_by_username(username):
        """Retrieve user from MongoDB by username."""
        user_data = mongo.db.users.find_one({"username": username})
        if user_data:
            return User(str(user_data["_id"]), user_data["username"], user_data["password"])
        return None