import urllib.request
from urllib.request import Request
import urllib.parse
import urllib.error
import json

api_url = "http://api.staging.videobserver.com/"


# get the token
def get_token(username, password):
    try:

        # compose the data
        data = {"user": username,
                "pass": password,
                "version": "10.0.100",
                "type": "VO_CONVERTER_APP"}
        post_data = urllib.parse.urlencode(data)
        binary_data = post_data.encode()

        with urllib.request.urlopen(url=api_url + "v3/auth/get_token.json", data=binary_data) as auth_request:
            # print(auth_request.status)
            response_json = json.loads(auth_request.read().decode('utf-8'))
            if response_json["code"] == 200:
                return response_json["code"], {"token": response_json["data"]["token"], "user_id": response_json["data"]["user_id"]}
            else:
                return response_json["code"], None

    except urllib.error.URLError as ue:
        print("ERROR AUTH", ue.reason)
        return None


# get the aws upload data
def get_aws_data(token):
    try:

        # compose the data
        data = {"timeout": 7200}
        post_data = urllib.parse.urlencode(data)
        binary_data = post_data.encode()

        aws_request = Request(url=api_url + "v3/upload/getuploadtoken.json", data=binary_data,
                              headers={"x-auth-token-vo": token})

        with urllib.request.urlopen(aws_request) as aws_response:
            response_json = json.loads(aws_response.read().decode('utf-8'))
            return response_json["data"]

    except urllib.error.URLError as ue:
        print("ERROR AWS", ue.reason)
        return None


# get the aws upload data
def confirm_upload(token, bucket, key, duration, size):
    try:

        # compose the data
        data = {"bucket": bucket,
                "key": key,
                "duration": duration,
                "size": size}
        post_data = urllib.parse.urlencode(data)
        binary_data = post_data.encode()

        aws_request = Request(url=api_url + "v3/upload/confirmupload.json", data=binary_data,
                              headers={"x-auth-token-vo": token})

        with urllib.request.urlopen(aws_request) as aws_response:
            response_json = json.loads(aws_response.read().decode('utf-8'))
            return response_json["data"]

    except urllib.error.URLError as ue:
        print("ERROR AWS", ue.reason)
        return None
