from flask_login import UserMixin
from db import mongo
from bson import ObjectId
import bcrypt

class User(UserMixin):
    def __init__(self, user_id, username, email, password):
        self.id = user_id  # This needs to be a string
        self.username = username
        self.email = email
        self.password = password  # In production, this should be hashed!

    @staticmethod
    def hash_password(password):
        # Convert the password to bytes and hash it
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password_bytes, salt)
    
    def check_password(self, password):
        # Check if password matches hash
        return bcrypt.checkpw(password.encode('utf-8'), self.password)
    

    @staticmethod
    def create_user(username, password, email):
        # Hash the password before storing
        password_hash = User.hash_password(password)
        user_data = {
            "username": username,
            "password": password_hash,
            "email": email
        }
        # Insert into MongoDB
        result = mongo.db.users.insert_one(user_data)
        return User(str(result.inserted_id), username, email, password_hash)
    

    @staticmethod
    def find_by_username(username):
        """Retrieve user from MongoDB by username."""
        user_data = mongo.db.users.find_one({"username": username})
        if user_data:
            return User(
            str(user_data["_id"]), 
            user_data["username"], 
            user_data["email"],
            user_data["password"]
        )
        return None
    
    @staticmethod
    def find_by_email(email):
        """Retrieve user from MongoDB by email."""
        user_data = mongo.db.users.find_one({"email": email})
        if user_data:
            return User(
            str(user_data["_id"]), 
            user_data["username"], 
            user_data["email"],
            user_data["password"]
        )
        return None
    
