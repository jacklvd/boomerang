output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "instance_public_ip" {
  value = aws_instance.app.public_ip
}

output "shell" {
  description = "Open a shell on the instance (no SSH key needed)."
  value       = "aws ssm start-session --target ${aws_instance.app.id} --region ${var.region}"
}
