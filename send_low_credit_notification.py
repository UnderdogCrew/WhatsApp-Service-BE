import os
import sys
import django
from datetime import datetime, timedelta
import traceback

current_path = os.path.abspath(os.getcwd())
base_path = os.path.dirname(current_path)  # This will give you /opt/whatsapp_service/WhatsApp-Service-BE
print(f"base_path: {base_path}")

# Set up Django environment
sys.path.append(base_path)  # Adjust this path accordingly
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'UnderdogCrew.settings')
django.setup()

from utils.database import MongoDB
from utils.twilio_otp import send_sms_message


def send_low_credit_notifications():
    """
    Send SMS notifications to users who have low credit balance (< 10 rupees)
    """
    try:
        db = MongoDB()
        
        # Fetch users with low credit (< 10 rupees) and active accounts with phone numbers
        query = {
            "default_credit": {"$lt": 20},
            "is_active": True,
            "business_number": {"$exists": True, "$ne": ""}
        }
        
        # Only get necessary fields for performance
        projection = {
            "_id": 1,
            "first_name": 1,
            "last_name": 1,
            "email": 1,
            "default_credit": 1,
            "business_number": 1,
            "last_credit_notification": 1
        }
        
        low_credit_users = list(db.find_documents('users', query, projection=projection))
        
        print(f"Found {len(low_credit_users)} users with low credit balance")
        
        current_time = datetime.now()
        notification_sent_count = 0
        
        for user in low_credit_users:
            try:
                user_id = str(user['_id'])
                credit_balance = user.get('default_credit', 0)
                phone_number = user.get('business_number', '')
                first_name = user.get('first_name', '')
                last_name = user.get('last_name', '')
                full_name = f"{first_name} {last_name}".strip()
                email = user.get('email', '')
                
                # Check if notification was sent in the last 23 hours to avoid spam
                # last_notification = user.get('last_credit_notification')
                # if last_notification:
                #     time_since_last_notification = current_time - last_notification
                #     if time_since_last_notification < timedelta(hours=23):
                #         print(f"Skipping user {email} - notification sent within last 24 hours")
                #         continue
                
                # Skip if phone number is not available
                if not phone_number:
                    print(f"Skipping user {email} - no phone number available")
                    continue
                
                # Determine message content and urgency based on credit level
                if credit_balance <= 0:
                    urgency = "URGENT"
                    message_body = f"🚨 URGENT: Hello {full_name or 'Valued Customer'}, your WapNeXus credit balance is EXHAUSTED (₹{credit_balance:.2f}). Your messaging service has been suspended. Please recharge immediately to continue sending messages. Support: support@wapnexus.com"
                elif credit_balance <= 10:
                    urgency = "HIGH"
                    message_body = f"⚠️ Hello {full_name or 'Valued Customer'}, your WapNeXus credit balance is very low: ₹{credit_balance:.2f}. You can send only a few more messages. Please recharge soon to avoid service interruption. Support: support@wapnexus.com"
                else:  # credit_balance < 10
                    urgency = "MEDIUM"
                    message_body = f"💡 Hello {full_name or 'Valued Customer'}, your WapNeXus credit balance is running low: ₹{credit_balance:.2f}. Consider recharging to ensure uninterrupted messaging service. Support: support@wapnexus.com"
                
                print(f"Sending {urgency} low credit SMS to {email} (₹{credit_balance:.2f})")

                # Send the SMS notification
                # Remove any +91 prefix if present (should be handled in DB, but ensure here)
                clean_phone_number = phone_number.lstrip('+') if phone_number.startswith('+91') else phone_number
                success, message_sid = send_sms_message(
                    to_number=clean_phone_number,
                    message_body=message_body
                )
                
                if success and message_sid:
                    # Update last notification timestamp
                    db.update_document(
                        'users',
                        {'_id': user['_id']},
                        {
                            'last_credit_notification': current_time,
                            'last_sms_sid': message_sid
                        }
                    )
                    notification_sent_count += 1
                    print(f"Successfully sent SMS to {email} (SID: {message_sid})")
                else:
                    print(f"Failed to send SMS to {email}")
                    
            except Exception as user_error:
                print(f"Error processing user {user.get('email', 'unknown')}: {str(user_error)}")
                continue
        
        print(f"Low credit SMS notification process completed. Sent {notification_sent_count} SMS messages.")
        
        # Log the activity
        db.create_document('notification_logs', {
            "type": "low_credit_sms_notification",
            "executed_at": current_time,
            "users_processed": len(low_credit_users),
            "sms_sent": notification_sent_count,
            "status": "completed"
        })
        
        return True

    except Exception as e:
        tb = traceback.extract_tb(sys.exc_info()[2])[-1]  # Get last traceback frame
        line_number = tb.lineno
        print(f"Error in low credit SMS notification process on line {line_number}: {str(e)}")
        
        # Log the error
        try:
            db = MongoDB()
            db.create_document('notification_logs', {
                "type": "low_credit_sms_notification",
                "executed_at": datetime.now(),
                "error": str(e),
                "line_number": line_number,
                "status": "failed"
            })
        except:
            pass
            
        return False


if __name__ == "__main__":
    print(f"Starting low credit SMS notification job at {datetime.now()}")
    
    # Send low credit SMS notifications
    success = send_low_credit_notifications()
    
    
    if success:
        print("Low credit SMS notification job completed successfully")
        sys.exit(0)
    else:
        print("Low credit SMS notification job failed")
        sys.exit(1) 