# import boto3
from boto3.session import Session
import urllib.request
from urllib.request import Request
import urllib.parse
import urllib.error
import json
import threading
import os
import math
import wx
# import sys
from easysettings import EasySettings

api_url = "http://api.qa.videobserver.com/"
# test_file = "teste user.mp4"
# test_file = "d:\\adil_camara_fixa.mp4"
test_file = "c:\\Users\Rui\Desktop\drawing_ERROR.mp4"

test_name = "teste-coisas"

# lets us try to send the minimum 5 megabytes at a time
part_size = 5 * 1024 * 1024

# just some global settings
settings = EasySettings("test.conf")


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
            print(part_upload_ret)
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


# get the token
def get_token():
    try:

        # compose the data
        data = {"user": "soccer_teste@vo.com",
                "pass": "password",
                "version": "69.69",
                "type": "ANDROID_APP"}
        post_data = urllib.parse.urlencode(data)
        binary_data = post_data.encode()

        with urllib.request.urlopen(url=api_url + "v3/auth/get_token.json", data=binary_data) as auth_request:
            # print(auth_request.status)
            response_json = json.loads(auth_request.read().decode('utf-8'))
            # print(response_json)
            return response_json["data"]["token"]

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


class MainWindow(wx.Frame):

    def __init__(self, parent, title):

        # we don't want to allow resizing
        wx.Frame.__init__(self, parent, title=title, size=(600, 100),
                          style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX))

        # self.panel = wx.Panel(parent=self, id=wx.ID_ANY)

        self.upload_progress_gauge = wx.Gauge(parent=self, id=wx.ID_ANY, range=100, size=(400, 20))

        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.main_sizer.Add(self.upload_progress_gauge, 0, wx.EXPAND)

        self.progress_label = wx.StaticText(parent=self, id=wx.ID_ANY, label="0%")
        self.main_sizer.Add(self.progress_label)

        self.upload_button = wx.Button(parent=self, id=wx.ID_ANY, label="UPLOAD!!!")
        self.main_sizer.Add(self.upload_button, 0, wx.ALIGN_CENTER_HORIZONTAL)

        self.Bind(event=wx.EVT_BUTTON, handler=self.do_upload, source=self.upload_button)

        self.cancel_button = wx.Button(parent=self, id=wx.ID_ANY, label="CANCEL YAY!!")
        self.main_sizer.Add(self.cancel_button, 0, wx.ALIGN_CENTER_HORIZONTAL)

        self.Bind(event=wx.EVT_BUTTON, handler=self.cancel_this, source=self.cancel_button)

        self.SetSizer(self.main_sizer)
        self.main_sizer.SetSizeHints(self)
        self.Show()

        self.t = ""
        self.aws_data = {}

        # to record progress
        self.total_size = os.stat(test_file).st_size
        self.uploaded_size = 0
        self.percentage = 0
        self.last_percentage = 0

        self.t = get_token()
        self.aws_data = get_aws_data(self.t)

        # init s3 session
        self.aws_session = Session(aws_access_key_id=self.aws_data["AccessKeyId"],
                                   aws_secret_access_key=self.aws_data["SecretAccessKey"],
                                   aws_session_token=self.aws_data["SessionToken"],
                                   region_name=self.aws_data["region"])

        # first create and object to send
        self.client = self.aws_session.client("s3")

    def do_upload(self, e):
        upload_thr = UploadFile(s3client=self.client,
                                bucket=self.aws_data["bucket"],
                                key="test_multi.mp4",
                                file=test_file,
                                progress_callback=self.update_progress,
                                resume_callback=self.set_progress,
                                name=test_name)
        upload_thr.start()

        while upload_thr.is_alive():
            dummy_event = threading.Event()
            dummy_event.wait(timeout=0.01)
            self.upload_progress_gauge.SetValue(self.percentage)
            self.progress_label.SetLabelText(str(self.percentage) + "%")
            wx.Yield()
            self.Update()

    def update_progress(self, progress):
        self.uploaded_size += progress
        self.percentage = math.ceil((self.uploaded_size / self.total_size) * 100)

    def set_progress(self, progress):
        self.uploaded_size = progress
        self.percentage = math.ceil((self.uploaded_size / self.total_size) * 100)

    def cancel_this(self, e):
        for thread in threading.enumerate():
            if thread.name is test_name:
                thread.cancel_upload()
        # sys.exit(0)


app = wx.App(False)
frame = MainWindow(None, "Uploadamos")
app.MainLoop()
