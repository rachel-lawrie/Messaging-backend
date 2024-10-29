from flask import Flask, request, jsonify
from flask_login import LoginManager, login_user, login_required
from models import User
from db import mongo
from bson import ObjectId
from bson.errors import InvalidId
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from dotenv import load_dotenv
import os

# name is built-in variable in python that is used to check if the code is run from the main file or not
app = Flask(__name__)

# load environment variables
load_dotenv()

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

# Initialize Twilio client
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
client = Client(account_sid, auth_token)

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
    
# Create Group
@app.route('/groups', methods=['Post'])
def create_group():
    data = request.json
    try:
        result = mongo.db.groups.insert_one(data)
        return jsonify({"message": "Group created successfully", "id": str(result.inserted_id)}), 201
    except Exception as e:
        print("Error creating message:", str(e))
        return jsonify({"error": "Failed to create message"}), 500
    
# Get groups for specific user
@app.route('/groups', methods=['GET'])
def get_groups():
    try:
        # Retrieve the user_id from the query parameters
        user_id = request.args.get('user_id')

        if not user_id:
            return jsonify({"error": "Missing user_id parameter"}), 400
        
        # Query the database to get all messages for this specific user
        groups = mongo.db.groups.find({"userID": user_id})

        # Convert the cursor to a list of dictionaries to be returned as JSON
        groups_list = []
        for group in groups:
            group['_id'] = str(group['_id'])  # Convert ObjectId to string
            groups_list.append(group)

        # Return the list of messages
        return jsonify(groups_list), 200

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

# Update existing group
@app.route('/groups/<group_id>', methods=['PUT'])
def update_group(group_id):
    try:
        # Check if group_id is a valid ObjectId
        object_id = ObjectId(group_id)  # This will raise an InvalidId error if invalid
        print(f"Valid ObjectId: {object_id}")

        data = request.json
        result = mongo.db.groups.update_one({"_id": object_id}, {"$set": data})
        
        if result.matched_count:
            print("Group updated successfully")
            return jsonify({"message": "Group updated successfully"}), 200
        else:
            print("Group not found")
            return jsonify({"error": "Group not found"}), 404

    except InvalidId:
        print("Invalid ObjectId format")
        return jsonify({"error": "Invalid group ID format"}), 400

    except Exception as e:
        print("Error updating group:", str(e))
        return jsonify({"error": "Failed to update group"}), 500

    

# Create Message
@app.route('/messages', methods=['Post'])
def create_message():
    data = request.json
    try:
        result = mongo.db.messages.insert_one(data)
        return jsonify({"message": "Message created successfully", "id": str(result.inserted_id)}), 201
    except Exception as e:
        print("Error creating message:", str(e))
        return jsonify({"error": "Failed to create message"}), 500

# Update existing message
@app.route('/messages/<message_id>', methods=['PUT'])
def update_message(message_id):
    try:
        # Check if message_id is a valid ObjectId
        object_id = ObjectId(message_id)  # This will raise an InvalidId error if invalid
        print(f"Valid ObjectId: {object_id}")

        data = request.json
        result = mongo.db.messages.update_one({"_id": object_id}, {"$set": data})
        
        if result.matched_count:
            print("Message updated successfully")
            return jsonify({"message": "Message updated successfully"}), 200
        else:
            print("Message not found")
            return jsonify({"error": "Message not found"}), 404

    except InvalidId:
        print("Invalid ObjectId format")
        return jsonify({"error": "Invalid message ID format"}), 400

    except Exception as e:
        print("Error updating message:", str(e))
        return jsonify({"error": "Failed to update message"}), 500

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

# Send message
@app.route('/send-messages', methods=['POST'])
def send_messages():
    try:
        data = request.json
        recipients = data.get('recipients', [])
        message_content = data.get('message', '')
        
        success_count = 0
        failed_recipients = []
        
        for recipient in recipients:
            try:
                # Send message via Twilio
                message = client.messages.create(
                    body=message_content,
                    from_=twilio_phone,
                    to=recipient['phoneNumber']
                )
                success_count += 1
            except TwilioRestException as e:
                failed_recipients.append({
                    'phoneNumber': recipient['phoneNumber'],
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'successCount': success_count,
            'failedRecipients': failed_recipients
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)