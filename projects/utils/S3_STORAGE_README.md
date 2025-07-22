# S3 Storage Implementation for Projects

## Overview

This implementation moves PRD (Product Requirements Document) and Technical Implementation content from database storage to S3 (or local file storage), improving scalability and reducing database load.

## Architecture

### Storage Handler: `ProjectS3Storage`
Located in `projects/utils/s3_storage.py`, this class provides a unified interface for file storage that automatically switches between S3 and local storage based on your configuration.

### Key Features
- **Dual Storage Support**: Automatically uses S3 when configured, falls back to local file storage
- **JSON Format**: All files are stored as JSON with metadata
- **Backward Compatible**: Existing database content continues to work
- **Error Handling**: Graceful fallback to database content if S3 fails

## Configuration

### Environment Variables
```bash
# Storage type: 's3' or 'local' (default: 'local')
FILE_STORAGE_TYPE=s3

# S3 Configuration (required when FILE_STORAGE_TYPE=s3)
AWS_STORAGE_BUCKET_NAME=your-bucket-name
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_S3_REGION_NAME=us-east-1
AWS_S3_PROJECT_PREFIX=projects  # Optional, default: 'projects'
```

### Local Storage
When `FILE_STORAGE_TYPE=local`, files are stored in:
```
MEDIA_ROOT/projects/{project_id}/{file_type}/{filename}.json
```

### S3 Storage Structure
When using S3, files are organized as:
```
s3://your-bucket/projects/{project_id}/{file_type}/{filename}.json
```

## File Structure

### PRD Files
- Location: `{project_id}/prd/{prd_name}.json`
- Example: `123e4567-e89b-12d3-a456-426614174000/prd/main_prd.json`

### Implementation Files
- Location: `{project_id}/implementation/implementation_plan.json`
- Example: `123e4567-e89b-12d3-a456-426614174000/implementation/implementation_plan.json`

### JSON File Format
```json
{
  "content": "The actual PRD or implementation content...",
  "metadata": {
    "prd_id": 123,
    "prd_name": "Main PRD",
    "updated_by": "username"
  },
  "type": "prd"
}
```

## API Changes

### PRD API (`/api/projects/{project_id}/prd/`)
- **GET**: Loads content from S3/local storage, falls back to database if needed
- **POST**: Saves content to S3/local storage, stores file key in database
- **DELETE**: Removes file from S3/local storage and database record

### Implementation API (`/api/projects/{project_id}/implementation/`)
- **GET**: Loads content from S3/local storage, falls back to database if needed
- **POST**: Saves content to S3/local storage, stores file key in database
- **DELETE**: Removes file from S3/local storage and database record

## Database Changes

### New Fields Added
1. **ProjectPRD.s3_file_key**: Stores the S3/local file key for PRD content
2. **ProjectImplementation.s3_file_key**: Stores the S3/local file key for implementation content

### Migration
Run migration `0022_projectimplementation_s3_file_key_and_more.py` to add these fields.

## Usage Examples

### Saving a PRD
```python
from projects.utils.s3_storage import project_s3_storage

success, file_key, error = project_s3_storage.save_file(
    project_id="123e4567-e89b-12d3-a456-426614174000",
    file_type="prd",
    content="Your PRD content here...",
    file_name="main_prd",
    metadata={
        "prd_id": 123,
        "prd_name": "Main PRD",
        "updated_by": "john_doe"
    }
)
```

### Loading a PRD
```python
success, content, error = project_s3_storage.load_file(file_key)
if success:
    print(content)  # Your PRD content
```

### Listing Project Files
```python
files = project_s3_storage.list_project_files(
    project_id="123e4567-e89b-12d3-a456-426614174000",
    file_type="prd"  # Optional filter
)
```

## Migration Strategy

### For New Projects
- All content automatically saved to S3/local storage
- Database only stores file keys

### For Existing Projects
- Old content remains in database until updated
- On first update, content moves to S3/local storage
- System automatically checks both locations

## Error Handling

1. **S3 Connection Failures**: Falls back to database content
2. **Missing Files**: Returns empty content or database content
3. **Save Failures**: Returns error message, doesn't update database

## Performance Benefits

1. **Reduced Database Size**: Large text content moved to object storage
2. **Better Scalability**: S3 handles large files better than database
3. **Cost Efficiency**: Object storage is cheaper for large content
4. **Improved Backup**: Easier to backup/restore individual files

## Security Considerations

1. **S3 Access**: Use IAM roles with minimal required permissions
2. **Presigned URLs**: Generated for temporary access (1 hour default)
3. **File Organization**: Files organized by project for access control
4. **Metadata**: Tracks who updated files and when

## Troubleshooting

### Common Issues

1. **S3 Access Denied**
   - Check AWS credentials in environment variables
   - Verify S3 bucket permissions

2. **Files Not Found**
   - Check `s3_file_key` in database
   - Verify file exists in S3/local storage
   - System will fall back to database content

3. **Local Storage Issues**
   - Ensure `MEDIA_ROOT/projects` directory exists
   - Check file permissions

### Debug Logging
Enable logging to see storage operations:
```python
import logging
logging.getLogger('projects.utils.s3_storage').setLevel(logging.DEBUG)
```

## Future Enhancements

1. **Versioning**: Track file versions in S3
2. **Compression**: Compress large files before storage
3. **CDN Integration**: Serve files through CloudFront
4. **Batch Operations**: Upload/download multiple files efficiently
5. **Migration Tool**: Bulk migrate existing database content to S3