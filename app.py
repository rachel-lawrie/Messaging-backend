from flask import abort, Flask, request, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required
from flask_cors import CORS
from models import User
from db import mongo
from bson import ObjectId
from bson.errors import InvalidId
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from twilio.request_validator import RequestValidator
from dotenv import load_dotenv
from functools import wraps
import os
from werkzeug.middleware.proxy_fix import ProxyFix


# load environment variables
load_dotenv()

# name is built-in variable in python that is used to check if the code is run from the main file or not
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
CORS(app, supports_credentials=True)



# authentication
app.config['JWT_SECRET_KEY'] = os.getenv('SECRET_KEY')
jwt = JWTManager(app)

# MongoDB configuration
app.config["MONGO_URI"] = os.getenv('MONGO_URI')
mongo.init_app(app)

# Initialize Twilio client using env
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
client = Client(account_sid, auth_token)
messagingServiceSid = os.getenv('MESSAGING_SERVICE_SID')
webhook_address = os.getenv('WEBHOOK_ADDRESS')

# Validate Twilio request
def validate_twilio_request(f):
    """Validates that incoming requests genuinely originated from Twilio"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Create an instance of the RequestValidator class
        validator = RequestValidator(auth_token)
        print("token:", auth_token)
        print("Request URL:", request.url)
        print("Request Data:", request.form)
        print("Twilio Signature:", request.headers.get('X-TWILIO-SIGNATURE', ''))
        calculated_signature = validator.compute_signature(request.url, request.form)
        print("Calculated Signature:", calculated_signature)
        print("headers:", request.headers)
        print("data:", request.get_data())

        # Validate the request using its URL, POST data,
        # and X-TWILIO-SIGNATURE header
        request_valid = validator.validate(
            request.url,
            request.form,
            request.headers.get('X-TWILIO-SIGNATURE', ''))

        # Continue processing the request if it's valid, return a 403 error if
        # it's not
        if request_valid:
            return f(*args, **kwargs)
        else:
            return abort(403)
    return decorated_function

# Routes
# Register
@app.route('/register', methods=['POST'])
def register_user():
    try:
        data = request.json
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')

        # Check if all required fields are present
        if not username or not password or not email:
            return jsonify({"message": "Missing required fields"}), 400

        # Create new user - this will handle all other validations
        user = User.create_user(username, password, email)
        
        # Generate JWT token
        access_token = create_access_token(identity=str(user.id))
        
        return jsonify({
            "message": "User created successfully",
            "token": access_token,
            "user_id": str(user.id)
        }), 201
        
    except ValueError as e:
        # This will catch validation errors from User.create_user
        return jsonify({"message": str(e)}), 400
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

# Get single message by ID
@app.route('/messages/<message_id>', methods=['GET'])
@jwt_required()
def get_message(message_id):
    try:
        # Check if message_id is a valid ObjectId
        object_id = ObjectId(message_id)  # This will raise an InvalidId error if invalid
        
        # Query the database to get the specific message
        message = mongo.db.messages.find_one({"_id": object_id})
        
        if message:
            message['_id'] = str(message['_id'])  # Convert ObjectId to string
            return jsonify(message), 200
        else:
            return jsonify({"error": "Message not found"}), 404

    except InvalidId:
        return jsonify({"error": "Invalid message ID format"}), 400
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

# Send message
@app.route('/twilio', methods=['POST'])
@jwt_required()
def send_messages():

    data = request.json
    recipients = data.get('recipients', [])
    message_content = data.get('message', '')
    response_id = data.get('responseId', '')

    responses = []
    
    for recipient in recipients:
        try:
            message = client.messages.create(
                body= f"{message_content} Respond '{response_id}' to confirm your attendance.",
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

@app.route('/twilio-webhook', methods=['POST'])
@validate_twilio_request
def twilio_webhook():
    print("Twilio webhook received!")
    print("Request headers:", request.headers)
    print("Request data:", request.form)
    try:
        data = request.form
        print("Twilio webhook received:", data)

        # Extract the response body
        response_body = data.get('Body', '').strip()  # Remove extra spaces
        print("Response body:", response_body)

        from_number = data.get('From', '')
        print("From:", from_number)

        # Query the database to check for a matching responseId
        matching_message = mongo.db.messages.find_one({"responseId": response_body})

        if matching_message:

            print("Matching message found:", matching_message)
            # Process the matching message (e.g., update status, log response)
            matching_contact = next(
                (contact for contact in matching_message.get("to", []) if contact["phoneNumber"] == from_number),
                None
            )

            if matching_contact:
                print("Matching contact found:", matching_contact)

                # Use $addToSet to update or create 'responded_yes'
                update_result = mongo.db.messages.update_one(
                    {"_id": matching_message["_id"]},
                    {"$addToSet": {"responded_yes": matching_contact}}  # Add to array or create it if not present
                )
                return jsonify({"message": "Contact added to responded_yes."}), 200
        
            else:
                print("No matching contact found in the 'to' array.")
                return jsonify({"message": "No matching contact found."}), 404
        else:
            print("No matching message found for responseId:", response_body)
            return jsonify({"message": "No matching message found."}), 404

    except Exception as e:
        print("Error processing webhook:", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)