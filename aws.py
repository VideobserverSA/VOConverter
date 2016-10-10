import urllib.request
from datetime import time
from urllib.request import Request
import urllib.parse
import urllib.error
import json
import threading
from easysettings import EasySettings
import jsonpickle
import zlib
import os

api_url = "http://api.staging.videobserver.com/"

# lets us try to send the minimum 5 megabytes at a time
part_size = 5 * 1024 * 1024

os.makedirs(os.path.expanduser("~/VoConverter/"), exist_ok=True)
# just some global settings
settings = EasySettings(os.path.expanduser("~/VoConverter/uploads.conf"))

# boto3.set_stream_logger(name="boto3", level=logging.DEBUG)
# boto3.set_stream_logger(name="botocore", level=logging.DEBUG)
# boto3.set_stream_logger(name="s3", level=logging.DEBUG)


def print_mine(*args):
    pass
    # print(args)


class SavedUpload:

    def __init__(self):
        # info about file on disk
        self.file = ""
        self.size = ""
        self.checksum = ""
        # info about aws multipart upload
        self.upload_id = ""
        self.current_part = ""
        self.part_etag_list = []
        # upload status
        self.complete = False
        self.canceled = False
        self.date = time()


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
            # print_mine(auth_request.status)
            response_json = json.loads(auth_request.read().decode('utf-8'))
            if response_json["code"] == 200:
                return response_json["code"], {"token": response_json["data"]["token"], "user_id": response_json["data"]["user_id"]}
            else:
                return response_json["code"], None

    except urllib.error.URLError as ue:
        print_mine("ERROR AUTH", ue.reason)
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
        print_mine("ERROR AWS", ue.reason)
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
        print_mine("ERROR AWS", ue.reason)
        return None


class UploadFile(threading.Thread):

    def __init__(self, s3client, bucket, file, key, progress_callback, resume_callback, name):

        super().__init__(name=name)

        self.s3client = s3client
        self.bucket = bucket
        self.file = file
        self.key = key

        # print_mine(self.total_size)

        self.progress_callback = progress_callback
        self.resume_callback = resume_callback

        self.upload_id = ""
        self.current_part = 1

        # so that we can cancel the download
        self.canceled = False
        self.part_etag_list = []

        if settings.has_option("uploads"):
            self.current_uploads = jsonpickle.decode(settings.get("uploads"))
        else:
            self.current_uploads = {}

    def run(self):

        # now we loop for all the parts? one meg at the time?
        f = open(self.file, "rb+")
        total = 0
        done = False

        do_resume = False

        # grab the size and first bytes of the file
        test_fd = open(self.file, "rb")
        tes_buffer = test_fd.read(1024 * 10)
        test_fd.close()

        checksum = zlib.adler32(tes_buffer)
        size = os.stat(self.file).st_size

        # do we have an upload of this kind?
        if self.file in self.current_uploads:
            upload = self.current_uploads[self.file]
            if upload.checksum == checksum and upload.size == size\
               and not upload.complete and not upload.canceled:
                do_resume = True

        if not do_resume:
            # create an upload
            upload = SavedUpload()
            upload.file = self.file
            upload.checksum = checksum
            upload.size = size

            # lets do this with a multi part upload so we can cancel it?
            ret = self.s3client.create_multipart_upload(Bucket=self.bucket,
                                                        Key=self.key
                                                        )

            # grab the upload id to use in the following methods
            upload.upload_id = ret["UploadId"]
            self.upload_id = upload.upload_id
            self.current_uploads[self.file] = upload
            settings.set("uploads", jsonpickle.encode(self.current_uploads))
            settings.save()

        else:
            # read settings
            self.upload_id = upload.upload_id
            self.current_part = upload.current_part
            self.part_etag_list = upload.part_etag_list

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

            upload.part_etag_list = self.part_etag_list
            upload.current_part = self.current_part
            upload.upload_id = self.upload_id
            upload.complete = False

            settings.set("uploads", jsonpickle.encode(self.current_uploads))
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
            upload.complete = True
            settings.set("uploads", jsonpickle.encode(self.current_uploads))
            settings.save()
        else:
            # we have canceled
            self.cancel_upload()
            settings.set("uploads", jsonpickle.encode(self.current_uploads))
            settings.save()
            self._stop()
        f.close()

    def send_callback(self, bytes_loaded):
        self.progress_callback(self, bytes_loaded)

    def cancel_upload(self):
        del self.current_uploads[self.file]
        settings.set("uploads", jsonpickle.encode(self.current_uploads))
        settings.save()
        abort_ret = self.s3client.abort_multipart_upload(Bucket=self.bucket,
                                                         Key=self.key,
                                                         UploadId=self.upload_id
                                                         )
        print_mine(abort_ret)

    def abort(self):
        self.canceled = True
        # self.cancel_upload()
        # self._stop()
