from flask_login import UserMixin
from db import mongo
from bson import ObjectId
import bcrypt
import re
import html

class User(UserMixin):
    def __init__(self, user_id, username, email, password, first_name="", last_name=""):
        self.id = user_id
        self.username = username
        self.email = email
        self.password = password
        self.first_name = first_name
        self.last_name = last_name

    # Input validations
    # Ensure password is at least 8 characters long
    @staticmethod
    def validate_password(password):
        # Password strength validation
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        return True, "Password is valid"
    
    # Username validation
    @staticmethod
    def validate_username(username):
        """Validate username to prevent injection attacks"""
        # Check if username contains only allowed characters
        if not re.match(r'^[a-zA-Z0-9._-]{3,30}$', username):
            return False, "Username can only contain letters, numbers, dots, underscores, and hyphens"
        
        # Check for MongoDB operator injection attempts
        if any(op in username for op in ['$', '{', '}']):
            return False, "Username contains invalid characters"
        
        # Check uniqueness (case-insensitive)
        existing_user = mongo.db.users.find_one({"username": username.lower()})
        if existing_user:
            return False, "Username already exists"
        
        return True, "Username is valid"
    
    # Name validation
    @staticmethod
    def validate_name(name, field_label="Name"):
        """Validate a first/last name to prevent injection attacks"""
        if not name or not name.strip():
            return False, f"{field_label} is required"

        if not re.match(r"^[a-zA-Z\s'-]{1,50}$", name.strip()):
            return False, f"{field_label} can only contain letters, spaces, hyphens, and apostrophes"

        return True, f"{field_label} is valid"

    # Email validation
    @staticmethod
    def validate_email(email):
        """
        Validate email format and uniqueness
        Returns tuple (is_valid, error_message)
        """
        # Validate email format
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return False, "Invalid email format"
        
        # Check if email already exists
        if mongo.db.users.find_one({"email": email}):
            return False, "Email already registered"
            
        return True, "Email is valid"

    # Password hashing
    @staticmethod
    def hash_password(password):
        # Convert the password to bytes and hash it
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password_bytes, salt)

    def check_password(self, password):
        # Check if password matches hash
        return bcrypt.checkpw(password.encode('utf-8'), self.password)
    
    

    # Create user
    @staticmethod
    def create_user(username, password, email, first_name, last_name):
        # Validate username
        username_valid, username_msg = User.validate_username(username)
        if not username_valid:
            raise ValueError(username_msg)

        # Validate email
        email_valid, email_msg = User.validate_email(email)
        if not email_valid:
            raise ValueError(email_msg)

        # Validate password
        password_valid, password_msg = User.validate_password(password)
        if not password_valid:
            raise ValueError(password_msg)

        # Validate first and last name
        first_name_valid, first_name_msg = User.validate_name(first_name, "First name")
        if not first_name_valid:
            raise ValueError(first_name_msg)

        last_name_valid, last_name_msg = User.validate_name(last_name, "Last name")
        if not last_name_valid:
            raise ValueError(last_name_msg)

        # Hash the password
        password_hash = User.hash_password(password)

        # Create user document with inputs
        user_data = {
            "username": username.lower(),
            "password": password_hash,
            "email": email,
            "firstName": first_name.strip(),
            "lastName": last_name.strip()
        }

        # Insert into MongoDB
        try:
            result = mongo.db.users.insert_one(user_data)
            return User(str(result.inserted_id), username, email, password_hash, first_name.strip(), last_name.strip())
        except Exception as e:
            raise ValueError("Failed to create user account")
    
    # Find methods
    @staticmethod
    def find_by_username(username):
        """Retrieve user from MongoDB by username."""
        user_data = mongo.db.users.find_one({"username": username.lower()})
        if user_data:
            return User(
            str(user_data["_id"]),
            user_data["username"],
            user_data["email"],
            user_data["password"],
            user_data.get("firstName", ""),
            user_data.get("lastName", "")
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
            user_data["password"],
            user_data.get("firstName", ""),
            user_data.get("lastName", "")
        )
        return None

    @staticmethod
    def find_by_id(user_id):
        """Retrieve user from MongoDB by id."""
        try:
            user_data = mongo.db.users.find_one({"_id": ObjectId(user_id)})
        except Exception:
            return None

        if user_data:
            return User(
            str(user_data["_id"]),
            user_data["username"],
            user_data["email"],
            user_data["password"],
            user_data.get("firstName", ""),
            user_data.get("lastName", "")
        )
        return None
    