# To avoid circular dependencies in other files made this its own file
from flask_pymongo import PyMongo

mongo = PyMongo()
