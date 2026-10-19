# ──────────────────────────────────────────────
# CloudFront Origin Access Control (OAC)
# ──────────────────────────────────────────────
resource "aws_cloudfront_origin_access_control" "oac" {
  name                              = "cloudtrain-${var.env}-web-oac"
  description                       = "Origin Access Control for CloudTrain Web Bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Managed policies IDs:
# CachingOptimized: 658327ea-f89d-4fab-a63d-7e88639e58f6
# SecurityHeadersPolicy: 67f7725c-6f97-4210-82d7-5512b31e9d03
locals {
  caching_optimized_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  security_headers_policy_id  = "67f7725c-6f97-4210-82d7-5512b31e9d03"
}

# ──────────────────────────────────────────────
# CloudFront Distribution (Edge SPA Delivery)
# ──────────────────────────────────────────────
resource "aws_cloudfront_distribution" "distribution" {
  origin {
    domain_name              = var.web_bucket_regional_domain_name
    origin_id                = "S3-WebOrigin"
    origin_access_control_id = aws_cloudfront_origin_access_control.oac.id
  }

  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  price_class         = "PriceClass_200"

  default_cache_behavior {
    target_origin_id       = "S3-WebOrigin"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id            = local.caching_optimized_policy_id
    response_headers_policy_id = local.security_headers_policy_id
  }

  # SPA Routing: Redirect 403/404 to /index.html (200 OK)
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name = "cloudtrain-${var.env}-cdn"
  }
}

# ──────────────────────────────────────────────
# Web Bucket Policy: CloudFront OAC Only
# ──────────────────────────────────────────────
resource "aws_s3_bucket_policy" "web_oac" {
  bucket = var.web_bucket_id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontOAC"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${var.web_bucket_arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.distribution.arn
          }
        }
      },
      {
        Sid       = "EnforceTLSRequestsOnly"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          var.web_bucket_arn,
          "${var.web_bucket_arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}

# ──────────────────────────────────────────────
# Dynamic config.json rendered directly into S3 Web Bucket
# ──────────────────────────────────────────────
resource "aws_s3_object" "config_json" {
  bucket        = var.web_bucket_id
  key           = "config.json"
  content_type  = "application/json"
  cache_control = "no-store, no-cache, must-revalidate"

  content = jsonencode({
    api_url             = var.api_endpoint
    region              = var.region
    user_pool_id        = var.user_pool_id
    user_pool_client_id = var.user_pool_client_id
  })
}
