resource "aws_s3_bucket" "file_storage" {
    bucket = "${var.project_name}-file-storage"
    force_destroy = false
}

resource "aws_s3_bucket_versioning" "file_storage_versioning" {
    bucket = aws_s3_bucket.file_storage.id
    versioning_configuration {
        status = "Enabled"
    }
}

# Encrypts objects in s3
resource "aws_s3_bucket_server_side_encryption_configuration" "file_storage_encryption" {
    bucket = aws_s3_bucket.file_storage.id

    rule {
        apply_server_side_encryption_by_default {
            sse_algorithm = "AES256"
        }
    }
}

resource "aws_s3_bucket_public_access_block" "file_storage_public_block" {
    bucket = aws_s3_bucket.file_storage.id

    block_public_acls = true
    block_public_policy = true
    ignore_public_acls = true
    restrict_public_buckets = true
}