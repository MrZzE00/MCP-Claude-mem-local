output "cloud_run_url" {
  value       = google_cloud_run_v2_service.mcp_service.uri
  description = "The direct, internal URL of the deployed Cloud Run service"
}

output "serverless_neg_id" {
  value       = google_compute_region_network_endpoint_group.serverless_neg.id
  description = "The ID of the Serverless Network Endpoint Group (NEG). Use this in the parent project's URL map if routing directly."
}

output "backend_service_id" {
  value       = google_compute_backend_service.mcp_backend.id
  description = "The ID of the Backend Service (with IAP enabled if configured). Connect this to your parent Load Balancer's URL map paths."
}

output "service_account_email" {
  value       = var.service_account_email
  description = "Email du Service Account (créé par la plateforme via cr_extra_projects.tf)"
}
