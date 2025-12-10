import boto3
from uuid import uuid4
import os
import base64
from io import BytesIO
from app.core.config import settings

s3_client = boto3.client(
    "s3",
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
)

def upload_base64_to_s3(base64_string: str, filename_prefix: str, ext="png"):
    print("🔹 upload_base64_to_s3 called")  # debug: function called
    try:
        file_bytes = base64.b64decode(base64_string.split(",")[-1])  # remove "data:image/png;base64,"
        print(f"🔹 File size in bytes: {len(file_bytes)}")  # debug: file size

        file_obj = BytesIO(file_bytes)
        unique_filename = f"{filename_prefix}/{uuid4()}.{ext}"
        print(f"🔹 Uploading file to S3 as: {unique_filename}")

        s3_client.upload_fileobj(
            file_obj,
            settings.S3_BUCKET_NAME,
            unique_filename,
            ExtraArgs={"ContentType": f"image/{ext}"}
        )
        file_url = f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{unique_filename}"
        print(f"🔹 Upload success, file URL: {file_url}")
        return file_url

    except Exception as e:
        print(f"❌ S3 Upload failed: {e}")
        raise ValueError(f"S3 Upload failed: {e}")


def upload_to_s3(file_data, filename_prefix: str):
    max_size = 5 * 1024 * 1024 
    file_data.file.seek(0, 2)
    file_size = file_data.file.tell()
    file_data.file.seek(0)

    if file_size > max_size:
        raise ValueError("File size exceeds maximum allowed size (5MB)")

    allowed_extensions = {'jpg', 'jpeg', 'png', 'gif'}
    file_extension = file_data.filename.split(".")[-1].lower()
    if file_extension not in allowed_extensions:
        raise ValueError(f"Invalid file type. Allowed types: {', '.join(allowed_extensions)}")

    unique_filename = f"{filename_prefix}/{uuid4()}.{file_extension}"

    try:
        s3_client.upload_fileobj(
            file_data.file,
            settings.S3_BUCKET_NAME,
            unique_filename,
            ExtraArgs={"ContentType": file_data.content_type}
        )
    except Exception as e:
        raise

    url = f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{unique_filename}"
    return url

