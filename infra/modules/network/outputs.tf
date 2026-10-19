output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = aws_subnet.public[*].id
}

output "trainer_security_group_id" {
  description = "Security Group ID for training EC2 instances"
  value       = aws_security_group.trainer.id
}
