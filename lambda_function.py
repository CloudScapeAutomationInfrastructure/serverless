import json
import os
import pymysql
import sendgrid
from sendgrid.helpers.mail import Mail
from datetime import datetime, timedelta
import boto3
import base64
from botocore.exceptions import BotoCoreError, ClientError


kms_client = boto3.client('kms', region_name=os.getenv('AWS_REGION'))


RDS_HOST = os.getenv('DB_HOST')
RDS_USER_ENCRYPTED = os.getenv('DB_USER_ENCRYPTED')  
RDS_PASSWORD_ENCRYPTED = os.getenv('DB_PASSWORD_ENCRYPTED')  
RDS_DATABASE = os.getenv('DB_NAME')


FROM_EMAIL = os.getenv('FROM_EMAIL')
DOMAIN_NAME = os.getenv('DOMAIN_NAME')
SENDGRID_API_KEY_ENCRYPTED = os.getenv('SENDGRID_API_KEY_ENCRYPTED')  


KMS_KEY_ALIAS = os.getenv('KMS_KEY_ALIAS', 'alias/my-kms-key')


def decrypt_kms(encrypted_value):
    """Decrypts an encrypted value using AWS KMS."""
    try:
        encrypted_blob = base64.b64decode(encrypted_value)
        response = kms_client.decrypt(CiphertextBlob=encrypted_blob)
        plaintext_value = response['Plaintext'].decode('utf-8')
        print("Decrypted value using KMS.")
        return plaintext_value
    except (BotoCoreError, ClientError) as e:
        print(f"Error decrypting value: {e}")
        raise Exception("Decryption failed.")


def initialize_sensitive_configs():
    """Decrypt and initialize sensitive configuration values."""
    print("Initializing sensitive configurations using KMS.")
    global RDS_USER, RDS_PASSWORD, SENDGRID_API_KEY
    RDS_USER = decrypt_kms(RDS_USER_ENCRYPTED)
    RDS_PASSWORD = decrypt_kms(RDS_PASSWORD_ENCRYPTED)
    SENDGRID_API_KEY = decrypt_kms(SENDGRID_API_KEY_ENCRYPTED)


def generate_encrypted_verification_token(user_id):
    """Generates and encrypts a verification token using KMS."""
    expiration_time = datetime.utcnow() + timedelta(minutes=2)
    expiration_timestamp = int(expiration_time.timestamp())
    token = f"{user_id}-{expiration_timestamp}"
    try:
        response = kms_client.encrypt(
            KeyId=KMS_KEY_ALIAS,
            Plaintext=token.encode('utf-8')
        )
        encrypted_token = base64.b64encode(response['CiphertextBlob']).decode('utf-8')
        print("Encrypted token generated successfully.")
        return encrypted_token
    except (BotoCoreError, ClientError) as e:
        print(f"Error encrypting token: {e}")
        raise Exception("Token encryption failed.")


def decrypt_verification_token(encrypted_token):
    """Decrypts an encrypted verification token using KMS."""
    try:
        encrypted_blob = base64.b64decode(encrypted_token)
        response = kms_client.decrypt(CiphertextBlob=encrypted_blob)
        plaintext_token = response['Plaintext'].decode('utf-8')
        print("Decrypted token successfully.")
        return plaintext_token
    except (BotoCoreError, ClientError) as e:
        print(f"Error decrypting token: {e}")
        raise Exception("Token decryption failed.")


def lambda_handler(event, context):
    print("Lambda function triggered.")
    try:
        print("Received event:", json.dumps(event, indent=4))  

        
        initialize_sensitive_configs()

       
        for record in event['Records']:
            print("Processing record:", record)

            message = json.loads(record['Sns']['Message'])
            print("Parsed message:", message)

            user_email = message['email']
            user_id = message['user_id']
            first_name = message['first_name']
            last_name = message['last_name']

            print(f"User details - Email: {user_email}, ID: {user_id}, Name: {first_name} {last_name}")

            
            encrypted_token = generate_encrypted_verification_token(user_id)
            verification_link = f"http://{DOMAIN_NAME}/v1/verify?token={encrypted_token}"
            print(f"Generated verification link: {verification_link}")

            
            email_subject = "Verify Your Email Address"
            email_body = f"""
            Hello {first_name} {last_name},

            Please verify your email address by clicking the link below. This link will expire in 2 minutes:
            {verification_link}

            Thank you!
            """
            print(f"Sending email to {user_email} with subject '{email_subject}'")
            send_email(user_email, email_subject, email_body)

            
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


def store_email_details(user_id, email_type, email_subject, verification_link):
    print("Connecting to RDS database.")
    connection = None
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
    except pymysql.MySQLError as e:
        print(f"MySQL error: {e}")
        raise
    except Exception as e:
        print(f"Error inserting email tracking record: {e}")
        raise
    finally:
        if connection:
            connection.close()
            print("RDS connection closed.")
