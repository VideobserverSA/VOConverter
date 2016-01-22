import urllib.request
from urllib.request import Request
import urllib.parse
import urllib.error
import json
import threading
from easysettings import EasySettings

api_url = "http://api.staging.videobserver.com/"

# lets us try to send the minimum 5 megabytes at a time
part_size = 5 * 1024 * 1024

# just some global settings
settings = EasySettings("test.conf")


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


class UploadFile(threading.Thread):

    def __init__(self, s3client, bucket, file, key, progress_callback, resume_callback, name):

        super().__init__(name=name)

        self.s3client = s3client
        self.bucket = bucket
        self.file = file
        self.key = key

        # print(self.total_size)

        self.progress_callback = progress_callback
        self.resume_callback = resume_callback

        self.upload_id = ""
        self.current_part = 1

        # so that we can cancel the download
        self.canceled = False
        self.part_etag_list = []

    def run(self):

        # now we loop for all the parts? one meg at the time?
        f = open(self.file, "rb+")
        total = 0
        done = False

        if settings.get("complete", True) or settings.get("canceled", True):
            # lets do this with a multi part upload so we can cancel it?
            ret = self.s3client.create_multipart_upload(Bucket=self.bucket,
                                                        Key=self.key
                                                        )

            # grab the upload id to use in the following methods
            self.upload_id = ret["UploadId"]
        else:
            # read settings
            self.upload_id = settings.get("upload_id")
            self.current_part = settings.get("current_part")
            self.part_etag_list = settings.get("part_etag_list")

            # calc sent size
            sent_size = part_size * self.current_part
            f.seek(sent_size)
            self.resume_callback(sent_size)

            # we already sent x parts, so start at x+1
            self.current_part += 1

        while not done and not self.canceled:
            # read a chunk
            buffer = f.read(part_size)
            total += len(buffer)
            # if we read less than what we wanted it's the EOF
            if len(buffer) != part_size:
                done = True

            # now we upload the part
            part_upload_ret = self.s3client.upload_part(Bucket=self.bucket,
                                                        Key=self.key,
                                                        PartNumber=self.current_part,
                                                        UploadId=self.upload_id,
                                                        Body=buffer,
                                                        ContentLength=len(buffer)
                                                        )

            self.part_etag_list.append({'ETag': part_upload_ret["ETag"], 'PartNumber': self.current_part})
            self.progress_callback(len(buffer))

            settings.set("part_etag_list", self.part_etag_list)
            settings.set("current_part", self.current_part)
            settings.set("upload_id", self.upload_id)
            settings.set("complete", False)
            settings.save()

            self.current_part += 1

        if not self.canceled:
            # and now complete the upload
            parts_dict = {'Parts': self.part_etag_list}
            complete_ret = self.s3client.complete_multipart_upload(Bucket=self.bucket,
                                                                   Key=self.key,
                                                                   MultipartUpload=parts_dict,
                                                                   UploadId=self.upload_id
                                                                   )
            settings.setsave("complete", True)
        f.close()

    def send_callback(self, bytes_loaded):
        self.progress_callback(self, bytes_loaded)

    def cancel_upload(self):
        self.canceled = True
        settings.setsave("canceled", True)
        abort_ret = self.s3client.abort_multipart_upload(Bucket=self.bucket,
                                                         Key=self.key,
                                                         UploadId=self.upload_id
                                                         )
        # print(abort_ret)


