# API Gateway (HTTP API v2) for REST API
#
# Authentication: AWS IAM
# All routes require IAM authorization. Requests must be signed with valid
# AWS credentials (SigV4) that have execute-api:Invoke permission.
#
# Usage examples:
#   # With awscurl (pip install awscurl)
#   awscurl --service execute-api --region eu-west-1 \
#     https://<api-id>.execute-api.eu-west-1.amazonaws.com/devices
#
#   # With AWS CLI (v2.22+)
#   aws curl https://<api-id>.execute-api.eu-west-1.amazonaws.com/devices \
#     --service execute-api --region eu-west-1
#
# IAM policy needed by the caller:
#   {
#     "Effect": "Allow",
#     "Action": "execute-api:Invoke",
#     "Resource": "arn:aws:execute-api:eu-west-1:<account>:<api-id>/*"
#   }

resource "aws_apigatewayv2_api" "network_monitor" {
  name          = "network-monitor"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.network_monitor.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_apigatewayv2_integration" "api_handler" {
  api_id                 = aws_apigatewayv2_api.network_monitor.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api_handler.invoke_arn
  payload_format_version = "2.0"
}

# Routes - all protected with IAM auth
resource "aws_apigatewayv2_route" "list_devices" {
  api_id             = aws_apigatewayv2_api.network_monitor.id
  route_key          = "GET /devices"
  target             = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
  authorization_type = "AWS_IAM"
}

resource "aws_apigatewayv2_route" "get_device" {
  api_id             = aws_apigatewayv2_api.network_monitor.id
  route_key          = "GET /devices/{mac}"
  target             = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
  authorization_type = "AWS_IAM"
}

resource "aws_apigatewayv2_route" "update_device" {
  api_id             = aws_apigatewayv2_api.network_monitor.id
  route_key          = "PUT /devices/{mac}"
  target             = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
  authorization_type = "AWS_IAM"
}

resource "aws_apigatewayv2_route" "delete_device" {
  api_id             = aws_apigatewayv2_api.network_monitor.id
  route_key          = "DELETE /devices/{mac}"
  target             = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
  authorization_type = "AWS_IAM"
}

resource "aws_apigatewayv2_route" "get_stats" {
  api_id             = aws_apigatewayv2_api.network_monitor.id
  route_key          = "GET /stats"
  target             = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
  authorization_type = "AWS_IAM"
}

resource "aws_apigatewayv2_route" "get_vlan_stats" {
  api_id             = aws_apigatewayv2_api.network_monitor.id
  route_key          = "GET /stats/vlan/{vlan_id}"
  target             = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
  authorization_type = "AWS_IAM"
}

resource "aws_apigatewayv2_route" "get_device_history" {
  api_id             = aws_apigatewayv2_api.network_monitor.id
  route_key          = "GET /devices/{mac}/history"
  target             = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
  authorization_type = "AWS_IAM"
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.network_monitor.execution_arn}/*/*"
}
