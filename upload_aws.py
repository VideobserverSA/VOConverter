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
from easysettings import EasySettings
from subprocess import *
import tempfile
import uuid
import re
import time

api_url = "http://api.qa.videobserver.com/"
# test_file = "teste user.mp4"
# test_file = "d:\\adil_camara_fixa.mp4"
# test_file = "c:\\Users\Rui\Desktop\drawing_ERROR.mp4"
test_conv = "c:\\Users\Rui\Desktop\\00009.MTS"

# test_out = "c:\\Users\\Rui\\Desktop\\voconv_teste_out.mp4"

test_name = "teste-coisas"

ffmpeg_path = "ffmpeg.exe"
ffprobe_path = "ffprobe.exe"

# lets us try to send the minimum 5 megabytes at a time
part_size = 5 * 1024 * 1024

# just some global settings
settings = EasySettings("test.conf")


class VideoInfo:

    def __init__(self):
        self.width = 0
        self.height = 0
        self.has_sound = True
        self.duration = 0

    def set_w_and_h(self, w, h):
        self.width = w
        self.height = h

    def set_has_sound(self, has_sound):
        self.has_sound = has_sound

    def set_duration(self, duration):
        self.duration = duration


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


class EncodeWithKeyFrames(threading.Thread):

    def __init__(self, in_video,in_video_time, out_video, key_frames, log, callback):

        super().__init__()

        self.in_video = in_video
        self.in_video_time = in_video_time
        self.out_video = out_video
        self.key_frames = key_frames
        self.log = log
        self.callback = callback

    def run(self):

        # log_path = self.temp_dir.name + path_separator + str(self.cut_number) + "_cut_key_frames.log"
        # log_file = open(log_path, "wb")

        cmd = [
                # path to ffmpeg
                ffmpeg_path,
                # overwrite
                "-y",
                # input file
                "-i",
                self.in_video,
                # codec
                "-x264opts",
                "keyint=" + str(self.key_frames) + ":min-keyint=" + str(self.key_frames),
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-strict",
                "-2",
                # output file
                self.out_video
                ]

        p = Popen(cmd,
                  stderr=STDOUT,
                  stdout=PIPE,
                  universal_newlines=True
                  )

        reg = re.compile("time=[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9]")

        had_one_hundred = False

        for line in iter(p.stdout.readline, b''):
            # print(">>> " + str(line.rstrip()))
            m = reg.search(str(line.rstrip()))
            if m is not None:
                time_str = m.group().replace("time=", "")[:-3]
                splitted = time_str.split(":")
                seconds = 60 * 60 * int(splitted[0]) + 60 * int(splitted[1]) + int(splitted[2])
                # print("time:", time_str, " seconds:" + str(seconds))
                percentage = int((seconds * 100) / int(float(self.in_video_time)))

                if percentage == 100:
                    had_one_hundred = True
                # print(str(percentage))
                self.callback(percentage)
            else:
                if had_one_hundred:
                    # the process Popen does not terminate correctly with universal newlines
                    # so we kill it
                    # this happens and p.stdout.readling keeps returning empty strings
                    # so we need to avoid it
                    p.terminate()
                    break


# get the token
def get_token():
    try:

        # compose the data
        data = {"user": "soccer_teste@vo.com",
                "pass": "password",
                "version": "10.0.100",
                "type": "VO_CONVERTER_APP"}
        post_data = urllib.parse.urlencode(data)
        binary_data = post_data.encode()

        with urllib.request.urlopen(url=api_url + "v3/auth/get_token.json", data=binary_data) as auth_request:
            # print(auth_request.status)
            response_json = json.loads(auth_request.read().decode('utf-8'))
            # print(response_json)
            return {"token": response_json["data"]["token"], "user_id": response_json["data"]["user_id"]}

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


