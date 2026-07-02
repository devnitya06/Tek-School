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

def _parse_base64_content_type(base64_string: str) -> tuple[str | None, str | None]:
    header = base64_string.split(",")[0]
    if header.startswith("data:") and ";" in header:
        content_type = header[5:header.index(";")]
        file_ext = content_type.split("/")[-1]
        if file_ext == "jpeg":
            file_ext = "jpg"
        return content_type, file_ext
    return None, None


def upload_base64_to_s3(base64_string: str, filename_prefix: str, ext="png"):
    try:
        file_bytes = base64.b64decode(base64_string.split(",")[-1])  # remove "data:image/png;base64,"

        file_obj = BytesIO(file_bytes)
        unique_filename = f"{filename_prefix}/{uuid4()}.{ext}"

        s3_client.upload_fileobj(
            file_obj,
            settings.S3_BUCKET_NAME,
            unique_filename,
            ExtraArgs={"ContentType": f"image/{ext}"}
        )
        file_url = f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{unique_filename}"
        return file_url

    except Exception as e:
        raise ValueError(f"S3 Upload failed: {e}")


def upload_base64_file_to_s3(
    base64_string: str,
    filename_prefix: str,
    max_size: int | None = None,
):
    content_type, ext = _parse_base64_content_type(base64_string)
    if not content_type or not ext:
        raise ValueError("Invalid base64 file format")

    ext = ext.lower()
    if ext == "jpeg":
        ext = "jpg"

    allowed_exts = {"png", "jpg", "jpeg", "gif", "pdf", "mp4", "mov", "webm", "mkv"}
    if ext not in allowed_exts:
        raise ValueError(f"Unsupported file type: {ext}")

    file_bytes = base64.b64decode(base64_string.split(",")[-1])
    if max_size is not None and len(file_bytes) > max_size:
        raise ValueError(f"File size exceeds maximum allowed size ({max_size // (1024 * 1024)}MB)")

    if ext in {"png", "jpg", "jpeg", "gif"}:
        return upload_base64_to_s3(base64_string, filename_prefix, ext=ext)

    file_obj = BytesIO(file_bytes)
    unique_filename = f"{filename_prefix}/{uuid4()}.{ext}"
    if ext == "pdf":
        content_type = "application/pdf"
    elif ext in {"mp4", "mov", "webm", "mkv"}:
        content_type = f"video/{ext}"
    else:
        content_type = content_type

    try:
        s3_client.upload_fileobj(
            file_obj,
            settings.S3_BUCKET_NAME,
            unique_filename,
            ExtraArgs={"ContentType": content_type},
        )
        return f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{unique_filename}"
    except Exception as e:
        raise ValueError(f"S3 Upload failed: {e}")


def upload_multipart_file_to_s3(
    upload_file,
    filename_prefix: str,
    max_size: int | None = None,
):
    file_extension = upload_file.filename.split(".")[-1].lower()
    if file_extension == "jpeg":
        file_extension = "jpg"

    allowed_extensions = {"jpg", "jpeg", "png", "gif", "pdf", "mp4", "mov", "webm", "mkv"}
    if file_extension not in allowed_extensions:
        raise ValueError(f"Unsupported file type: {file_extension}")

    if max_size is None:
        max_size = 50 * 1024 * 1024 if file_extension in {"mp4", "mov", "webm", "mkv"} else 5 * 1024 * 1024

    upload_file.file.seek(0, 2)
    file_size = upload_file.file.tell()
    upload_file.file.seek(0)
    if file_size > max_size:
        raise ValueError(
            f"File size exceeds maximum allowed size ({max_size // (1024 * 1024)}MB)"
        )

    content_type = upload_file.content_type
    if not content_type:
        if file_extension == "pdf":
            content_type = "application/pdf"
        elif file_extension in {"mp4", "mov", "webm", "mkv"}:
            content_type = f"video/{file_extension}"
        else:
            image_ext = "jpeg" if file_extension == "jpg" else file_extension
            content_type = f"image/{image_ext}"

    unique_filename = f"{filename_prefix}/{uuid4()}.{file_extension}"
    try:
        s3_client.upload_fileobj(
            upload_file.file,
            settings.S3_BUCKET_NAME,
            unique_filename,
            ExtraArgs={"ContentType": content_type},
        )
        return f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{unique_filename}"
    except Exception as e:
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

