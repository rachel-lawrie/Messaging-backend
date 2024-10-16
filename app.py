from flask import Flask, request, jsonify
from flask_login import LoginManager, login_user, login_required
from models import User
from db import mongo

# name is built-in variable in python that is used to check if the code is run from the main file or not
app = Flask(__name__)

# authentication
app.secret_key = 'supersecretkey'  # Set a secret key for session security

login_manager = LoginManager()
login_manager.init_app(app)

# User loader for Flask-Login - review this, is this being used anywhere?
@login_manager.user_loader
def load_user(user_id):
    return User.find_by_username(username)

# MongoDB configuration
app.config["MONGO_URI"] = "mongodb+srv://raedawnlaw:gP5QJVoabpXYJ7qJ@cluster0.es8bz.mongodb.net/messagingdb?retryWrites=true&w=majority&appName=Cluster0"
mongo.init_app(app)

# Routes
# Register
@app.route('/register', methods=['POST'])
def register_user():
    data = request.json
    mongo.db.users.insert_one(data)
    return jsonify({"message": "User registered successfully!"}), 201

# Login
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data['username']
    password = data['password']
    user = User.find_by_username(username)
    if user and user.password == password:
        login_user(user)
        user_id = str(user.id)

        return jsonify({"message": "Login Successful", "user_id": user_id}), 200
    else:
        return jsonify({"message": "Invalid username or password"}), 401
    
# Create/save Message
@app.route('/messages', methods=['Post'])
def save_message():
    data = request.json
    try:
        message_id = data.get('message_id')

        # Use the upsert option to insert a new entry if it doesn't exist, or update if it does
        mongo.db.messages.update_one(
            {"message_id": message_id},  # Query to check if the document exists
            {"$set": data},              # Update the document with the new data
            upsert=True                  # Create a new document if it doesn't exist
        )
        
        return jsonify({"message": "Message saved or updated successfully"}), 200

    except Exception as e:
        return jsonify({"error": "Failed to save or update message"}), 500

# Get messages for specific user
@app.route('/messages', methods=['GET'])
def get_messages():
    try:
        # Retrieve the user_id from the query parameters
        user_id = request.args.get('user_id')

        if not user_id:
            return jsonify({"error": "Missing user_id parameter"}), 400
        
        # Query the database to get all messages for this specific user
        messages = mongo.db.messages.find({"userID": user_id})

        # Convert the cursor to a list of dictionaries to be returned as JSON
        message_list = []
        for message in messages:
            message['_id'] = str(message['_id'])  # Convert ObjectId to string
            message_list.append(message)

        # Return the list of messages
        return jsonify(message_list), 200

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

# Delete Message
@app.route('/messages/<title>', methods=['DELETE'])
def delete_message(title):
    try:
        result = mongo.db.messages.delete_one({"title": title})
        
        if result.deleted_count == 1:
            return jsonify({"message": "Message deleted successfully"}), 200
        else:
            return jsonify({"error": "Message not found"}), 404

    except Exception as e:
        return jsonify({"error": "Failed to delete message"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
