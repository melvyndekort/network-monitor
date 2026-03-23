data "terraform_remote_state" "get_cookies" {
  backend = "s3"

  config = {
    bucket = "mdekort-tfstate-075673041815"
    key    = "get-cookies.tfstate"
    region = "eu-west-1"
  }
}

data "terraform_remote_state" "tf_cloudflare" {
  backend = "s3"

  config = {
    bucket = "mdekort-tfstate-075673041815"
    key    = "tf-cloudflare.tfstate"
    region = "eu-west-1"
  }
}
