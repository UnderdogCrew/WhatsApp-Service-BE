import boto3
import os
from botocore.exceptions import ClientError
from UnderdogCrew import settings

class S3Helper:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )
        self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME

    def upload_file(self, file_obj, folder_name, file_extension,content_type=None):
        """Upload a file to S3 bucket"""
        try:
            # Generate unique filename
            file_extension = os.path.splitext(file_obj.name)[1]
            unique_filename = f"{folder_name}/{os.urandom(8).hex()}{file_extension}"

            # Upload to S3
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                unique_filename,
                ExtraArgs={'ACL': 'public-read',
                           'ContentType': content_type}
            )

            # Generate URL
            url = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{unique_filename}"
            return url

        except ClientError as e:
            print(f"Error uploading to S3: {str(e)}")
            return None 
    

    def upload_media_file(self, file_obj, folder_name, file_extension,content_type=None, file_name=None):
        """Upload a file to S3 bucket"""
        try:
            # Generate unique filename
            unique_filename = f"{folder_name}/{file_name}"

            # Upload to S3
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                unique_filename,
                ExtraArgs={'ACL': 'public-read',
                           'ContentType': content_type}
            )

            # Generate URL
            url = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{unique_filename}"
            return url

        except ClientError as e:
            print(f"Error uploading to S3: {str(e)}")
            return None 