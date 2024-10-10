from flask import Flask, request, jsonify
from flask_pymongo import PyMongo
from flask_login import LoginManager
from models import User

# name is built-in variable in python that is used to check if the code is run from the main file or not
app = Flask(__name__)

# authentication
app.secret_key = 'supersecretkey'  # Set a secret key for session security

login_manager = LoginManager()
login_manager.init_app(app)

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.find_by_username(username)

# MongoDB configuration
app.config["MONGO_URI"] = "mongodb+srv://raedawnlaw:gP5QJVoabpXYJ7qJ@cluster0.es8bz.mongodb.net/messagingdb?retryWrites=true&w=majority&appName=Cluster0"
mongo = PyMongo(app)

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
        return jsonify({"message": "Login Successful"}), 200
    else:
        return jsonify({"message": "Invalid credentials"}), 401
    

# old code
# @app.route('/login', methods=['GET', 'POST'])
# def login():
#     if request.method == 'POST':
#         username = request.form['username']
#         password = request.form['password']
#         user = User.find_by_username(username)
#         if user and user.password == password:
#             login_user(user)
#             return redirect(url_for('home'))
#         else:
#             return "Invalid credentials"

#     return render_template('login.html')

# Home
@app.route('/home')
@login_required
def home():
    return "Home"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)

