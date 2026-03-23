function getToken() {
  if (window.location.href.includes('#id_token=')) {
    var hash = window.location.hash.substring(1);
    var params = new URLSearchParams(hash);
    return params.get('id_token') || '';
  }
  return '';
}

function httpGetAsync(endpoint, callback, errorCallback) {
  var xmlHttp = new XMLHttpRequest();
  xmlHttp.onreadystatechange = function () {
    if (xmlHttp.readyState == 4) {
      if (xmlHttp.status == 200) {
        callback(xmlHttp.responseText);
      } else {
        errorCallback(xmlHttp.status, xmlHttp.statusText);
      }
    }
  }
  xmlHttp.open('GET', endpoint, true);
  xmlHttp.setRequestHeader('Content-Type', 'application/json');
  xmlHttp.send(null);
}

function setCookies(responseText) {
  try {
    var cookieObject = JSON.parse(responseText);
    var expiration = '; Expires=' + new Date(cookieObject.Expiration).toUTCString() + "; ";
    var staticInfo = '; Path=/; Secure';

    document.cookie = 'CloudFront-Policy=' + cookieObject.Policy + expiration + staticInfo;
    document.cookie = 'CloudFront-Signature=' + cookieObject.Signature + expiration + staticInfo;
    document.cookie = 'CloudFront-Key-Pair-Id=K3MOQECPWQIP8H' + expiration + staticInfo;

    window.location.href = '/';
  } catch (e) {
    alert("Authentication failed. Please try again.");
    window.location.href = '/';
  }
}

function handleError(status, statusText) {
  if (status === 403) {
    alert("Access denied. This domain is not authorized.");
  } else if (status === 401) {
    alert("Authentication failed. Please try again.");
  } else {
    alert("Authentication service unavailable. Please try again later.");
  }
  window.location.href = '/';
}

var token = getToken();
if (token) {
  var APIURL = 'https://api.mdekort.nl/cookies?id_token=' + encodeURIComponent(token);
  httpGetAsync(APIURL, setCookies, handleError);
} else {
  alert("No authentication token found. Please try logging in again.");
  window.location.href = '/';
}
