from django.core.management.base import BaseCommand
from django.conf import settings
import boto3
from botocore.exceptions import ClientError


class Command(BaseCommand):
    help = 'Test S3 configuration and file access'

    def handle(self, *args, **options):
        self.stdout.write("Testing S3 Configuration...")
        
        # Print current settings
        self.stdout.write(f"FILE_STORAGE_TYPE: {settings.FILE_STORAGE_TYPE}")
        self.stdout.write(f"AWS_STORAGE_BUCKET_NAME: {settings.AWS_STORAGE_BUCKET_NAME}")
        self.stdout.write(f"AWS_S3_REGION_NAME: {settings.AWS_S3_REGION_NAME}")
        self.stdout.write(f"AWS_S3_PROJECT_PREFIX: {settings.AWS_S3_PROJECT_PREFIX}")
        
        # Create S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        
        # Test bucket access
        try:
            response = s3_client.list_objects_v2(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Prefix=settings.AWS_S3_PROJECT_PREFIX,
                MaxKeys=5
            )
            
            self.stdout.write(self.style.SUCCESS("✓ Successfully connected to S3 bucket"))
            
            if 'Contents' in response:
                self.stdout.write(f"\nFound {len(response['Contents'])} files:")
                for obj in response['Contents']:
                    self.stdout.write(f"  - {obj['Key']}")
            else:
                self.stdout.write("No files found in bucket")
                
        except ClientError as e:
            self.stdout.write(self.style.ERROR(f"✗ Error accessing S3: {e}"))
            
        # Test presigned URL generation
        test_key = f"{settings.AWS_S3_PROJECT_PREFIX}/test.txt"
        try:
            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                    'Key': test_key
                },
                ExpiresIn=300
            )
            self.stdout.write(f"\n✓ Successfully generated presigned URL")
            self.stdout.write(f"  URL (first 100 chars): {presigned_url[:100]}...")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Error generating presigned URL: {e}"))