class MainWindow(wx.Frame):

    def __init__(self, parent, title):

        # we don't want to allow resizing
        wx.Frame.__init__(self, parent, title=title, size=(600, 100),
                          style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX))

        # self.panel = wx.Panel(parent=self, id=wx.ID_ANY)

        self.main_sizer = wx.BoxSizer(wx.VERTICAL)

        self.file_picker = wx.FilePickerCtrl(parent=self, id=wx.ID_ANY, message="Chose file to convert and upload",
                                             path="C:\\Users\\Rui\\Desktop\\Video07set_high.flv")

        self.conversion_progress_gauge = wx.Gauge(parent=self, id=wx.ID_ANY, range=100, size=(400, 20))

        self.upload_progress_gauge = wx.Gauge(parent=self, id=wx.ID_ANY, range=100, size=(400, 20))

        self.conv_progress_label = wx.StaticText(parent=self, id=wx.ID_ANY, label="0%")

        self.main_sizer.Add(self.file_picker, 0, wx.EXPAND)

        self.main_sizer.Add(self.conversion_progress_gauge, 0, wx.EXPAND)
        self.main_sizer.Add(self.conv_progress_label)
        self.convert_btn = wx.Button(parent=self, id=wx.ID_ANY, label="CONVERT THIS STUFF!!")
        self.main_sizer.Add(self.convert_btn, 0, wx.ALIGN_CENTER_HORIZONTAL)

        self.Bind(event=wx.EVT_BUTTON, handler=self.convert_test, source=self.convert_btn)

        self.main_sizer.Add(self.upload_progress_gauge, 0, wx.EXPAND)

        self.upload_progress_label = wx.StaticText(parent=self, id=wx.ID_ANY, label="0%")
        self.main_sizer.Add(self.upload_progress_label)

        self.upload_button = wx.Button(parent=self, id=wx.ID_ANY, label="UPLOAD!!!")
        self.main_sizer.Add(self.upload_button, 0, wx.ALIGN_CENTER_HORIZONTAL)

        self.Bind(event=wx.EVT_BUTTON, handler=self.do_upload, source=self.upload_button)

        self.cancel_button = wx.Button(parent=self, id=wx.ID_ANY, label="CANCEL YAY!!")
        self.main_sizer.Add(self.cancel_button, 0, wx.ALIGN_CENTER_HORIZONTAL)

        self.Bind(event=wx.EVT_BUTTON, handler=self.cancel_this, source=self.cancel_button)

        self.test_button = wx.Button(parent=self, id=wx.ID_ANY, label="CLEAN IMCOMPLETE!!!")
        self.main_sizer.Add(self.test_button, 0, wx.ALIGN_CENTER_HORIZONTAL)

        self.Bind(event=wx.EVT_BUTTON, handler=self.clean_incomplete_uploads, source=self.test_button)

        self.SetSizer(self.main_sizer)
        self.main_sizer.SetSizeHints(self)
        self.Show()

        self.t = ""
        self.aws_data = {}

        self.temp_dir = tempfile.TemporaryDirectory()
        self.upload_key = ''

        # to record progress
        self.total_size = 0
        self.uploaded_size = 0
        self.percentage = 0
        self.last_percentage = 0

        self.upload_data_points = []
        self.upload_start_time = time.time()

        self.conv_progress = 0

        self.converted_video = ''
        self.conversion_done = False

        self.t = get_token()
        self.aws_data = get_aws_data(self.t["token"])

        self.conv_data_points = []
        self.conv_start_time = time.time()

        # init s3 session
        self.aws_session = Session(aws_access_key_id=self.aws_data["AccessKeyId"],
                                   aws_secret_access_key=self.aws_data["SecretAccessKey"],
                                   aws_session_token=self.aws_data["SessionToken"],
                                   region_name=self.aws_data["Region"])

        # first create and object to send
        self.client = self.aws_session.client(service_name="s3",
                                              endpoint_url=self.aws_data["CloudfrontEndpoint"])

    def do_upload(self, e):

        if not self.conversion_done:
            return

        self.upload_start_time = time.time()

        # we cheat so that the user can see some progress at start
        self.upload_progress_gauge.Pulse()
        # self.progress_label.SetLabelText("1" + "%")
        self.Update()

        self.upload_key = os.path.basename(self.converted_video)
        print(self.upload_key)

        upload_thr = UploadFile(s3client=self.client,
                                bucket=self.aws_data["Bucket"],
                                key=self.upload_key,
                                file=self.converted_video,
                                progress_callback=self.update_progress,
                                resume_callback=self.set_progress,
                                name=test_name)
        upload_thr.start()

        while upload_thr.is_alive():
            dummy_event = threading.Event()
            dummy_event.wait(timeout=0.01)
            self.upload_progress_gauge.SetValue(self.percentage)
            # self.upload_progress_label.SetLabelText(str(self.percentage) + "%")
            if len(self.upload_data_points) > 0:

                remain = (sum(self.upload_data_points) / len(self.upload_data_points))
                # print(remain)
                s = int(remain % 60)
                m = int((remain / 60))
                h = int((remain / (60 * 60)))

                self.upload_progress_label.SetLabelText(str(self.percentage) + "%      " +
                                                        str(h) + "h " + str(m) + "m " + str(s) + "s" +
                                                        " remaining to completion"
                                                        )
            wx.Yield()
            self.Update()

        confirm_upload(token=self.t["token"], bucket=self.aws_data["Bucket"], key=self.upload_key, duration=100, size=100)
        self.upload_progress_label.SetLabelText("Complete")

    def update_progress(self, progress):
        self.uploaded_size += progress
        self.percentage = math.ceil((self.uploaded_size / self.total_size) * 100)

        if self.percentage == 0:
            self.percentage = 1

        # calc estimated time
        delta = time.time() - self.upload_start_time
        eta = (delta * 100) / self.percentage
        remaining = eta - delta

        # print("d:", delta, "p:", progress, "e:", eta, "r:", remaining)

        # create data point
        self.upload_data_points.append(remaining)
        if len(self.upload_data_points) > 5:
            # remove the earliest data point
            self.upload_data_points.pop(0)

    def set_progress(self, progress):
        self.uploaded_size = progress
        self.percentage = math.ceil((self.uploaded_size / self.total_size) * 100)

    def cancel_this(self, e):
        for thread in threading.enumerate():
            if thread.name is test_name:
                thread.cancel_upload()
        # sys.exit(0)

    def clean_incomplete_uploads(self, e):
        ret = self.client.list_multipart_uploads(Bucket=self.aws_data["Bucket"])
        # print(ret)

        for upload in ret["Uploads"]:
            # print(upload["Key"])
            if upload["Key"] == "test_multi.mp4":
                # print("u:", upload["UploadId"], "\n")
                abrt_ret = self.client.abort_multipart_upload(Bucket=self.aws_data["Bucket"],
                                                              Key=upload["Key"],
                                                              UploadId=upload["UploadId"]
                                                              )
        #         print(abrt_ret)

    def convert_test(self, e):

        self.conv_start_time = time.time()

        video_to_conv = self.file_picker.GetPath()

        video_info = self.get_video_info(video_to_conv)

        self.converted_video = self.temp_dir.name + "\\" + str(uuid.uuid4()) + "_" + str(self.t["user_id"]) + ".mp4"
        print(self.converted_video)

        log_file = open(self.temp_dir.name + '\\' + "conv.log", 'w')

        convert_thr = EncodeWithKeyFrames(in_video=video_to_conv, in_video_time=video_info.duration,
                                          out_video=self.converted_video, key_frames=24,
                                          log=log_file, callback=self.update_conv_progress)
        convert_thr.start()

        while convert_thr.is_alive():
            dummy_event = threading.Event()
            dummy_event.wait(timeout=0.01)
            # self.upload_progress_gauge.SetValue(self.percentage)
            self.conversion_progress_gauge.SetValue(self.conv_progress)
            if len(self.conv_data_points) > 0:

                remain = (sum(self.conv_data_points) / len(self.conv_data_points))
                # print(remain)
                s = int(remain % 60)
                m = int((remain / 60))
                h = int((remain / (60 * 60)))

                self.conv_progress_label.SetLabelText(str(self.conv_progress) + "%      " +
                                                      str(h) + "h " + str(m) + "m " + str(s) + "s" +
                                                      " remaining to completion"
                                                      )

            wx.Yield()
            self.Update()

        self.conversion_progress_gauge.SetValue(100)
        self.conv_progress_label.SetLabelText("Complete")
        self.conversion_done = True
        self.total_size = os.stat(self.converted_video).st_size

    def update_conv_progress(self, progress):
        self.conv_progress = progress
        if progress == 0:
            progress = 1

        # calc estimated time
        delta = time.time() - self.conv_start_time
        eta = (delta * 100) / progress
        remaining = eta - delta

        # print("d:", delta, "p:", progress, "e:", eta, "r:", remaining)

        # create data point
        self.conv_data_points.append(remaining)
        if len(self.conv_data_points) > 5:
            # remove the earliest data point
            self.conv_data_points.pop(0)

    def get_video_info(self, video_path):

        try:
            out = check_output([
                ffprobe_path,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                video_path
            ], stderr=STDOUT, shell=False, universal_newlines=True)

            info_json = json.loads(out)

            has_sound = False

            video_info = VideoInfo()
            for stream in info_json["streams"]:
                if stream["codec_type"] == "video":
                    video_info.set_w_and_h(stream["width"], stream["height"])
                if stream["codec_type"] == "audio":
                    has_sound = True

            video_info.set_has_sound(has_sound)

            video_info.set_duration(info_json["format"]["duration"])

            return video_info

        except CalledProcessError as cpe:
            print("FFPROBE OUT", cpe.output)


app = wx.App(False)
frame = MainWindow(None, "Uploadamos")
app.MainLoop()
