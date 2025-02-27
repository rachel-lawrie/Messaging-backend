Enter virtual environment:
```
Conda activate messagingapp_py312
```

Run the sever:
```
Python app.py
```

# Environment Variables
Create a `.env` file in the root directory with the following variables:
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number
MESSAGING_SERVICE_SID=your_messaging_service_sid
SECRET_KEY=your_secret_key
WEBHOOK_ADDRESS=your_webhook_address
MONGO_URI=your_mongodb_connection_string
