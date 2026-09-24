from flask import abort, Flask, request, jsonify
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
)
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from models import User
from db import mongo
from bson import ObjectId
from bson.errors import InvalidId
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from twilio.request_validator import RequestValidator
from dotenv import load_dotenv
from functools import wraps
from datetime import timedelta
import os
import secrets
from werkzeug.middleware.proxy_fix import ProxyFix


# load environment variables
load_dotenv()

# name is built-in variable in python that is used to check if the code is run from the main file or not
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
CORS(app, supports_credentials=True)



# authentication
app.config['JWT_SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)
jwt = JWTManager(app)

# Rate limiting (in-memory backend for this single-process app)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

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

MESSAGE_UPDATE_FIELDS = ("title", "message", "to", "limit", "timeSent")
GROUP_UPDATE_FIELDS = ("groupName", "members")


def allowlisted_fields(data, allowed):
    """Build a dict of only allowlisted keys present in data."""
    if not data:
        return {}
    return {key: data[key] for key in allowed if key in data}


def expand_allowed_phones(to_list):
    """Expand a message's `to` list into a set of phone numbers (groups have members)."""
    phones = set()
    for entry in to_list or []:
        members = entry.get("members")
        if members is not None:
            for member in members:
                phone = member.get("phoneNumber")
                if phone:
                    phones.add(phone)
        else:
            phone = entry.get("phoneNumber")
            if phone:
                phones.add(phone)
    return phones


# Validate Twilio request
def validate_twilio_request(f):
    """Validates that incoming requests genuinely originated from Twilio"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Create an instance of the RequestValidator class
        validator = RequestValidator(auth_token)

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
@limiter.limit("5 per minute")
def register_user():
    try:
        data = request.json
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        first_name = data.get('firstName')
        last_name = data.get('lastName')

        # Check if all required fields are present
        if not username or not password or not email or not first_name or not last_name:
            return jsonify({"message": "Missing required fields"}), 400

        # Create new user - this will handle all other validations
        user = User.create_user(username, password, email, first_name, last_name)
        
        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))
        
        return jsonify({
            "message": "User created successfully",
            "token": access_token,
            "refresh_token": refresh_token,
            "user_id": str(user.id)
        }), 201
        
    except ValueError as e:
        # This will catch validation errors from User.create_user
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Error creating user"}), 500

# Login
@app.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    user = User.find_by_username(username)
    if user and user.check_password(password):  # This uses the bcrypt check
        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))
        return jsonify({
            "message": "Login Successful",
            "token": access_token,
            "refresh_token": refresh_token,
            "user_id": str(user.id)
        }), 200
    return jsonify({"message": "Invalid username or password"}), 401


@app.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    access_token = create_access_token(identity=identity)
    return jsonify({"token": access_token}), 200

    
# Create Group
@app.route('/groups', methods=['Post'])
@jwt_required()
def create_group():
    data = dict(request.json or {})
    allowed = allowlisted_fields(data, GROUP_UPDATE_FIELDS)
    if not allowed:
        return jsonify({"error": "No valid fields provided"}), 400
    allowed["userID"] = get_jwt_identity()
    try:
        result = mongo.db.groups.insert_one(allowed)
        return jsonify({"message": "Group created successfully", "id": str(result.inserted_id)}), 201
    except Exception as e:
        return jsonify({"error": "Failed to create message"}), 500
    
# Get groups for specific user
@app.route('/groups', methods=['GET'])
@jwt_required()
def get_groups():
    try:
        user_id = get_jwt_identity()

        # Query the database to get all groups for the authenticated user
        groups = mongo.db.groups.find({"userID": user_id})

        # Convert the cursor to a list of dictionaries to be returned as JSON
        groups_list = []
        for group in groups:
            group['_id'] = str(group['_id'])  # Convert ObjectId to string
            groups_list.append(group)

        # Return the list of groups
        return jsonify(groups_list), 200

    except Exception as e:
        return jsonify({"error": "An error occurred"}), 500

# Update existing group
@app.route('/groups/<group_id>', methods=['PUT'])
@jwt_required()
def update_group(group_id):
    try:
        # Check if group_id is a valid ObjectId
        object_id = ObjectId(group_id)  # This will raise an InvalidId error if invalid

        data = request.json
        allowed = allowlisted_fields(data, GROUP_UPDATE_FIELDS)
        if not allowed:
            return jsonify({"error": "No valid fields provided"}), 400

        user_id = get_jwt_identity()
        result = mongo.db.groups.update_one(
            {"_id": object_id, "userID": user_id},
            {"$set": allowed},
        )
        
        if result.matched_count:
            return jsonify({"message": "Group updated successfully"}), 200
        else:
            return jsonify({"error": "Group not found"}), 404

    except InvalidId:
        return jsonify({"error": "Invalid group ID format"}), 400

    except Exception as e:
        return jsonify({"error": "Failed to update group"}), 500

# Delete Group
@app.route('/groups/<group_id>', methods=['DELETE'])
@jwt_required()
def delete_group(group_id):
    try:
        # Check if group_id is a valid ObjectId
        object_id = ObjectId(group_id)  # This will raise an InvalidId error if invalid

        user_id = get_jwt_identity()
        result = mongo.db.groups.delete_one({"_id": object_id, "userID": user_id})

        if result.deleted_count:
            return jsonify({"message": "Group deleted successfully"}), 200
        else:
            return jsonify({"error": "Group not found"}), 404

    except InvalidId:
        return jsonify({"error": "Invalid group ID format"}), 400

    except Exception as e:
        return jsonify({"error": "Failed to delete group"}), 500

# Create Message
@app.route('/messages', methods=['Post'])
@jwt_required()
def create_message():
    data = dict(request.json or {})
    allowed = allowlisted_fields(data, MESSAGE_UPDATE_FIELDS)
    if not allowed:
        return jsonify({"error": "No valid fields provided"}), 400
    allowed["userID"] = get_jwt_identity()
    try:
        result = mongo.db.messages.insert_one(allowed)
        return jsonify({"message": "Message created successfully", "id": str(result.inserted_id)}), 201
    except Exception as e:
        return jsonify({"error": "Failed to create message"}), 500



# Update existing message
@app.route('/messages/<message_id>', methods=['PUT'])
@jwt_required()
def update_message(message_id):
    try:
        # Check if message_id is a valid ObjectId
        object_id = ObjectId(message_id)  # This will raise an InvalidId error if invalid

        data = request.json
        allowed = allowlisted_fields(data, MESSAGE_UPDATE_FIELDS)
        if not allowed:
            return jsonify({"error": "No valid fields provided"}), 400

        user_id = get_jwt_identity()
        result = mongo.db.messages.update_one(
            {"_id": object_id, "userID": user_id},
            {"$set": allowed},
        )
        
        if result.matched_count:
            return jsonify({"message": "Message updated successfully"}), 200
        else:
            return jsonify({"error": "Message not found"}), 404

    except InvalidId:
        return jsonify({"error": "Invalid message ID format"}), 400

    except Exception as e:
        return jsonify({"error": "Failed to update message"}), 500

# Get messages for specific user
@app.route('/messages', methods=['GET'])
@jwt_required()
def get_messages():
    try:
        user_id = get_jwt_identity()

        # Query the database to get all messages for the authenticated user
        messages = mongo.db.messages.find({"userID": user_id})

        # Convert the cursor to a list of dictionaries to be returned as JSON
        message_list = []
        for message in messages:
            message['_id'] = str(message['_id'])  # Convert ObjectId to string
            message_list.append(message)

        # Return the list of messages
        return jsonify(message_list), 200

    except Exception as e:
        return jsonify({"error": "An error occurred"}), 500

# Get single message by ID
@app.route('/messages/<message_id>', methods=['GET'])
@jwt_required()
def get_message(message_id):
    try:
        # Check if message_id is a valid ObjectId
        object_id = ObjectId(message_id)  # This will raise an InvalidId error if invalid
        user_id = get_jwt_identity()

        # Query the database to get the specific message owned by this user
        message = mongo.db.messages.find_one({"_id": object_id, "userID": user_id})
        
        if message:
            message['_id'] = str(message['_id'])  # Convert ObjectId to string
            return jsonify(message), 200
        else:
            return jsonify({"error": "Message not found"}), 404

    except InvalidId:
        return jsonify({"error": "Invalid message ID format"}), 400
    except Exception as e:
        return jsonify({"error": "An error occurred"}), 500

# Delete message by id (scoped to the requesting user)
@app.route('/messages/<message_id>', methods=['DELETE'])
@jwt_required()
def delete_message(message_id):
    try:
        # Check if message_id is a valid ObjectId
        object_id = ObjectId(message_id)  # This will raise an InvalidId error if invalid

        # Only delete the message if it belongs to the user in the JWT, so one user
        # can't delete another user's message. Identity is str(user.id), matching userID.
        user_id = get_jwt_identity()
        result = mongo.db.messages.delete_one({"_id": object_id, "userID": user_id})

        if result.deleted_count == 1:
            return jsonify({"message": "Message deleted successfully"}), 200
        else:
            return jsonify({"error": "Message not found"}), 404

    except InvalidId:
        return jsonify({"error": "Invalid message ID format"}), 400
    except Exception as e:
        return jsonify({"error": "Failed to delete message"}), 500

# Send message
@app.route('/twilio', methods=['POST'])
@jwt_required()
@limiter.limit("10 per minute")
def send_messages():

    data = request.json or {}
    recipients = data.get('recipients', [])
    message_content = data.get('message', '')
    message_id = data.get('messageId', '')

    if not message_id:
        return jsonify({"error": "Missing messageId"}), 400

    try:
        object_id = ObjectId(message_id)
    except InvalidId:
        return jsonify({"error": "Invalid message ID format"}), 400

    user_id = get_jwt_identity()
    message_doc = mongo.db.messages.find_one({"_id": object_id, "userID": user_id})
    if not message_doc:
        return jsonify({"error": "Message not found"}), 404

    # Resolve the sender from the JWT identity (not client-supplied) so it can't be spoofed
    sender = User.find_by_id(user_id)
    sender_name = ""
    if sender:
        sender_name = f"{sender.first_name} {sender.last_name}".strip() or sender.username

    # Title and limit come from the owned saved message document
    title = message_doc.get("title", "")
    limit_text = ""
    limit_value = message_doc.get("limit")
    if limit_value:
        try:
            limit_num = int(limit_value)
            if limit_num > 0:
                limit_text = " There is 1 spot!" if limit_num == 1 else f" There are {limit_num} spots!"
        except (TypeError, ValueError):
            pass

    # RSVP code: generate and persist if the owned document has none; ignore client value
    response_id = message_doc.get("responseId")
    if not response_id:
        response_id = secrets.token_hex(4)
        mongo.db.messages.update_one(
            {"_id": object_id, "userID": user_id},
            {"$set": {"responseId": response_id}},
        )

    prefix = f"{sender_name} via cajAPP" if sender_name else "cajAPP"
    if title:
        prefix += f" - {title}"

    # Ensure the message content ends with punctuation before appending the RSVP sentence
    trimmed_content = message_content.rstrip()
    if trimmed_content and trimmed_content[-1] not in ".!?":
        trimmed_content += "."

    allowed_phones = expand_allowed_phones(message_doc.get("to"))
    responses = []

    for recipient in recipients:
        phone = recipient.get("phoneNumber")
        if not phone or phone not in allowed_phones:
            # Number not on the saved message — skip, do not send
            continue
        try:
            message = client.messages.create(
                body= f"{prefix}: {trimmed_content}{limit_text} Respond '{response_id}' to confirm your affirmative response/attendance.",
                messaging_service_sid=messagingServiceSid,
                to=phone
            )

            twilio_response = {
                "sid": message.sid,
                "status": message.status,
                "error_code": message.error_code,
                "error_message": message.error_message,
            }
            responses.append({"recipient": phone, "twilio_response": twilio_response})

        except Exception as e:
            responses.append({"recipient": phone, "error": "Failed to send"})

    # Return the collected responses after processing all recipients
    return {"responses": responses}, 200

@app.route('/twilio-webhook', methods=['POST'])
@validate_twilio_request
def twilio_webhook():
    try:
        data = request.form

        # Extract the response body
        response_body = data.get('Body', '').strip()  # Remove extra spaces

        from_number = data.get('From', '')

        # Query the database to check for a matching responseId
        matching_message = mongo.db.messages.find_one({"responseId": response_body})

        if matching_message:

            # Process the matching message (e.g., update status, log response)
            matching_contact = next(
                (contact for contact in matching_message.get("to", []) if contact["phoneNumber"] == from_number),
                None
            )

            if matching_contact:

                # Use $addToSet to update or create 'responded_yes'
                update_result = mongo.db.messages.update_one(
                    {"_id": matching_message["_id"]},
                    {"$addToSet": {"responded_yes": matching_contact}}  # Add to array or create it if not present
                )

                if update_result.modified_count:
                    updated_message = mongo.db.messages.find_one({"_id": matching_message["_id"]})
                    limit_value = updated_message.get("limit")
                    responded_yes = updated_message.get("responded_yes", [])

                    try:
                        limit_num = int(limit_value) if limit_value else None
                    except (TypeError, ValueError):
                        limit_num = None

                    if limit_num and limit_num > 0 and len(responded_yes) >= limit_num:
                        flag_result = mongo.db.messages.update_one(
                            {"_id": updated_message["_id"], "quotaMetNotified": {"$ne": True}},
                            {"$set": {"quotaMetNotified": True}}
                        )
                        if flag_result.modified_count:
                            responded_numbers = {c["phoneNumber"] for c in responded_yes}
                            remaining = [c for c in updated_message.get("to", []) if c.get("phoneNumber") not in responded_numbers]

                            owner = User.find_by_id(updated_message.get("userID"))
                            owner_name = ""
                            if owner:
                                owner_name = f"{owner.first_name} {owner.last_name}".strip() or owner.username

                            quota_prefix = f"{owner_name} via cajAPP" if owner_name else "cajAPP"
                            event_title = updated_message.get("title", "")
                            if event_title:
                                quota_prefix += f" - {event_title}"

                            for recipient in remaining:
                                try:
                                    client.messages.create(
                                        body=f"{quota_prefix} respondent quota has been met!",
                                        messaging_service_sid=messagingServiceSid,
                                        to=recipient["phoneNumber"]
                                    )
                                except Exception as e:
                                    pass

                return jsonify({"message": "Contact added to responded_yes."}), 200
        
            else:
                return jsonify({"message": "No matching contact found."}), 404
        else:
            return jsonify({"message": "No matching message found."}), 404

    except Exception as e:
        return jsonify({"error": "An error occurred"}), 500

if __name__ == '__main__':
    debug = os.getenv("FLASK_DEBUG") == "1"
    app.run(debug=debug, host='0.0.0.0', port=5001)
