import json
import os
import pymysql
import sendgrid
from sendgrid.helpers.mail import Mail
from datetime import datetime, timedelta

# Initialize RDS configuration
RDS_HOST = os.getenv('DB_HOST')
RDS_USER = os.getenv('DB_USER')
RDS_PASSWORD = os.getenv('DB_PASSWORD')
RDS_DATABASE = os.getenv('DB_NAME')

# Email configuration
FROM_EMAIL = os.getenv('FROM_EMAIL')
DOMAIN_NAME = os.getenv('DOMAIN_NAME')
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')

# Lambda handler
def lambda_handler(event, context):
    print("Lambda function triggered.")
    try:
        print("Received event:", json.dumps(event, indent=4))  # Debug: Log the entire event
        
        # Parse SNS message
        for record in event['Records']:
            print("Processing record:", record)
            
            message = json.loads(record['Sns']['Message'])
            print("Parsed message:", message)  # Debug: Log parsed message
            
            user_email = message['email']
            user_id = message['user_id']
            first_name = message['first_name']
            last_name = message['last_name']
            
            print(f"User details - Email: {user_email}, ID: {user_id}, Name: {first_name} {last_name}")
            
            # Generate verification link
            verification_token = generate_verification_token(user_id)
            verification_link = f"http://{DOMAIN_NAME}/v1/verify?token={verification_token}"
            print(f"Generated verification link: {verification_link}")
            
            # Send verification email
            email_subject = "Verify Your Email Address"
            email_body = f"""
            Hello {first_name} {last_name},
            
            Please verify your email address by clicking the link below. This link will expire in 2 minutes:
            {verification_link}
            
            Thank you!
            """
            print(f"Sending email to {user_email} with subject '{email_subject}'")
            send_email(user_email, email_subject, email_body)
            
            # Store email details in the RDS database
            print("Storing email details in RDS.")
            store_email_details(user_id, "verification", email_subject, verification_link)

        print("Lambda function executed successfully.")
        return {
            "statusCode": 200,
            "body": json.dumps("Lambda function executed successfully!")
        }

    except Exception as e:
        print(f"Error occurred: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps(f"Internal Server Error: {str(e)}")
        }

# Generate a verification token
def generate_verification_token(user_id):
    print("Generating verification token.")
    expiration_time = datetime.utcnow() + timedelta(minutes=2)
    expiration_timestamp = int(expiration_time.timestamp())
    token = f"{user_id}-{expiration_timestamp}"
    print(f"Generated token: {token}")
    return token

# Send email using SendGrid
def send_email(to_email, subject, body):
    try:
        print(f"Initializing SendGrid client with API key: {SENDGRID_API_KEY[:5]}******")
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        email = Mail(
            from_email=FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            plain_text_content=body
        )
        response = sg.send(email)
        print(f"Email sent to {to_email} with status code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")
        raise

# Store email details in the RDS database
def store_email_details(user_id, email_type, email_subject, verification_link):
    print("Connecting to RDS database.")
    try:
        connection = pymysql.connect(
            host=RDS_HOST,
            user=RDS_USER,
            password=RDS_PASSWORD,
            database=RDS_DATABASE
        )
        print("Connected to RDS.")
        with connection.cursor() as cursor:
            query = """
            INSERT INTO email_tracking (user_id, email_type, email_subject, verification_link, expires_at, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            expiration_time = datetime.utcnow() + timedelta(minutes=2)
            print(f"Executing query: {query}")
            cursor.execute(query, (user_id, email_type, email_subject, verification_link, expiration_time, 'pending'))
            connection.commit()
            print(f"Email tracking record inserted for user_id: {user_id}")
    except Exception as e:
        print(f"Error inserting email tracking record: {e}")
        raise
    finally:
        if connection:
            connection.close()
            print("RDS connection closed.")
