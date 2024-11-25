from flask import Flask, request, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_cors import CORS
from models import User
from db import mongo
from bson import ObjectId
from bson.errors import InvalidId
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from dotenv import load_dotenv
import os
import bcrypt

# load environment variables
load_dotenv()

# name is built-in variable in python that is used to check if the code is run from the main file or not
app = Flask(__name__)
CORS(app, supports_credentials=True)



# authentication
app.config['JWT_SECRET_KEY'] = os.getenv('SECRET_KEY')
jwt = JWTManager(app)

# MongoDB configuration
app.config["MONGO_URI"] = "mongodb+srv://raedawnlaw:gP5QJVoabpXYJ7qJ@cluster0.es8bz.mongodb.net/messagingdb?retryWrites=true&w=majority&appName=Cluster0"
mongo.init_app(app)

# Initialize Twilio client using env
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
client = Client(account_sid, auth_token)
messagingServiceSid = os.getenv('MESSAGING_SERVICE_SID')

# Validate password
def validate_password(password):
    """
    Validate password strength
    Returns (bool, str) - (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    return True, ""

# Routes
# Register
@app.route('/register', methods=['POST'])
def register_user():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    # Check if all required fields are present
    if not username or not password or not email:
        return jsonify({"message": "Missing required fields"}), 400

    # Check if username already exists
    if User.find_by_username(username):
        return jsonify({"message": "Username already exists"}), 400

    # Check if email already exists
    if User.find_by_email(email):
        return jsonify({"message": "Email already exists"}), 400

    # Validate password
    is_valid, error_message = validate_password(password)
    if not is_valid:
        return jsonify({"message": error_message}), 400

    # Create new user with hashed password
    try:
        user = User.create_user(username, password, email)
        access_token = create_access_token(identity=str(user.id))
        return jsonify({
            "message": "User created successfully",
            "token": access_token,
            "user_id": str(user.id)
        }), 201
    except Exception as e:
        print(f"Error creating user: {e}")  # For debugging
        return jsonify({"message": "Error creating user"}), 500

# Login
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    user = User.find_by_username(username)
    if user and user.check_password(password):  # This uses the bcrypt check
        access_token = create_access_token(identity=str(user.id))
        return jsonify({
            "message": "Login Successful",
            "token": access_token,
            "user_id": str(user.id)
        }), 200
    return jsonify({"message": "Invalid username or password"}), 401

    
# Create Group
@app.route('/groups', methods=['Post'])
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
def delete_message(title):
    try:
        result = mongo.db.messages.delete_one({"title": title})
        
        if result.deleted_count == 1:
            return jsonify({"message": "Message deleted successfully"}), 200
        else:
            return jsonify({"error": "Message not found"}), 404

    except Exception as e:
        return jsonify({"error": "Failed to delete message"}), 500

# Send message (for when Twilio not working)
# testing twilio again
@app.route('/twilio', methods=['POST'])
@jwt_required()
def send_messages():

    data = request.json
    recipients = data.get('recipients', [])
    message_content = data.get('message', '')

    responses = []
    
    for recipient in recipients:
        try:
            message = client.messages.create(
                body=message_content,
                messaging_service_sid=messagingServiceSid,
                to=recipient['phoneNumber']
            )

            twilio_response = {
                "sid": message.sid,
                "status": message.status,
                "error_code": message.error_code,
                "error_message": message.error_message,
            }
            responses.append({"recipient": recipient["phoneNumber"], "twilio_response": twilio_response})
            print("Message sent to:", recipient["phoneNumber"])

        except Exception as e:
            print(f"Error for {recipient['phoneNumber']}: {e}")
            responses.append({"recipient": recipient["phoneNumber"], "error": str(e)})

    # Return the collected responses after processing all recipients
    return {"responses": responses}, 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)



# @app.route('/messages/<message_id>', methods=['PUT'])
# @jwt_required()
# def send_messages(message_id):
#     try:
#         # Check if message_id is a valid ObjectId
#         object_id = ObjectId(message_id)  # This will raise an InvalidId error if invalid
#         print(f"Valid ObjectId: {object_id}")

#         data = request.json
#         result = mongo.db.messages.update_one({"_id": object_id}, {"$set": data})
        
#         if result.matched_count:
#             print("Message sent!")
#             return jsonify({"message": "Message sent!"}), 200
#         else:
#             print("Message not sent")
#             return jsonify({"error": "Message not sent"}), 404

#     except InvalidId:
#         print("Invalid ObjectId format")
#         return jsonify({"error": "Invalid message ID format"}), 400

#     except Exception as e:
#         print("Error sending message:", str(e))
#         return jsonify({"error": "Failed to send message"}), 500

# For when messaging service is up:
# @app.route('/send-messages', methods=['POST'])
# @jwt_required()
# def send_messages():
#     try:
#         data = request.json
#         recipients = data.get('recipients', [])
#         message_content = data.get('message', '')
        
#         success_count = 0
#         failed_recipients = []
        
#         for recipient in recipients:
#             try:
#                 # Send message via Twilio
#                 message = client.messages.create(
#                     body=message_content,
#                     from_=twilio_phone,
#                     to='+15712143080') # recipient['phoneNumber'] <- replace phone number with this
                
#                 success_count += 1

#                 if message_id:
#                     object_id = ObjectId(message_id)  # Validate ObjectId
#                     print(f"Valid ObjectId: {object_id}")

#                     # Add/update the `timeSent` field for the message
#                     result = mongo.db.messages.update_one(
#                         {"_id": object_id},
#                         {"$set": {"timeSent": datetime.utcnow()}}
#                     )
#                     print(f"MongoDB Update Result: {result.modified_count}")

#             except TwilioRestException as e:
#                 failed_recipients.append({
#                     'phoneNumber': recipient['phoneNumber'],
#                     'error': str(e)
#                 })
        
#         return jsonify({
#             'success': True,
#             'successCount': success_count,
#             'failedRecipients': failed_recipients
#         })
    
#     except Exception as e:
#         return jsonify({
#             'success': False,
#             'error': str(e)
#         }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)