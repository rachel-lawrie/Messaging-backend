from flask import Flask, request, jsonify
from flask_pymongo import PyMongo
# converts python object to JSON string
from bson.json_util import dumps

# name is built-in variable in python that is used to check if the code is run from the main file or not
app = Flask(__name__)

# MongoDB configuration
app.config["MONGO_URI"] = "mongodb+srv://raedawnlaw:gP5QJVoabpXYJ7qJ@cluster0.es8bz.mongodb.net/messagingdb?retryWrites=true&w=majority&appName=Cluster0"
mongo = PyMongo(app)

@app.route('/register', methods=['POST'])
def register_user():
    data = request.json
    mongo.db.users.insert_one(data)
    return jsonify({"message": "User registered successfully!"}), 201

if __name__ == '__main__':
    app.run(debug=True, port=5001)
