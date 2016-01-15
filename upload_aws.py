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
from qtfaststart import processor
import subprocess
import sys
import platform

api_url = "http://api.qa.videobserver.com/"
# test_file = "teste user.mp4"
# test_file = "d:\\adil_camara_fixa.mp4"
# test_file = "c:\\Users\Rui\Desktop\drawing_ERROR.mp4"
test_conv = "c:\\Users\Rui\Desktop\\00009.MTS"

# test_out = "c:\\Users\\Rui\\Desktop\\voconv_teste_out.mp4"

test_name = "teste-coisas"

ffmpeg_path = "ffmpeg.exe"
ffprobe_path = "ffprobe.exe"
path_separator = "\\"

if platform.system() == "Darwin":
    os_prefix = os.getcwd() + "/VoConverter.app/Contents/Resources/"

    ffmpeg_path = os_prefix + "ffmpeg"
    ffprobe_path = os_prefix + "ffprobe"

    shell_status = False
    path_separator = "/"

# lets us try to send the minimum 5 megabytes at a time
part_size = 5 * 1024 * 1024

# just some global settings
settings = EasySettings("test.conf")

# lets create a template array?


# we need this because: https://github.com/pyinstaller/pyinstaller/wiki/Recipe-subprocess

if getattr(sys, 'frozen', False):
    isFrozen = True
else:
    isFrozen = False


def subprocess_args(include_stdout=True):
    # The following is true only on Windows.
    if hasattr(subprocess, 'STARTUPINFO'):
        # On Windows, subprocess calls will pop up a command window by default
        # when run from Pyinstaller with the ``--noconsole`` option. Avoid this
        # distraction.
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        # Windows doesn't search the path by default. Pass it an environment so
        # it will.
        env = os.environ
    else:
        si = None
        env = None

    # ``subprocess.check_output`` doesn't allow specifying ``stdout``::
    #
    #   Traceback (most recent call last):
    #     File "test_subprocess.py", line 58, in <module>
    #       **subprocess_args(stdout=None))
    #     File "C:\Python27\lib\subprocess.py", line 567, in check_output
    #       raise ValueError('stdout argument not allowed, it will be overridden.')
    #   ValueError: stdout argument not allowed, it will be overridden.
    #
    # So, add it only if it's needed.
    if include_stdout:
        ret = {'stdout:': subprocess.PIPE}
    else:
        ret = {}

    # On Windows, running this from the binary produced by Pyinstaller
    # with the ``--noconsole`` option requires redirecting everything
    # (stdin, stdout, stderr) to avoid an OSError exception
    # "[Error 6] the handle is invalid."
    ret.update({'stdin': subprocess.PIPE,
                'stderr': subprocess.PIPE,
                'startupinfo': si,
                'env': env })
    return ret


class EncodingPreset:

    def __init__(self, name, width, height, bitrate, framerate, keyframes):
        self.name = name
        self.width = width
        self.height = height
        self.bitrate = bitrate
        self.framerate = framerate
        self.keyframes = keyframes


class VideoInfo:

    def __init__(self):
        self.width = 0
        self.height = 0
        self.has_sound = True
        self.duration = 0
        self.bitrate = 0
        self.framerate = 0
        self.video_codec = ""
        self.audio_codec = ""

    def set_w_and_h(self, w, h):
        self.width = w
        self.height = h

    def set_has_sound(self, has_sound):
        self.has_sound = has_sound

    def set_duration(self, duration):
        self.duration = duration

    def set_bitrate(self, bitrate):
        self.bitrate = bitrate

    def set_framerate(self, framerate):
        self.framerate = framerate

    def set_video_codec(self, codec):
        self.video_codec = codec

    def set_audio_codec(self, codec):
        self.audio_codec = codec

    def codecs_match(self, other_info):
        if self.width != other_info.width or\
           self.height != other_info.height or\
           self.video_codec != other_info.video_codec or\
           self.audio_codec != other_info.audio_codec:
            return False
        return True


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

    def __init__(self, in_video, in_video_info, out_video, callback, preset):

        super().__init__()

        self.in_video = in_video
        self.in_video_info = in_video_info
        self.out_video = out_video
        self.callback = callback
        self.preset = preset

    def run(self):

        # new_w = self.in_video_info.width
        # new_h = self.in_video_info.height

        # if self.restrict_resolution:
        #     if self.in_video_info.width > 3000 or self.in_video_info.height > 3000:
        #         new_w = int(self.in_video_info.width / 2)
        #         new_h = int(self.in_video_info.height / 2)
        #
        #         if new_w % 2 != 0:
        #             new_w += 1
        #
        #         if new_h % 2 != 0:
        #             new_h += 1

        if self.preset.name == "Original":
            self.preset.width = self.in_video_info.width
            self.preset.height = self.in_video_info.height
            self.preset.bitrate = str(int(self.in_video_info.bitrate) / 1024)
            self.preset.framerate = 25
            self.preset.keyframes = 25

        w = str(self.preset.width)
        h = str(self.preset.height)

        # shamelessly stolen from
        # http://superuser.com/questions/547296/resizing-videos-with-ffmpeg-avconv-to-fit-into-static-sized-player
        scale = "iw*min(" + w + "/iw\," + h + "/ih):ih*min(" + w + "/iw\," + h + "/ih), pad=" + w + ":" + h +\
                ":(" + w + " -iw*min(" + w + "/iw\," + h + "/ih))/2:(" + h + "-ih*min(" + w + "/iw\," + h + "/ih))/2"
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
                "keyint=" + str(self.preset.keyframes) + ":min-keyint=" + str(self.preset.keyframes),
                "-c:v",
                "libx264",
                "-b:v",
                str(self.preset.bitrate) + "k",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-strict",
                "-2",
                # pass scaling
                "-vf",
                "scale=" + scale,
                # frames
                "-framerate",
                str(self.preset.framerate),
                # output file
                self.out_video + "_temp.mp4"
                ]

        p = Popen(cmd,
                  stderr=STDOUT,
                  stdout=PIPE,
                  universal_newlines=True
                  )

        reg = re.compile("time=[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9]")

        had_one_hundred = False

        for line in iter(p.stdout.readline, b''):
            print(">>> " + str(line.rstrip()))
            m = reg.search(str(line.rstrip()))
            if m is not None:
                time_str = m.group().replace("time=", "")[:-3]
                splitted = time_str.split(":")
                seconds = 60 * 60 * int(splitted[0]) + 60 * int(splitted[1]) + int(splitted[2])
                # print("time:", time_str, " seconds:" + str(seconds))
                percentage = int((seconds * 100) / int(float(self.in_video_info.duration)))

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

        processor.process(self.out_video + "_temp.mp4", self.out_video)


class ConvertToFastCopy(threading.Thread):

    def __init__(self, temp_dir, cut_number, input_video, tmp_out):

        super().__init__()

        self.cut_number = cut_number
        self.input_video = input_video
        self.tmp_out = tmp_out
        self.temp_dir = temp_dir

    def run(self):

        # log_file = open(self.temp_dir.name + path_separator + str(self.cut_number) + "_fast_copy.log", "wb")

        out = check_call([
            # path to ffmpeg
            ffmpeg_path,
            # overwrite
            "-y",
            # start time, since this clip is already we want to use it all
            "-ss",
            "0",
            # input file
            "-i",
            self.input_video,
            "-c",
            "copy",
            "-bsf:v",
            "h264_mp4toannexb",
            "-f",
            "mpegts",
            # output file
            self.tmp_out
        ],  stderr=STDOUT,
            shell=False)


class JoinFiles(threading.Thread):
    def __init__(self, in_videos, out_video, callback, preset, tmp_dir):

        super().__init__()

        self.in_videos = in_videos
        self.out_video = out_video
        self.callback = callback
        self.preset = preset
        self.tmp_dir = tmp_dir

        self.progress = 0
        self.cut_number = 0

    def run(self):
        # loop the in videos and convert according to the preset
        for video in self.in_videos:
            # use the damn preset
            video_info = frame.get_video_info(video)

            convert_thr = EncodeWithKeyFrames(in_video=video,
                                              out_video=self.tmp_dir.name + path_separator + str(self.cut_number) + "_to_join.mp4",
                                              callback=self.update_progress, preset=self.preset,
                                              in_video_info=video_info)

            convert_thr.start()

            while convert_thr.is_alive():
                dummy_event = threading.Event()
                dummy_event.wait(timeout=0.01)

            # fast copy??
            fast_copy_thr = ConvertToFastCopy(self.tmp_dir, cut_number=self.cut_number,
                                              input_video=self.tmp_dir.name + path_separator + str(self.cut_number) + "_to_join.mp4",
                                              tmp_out=self.tmp_dir.name + path_separator + str(self.cut_number) + "_fast.mp4")
            fast_copy_thr.start()
            while fast_copy_thr.is_alive():
                dummy_event = threading.Event()
                dummy_event.wait(timeout=0.01)

            self.cut_number += 1

        # now we join the damn thing
        join_args = []
        # path to ffmpeg
        join_args.append(ffmpeg_path)
        # overwrite
        join_args.append("-y")
        # input
        join_args.append("-i")
        # the concat files
        concat = "concat:"
        for x in range(0, self.cut_number):
            concat += self.tmp_dir.name + path_separator + str(x) + "_fast.mp4" + "|"
        concat = concat[:-1]
        concat += ""
        join_args.append(concat)

        # fast copy concatneation
        join_args.append("-c")
        join_args.append("copy")
        join_args.append("-bsf:a")
        join_args.append("aac_adtstoasc")
        join_args.append("-movflags")
        join_args.append("faststart")

        # outfile
        # put it on desktop for now
        join_args.append("" + self.out_video + "")

        print("JUNTAMOS", join_args)

        try:
            out = check_call(join_args, stderr=STDOUT, shell=False)
        except CalledProcessError as cpe:
            print("ERROR>>", cpe.output)

        # we are DONE!
        self.callback(100)

    def update_progress(self, progress):
        # which part of the percentage each item takes?
        item_slice = 100 / len(self.in_videos)
        # at what cut number are we?
        # so at minimum we are
        baseline = self.cut_number * item_slice
        # now we add the actual slice percentage to the baseline
        to_add = (progress * item_slice / 100)
        self.callback(int(baseline + to_add))


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


class MyFileDrop(wx.FileDropTarget):

    def OnDropFiles(self, x, y, filenames):
        # frame.join_files(filenames)
        frame.add_files_to_join(filenames)
        return True


class MainWindow(wx.Frame):

    def __init__(self, parent, title):

        # we don't want to allow resizing
        wx.Frame.__init__(self, parent, title=title, size=(600, 100),
                          style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX))

        # self.panel = wx.Panel(parent=self, id=wx.ID_ANY)

        self.presets = []

        # parse the presets, and create radio buttons for each one
        presets_file = open("presets.json", "r")
        presets_json = json.load(presets_file)

        preset_choices = []

        for preset_json in presets_json:
            preset = EncodingPreset(name=preset_json["name"],
                                    width=preset_json["width"],
                                    height=preset_json["height"],
                                    bitrate=preset_json["bitrate"],
                                    framerate=preset_json["framerate"],
                                    keyframes=preset_json["keyframes"])
            self.presets.append(preset)
            preset_choices.append(preset.name)

        original_preset = EncodingPreset(name="Original",
                                         width=0,
                                         height=0,
                                         bitrate=0,
                                         framerate=0,
                                         keyframes=0)
        preset_choices.append(original_preset.name)
        self.presets.append(original_preset)

        self.main_sizer = wx.BoxSizer(wx.VERTICAL)

        self.main_sizer.Add(wx.StaticText(parent=self, id=wx.ID_ANY, label="Destination DIR"))

        self.destination_picker = wx.DirPickerCtrl(parent=self, id=wx.ID_ANY, path="",
                                                   message="Converted / joined files destination")

        desktop = os.path.expanduser("~" + path_separator + "Desktop")
        self.destination_picker.SetPath(desktop)

        self.main_sizer.Add(self.destination_picker, 0, wx.EXPAND)

        convert_header = wx.StaticText(parent=self, id=wx.ID_ANY, label="CONVERT JOIN FUNCTIONS")
        self.main_sizer.Add(convert_header)

        # create the radio button groups
        self.presets_radio_box = wx.RadioBox(parent=self, id=wx.ID_ANY, label="Video Preset!!", choices=preset_choices)
        self.presets_radio_box.SetSelection(1)

        self.main_sizer.Add(self.presets_radio_box)

        # should I open a bug somewhere??
        if platform.system() == "Darwin":
            self.join_list_view = wx.ListView(parent=self, id=wx.ID_ANY, style=wx.LC_REPORT, name="FILES TO JOIN!!!")
        else:
            self.join_list_view = wx.ListView(parent=self, winid=wx.ID_ANY, style=wx.LC_REPORT, name="FILES TO JOIN!!!")
        self.main_sizer.Add(self.join_list_view, wx.EXPAND)
        self.join_list_view.AppendColumn("File to convert. More than one file joins", wx.LIST_FORMAT_CENTER, 500)

        self.main_sizer.Add(wx.StaticText(parent=self, id=wx.ID_ANY, label="Final file name"))
        self.final_name = wx.TextCtrl(parent=self, id=wx.ID_ANY)
        self.main_sizer.Add(self.final_name, 0, wx.EXPAND)

        self.add_single_file_btn = wx.Button(parent=self, id=wx.ID_ANY, label="Add file to convert/join")
        self.main_sizer.Add(self.add_single_file_btn, 0, wx.ALIGN_CENTER_HORIZONTAL)

        self.join_files_btn = wx.Button(parent=self, id=wx.ID_ANY, label="Convert/Join these files")
        self.main_sizer.Add(self.join_files_btn, 0, wx.ALIGN_CENTER_HORIZONTAL)

        self.conversion_progress_gauge = wx.Gauge(parent=self, id=wx.ID_ANY, range=100, size=(400, 20))

        self.upload_progress_gauge = wx.Gauge(parent=self, id=wx.ID_ANY, range=100, size=(400, 20))

        self.conv_progress_label = wx.StaticText(parent=self, id=wx.ID_ANY, label="0%")

        self.main_sizer.Add(self.conversion_progress_gauge, 0, wx.EXPAND)
        self.main_sizer.Add(self.conv_progress_label, 0, wx.BOTTOM, 50)

        #
        # UPLOAD
        #

        self.main_sizer.Add(wx.StaticText(parent=self, id=wx.ID_ANY, label="UPLOAD FUNCS (A apontar para o QA)"), 0, wx.BOTTOM, 10)

        self.main_sizer.Add(wx.StaticText(parent=self, id=wx.ID_ANY, label="Username"))
        self.username = wx.TextCtrl(parent=self, id=wx.ID_ANY, value="soccer_teste@vo.com")
        self.main_sizer.Add(self.username, 0, wx.EXPAND)

        self.main_sizer.Add(wx.StaticText(parent=self, id=wx.ID_ANY, label="Password"))
        self.password = wx.TextCtrl(parent=self, id=wx.ID_ANY, value="password")
        self.main_sizer.Add(self.password, 0, wx.EXPAND)

        self.main_sizer.Add(wx.StaticText(parent=self, id=wx.ID_ANY, label="File to Upload"))

        self.upload_file_picker = wx.FilePickerCtrl(parent=self, id=wx.ID_ANY, message="File to upload")
        self.main_sizer.Add(self.upload_file_picker, 0, wx.EXPAND)

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

        self.Bind(event=wx.EVT_LIST_ITEM_SELECTED, handler=self.join_list_remove, source=self.join_list_view)
        self.Bind(event=wx.EVT_BUTTON, handler=self.join_files, source=self.join_files_btn)
        self.Bind(event=wx.EVT_BUTTON, handler=self.add_single_file, source=self.add_single_file_btn)

        self.SetSizer(self.main_sizer)
        self.main_sizer.SetSizeHints(self)
        self.Show()

        # test the drop target stuff?
        self.file_drop = MyFileDrop()
        self.SetDropTarget(self.file_drop)

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

        self.conv_data_points = []
        self.conv_start_time = time.time()

    def do_upload(self, e):

        # AMAZON STUFF
        t = get_token(self.username.GetValue(), self.password.GetValue())
        aws_data = get_aws_data(t["token"])

        # init s3 session
        aws_session = Session(aws_access_key_id=aws_data["AccessKeyId"],
                              aws_secret_access_key=aws_data["SecretAccessKey"],
                              aws_session_token=aws_data["SessionToken"],
                              region_name=aws_data["Region"])

        # first create and object to send
        client = aws_session.client(service_name="s3",
                                    endpoint_url=aws_data["CloudfrontEndpoint"])

        self.upload_start_time = time.time()

        # we cheat so that the user can see some progress at start
        self.upload_progress_gauge.Pulse()
        # self.progress_label.SetLabelText("1" + "%")
        self.Update()

        self.upload_key = os.path.basename(self.upload_file_picker.GetPath())
        print(self.upload_key)

        self.total_size = os.stat(self.upload_file_picker.GetPath()).st_size

        upload_thr = UploadFile(s3client=client,
                                bucket=aws_data["Bucket"],
                                key=self.upload_key,
                                file=self.upload_file_picker.GetPath(),
                                progress_callback=self.update_progress,
                                resume_callback=self.set_progress,
                                name=test_name)
        upload_thr.start()

        while upload_thr.is_alive():
            dummy_event = threading.Event()
            dummy_event.wait(timeout=0.01)
            if self.percentage > 0:
                self.upload_progress_gauge.SetValue(self.percentage)
            # self.upload_progress_label.SetLabelText(str(self.percentage) + "%")
            if len(self.upload_data_points) > 0:

                remain = (sum(self.upload_data_points) / len(self.upload_data_points))
                # print(remain)
                s = int(remain % 60)
                m = int((remain / 60) % 60)
                h = int((remain / (60 * 60)) % 60)

                self.upload_progress_label.SetLabelText(str(self.percentage) + "%      " +
                                                        str(h) + "h " + str(m) + "m " + str(s) + "s" +
                                                        " remaining to completion"
                                                        )
            wx.Yield()
            self.Update()

        # get the real duration
        final_video_info = self.get_video_info(self.upload_file_picker.GetPath())

        print("file duration", final_video_info.duration)


        confirm_upload(t["token"], bucket=aws_data["Bucket"], key=self.upload_key, duration=int(float(final_video_info.duration)), size=100)
        self.upload_progress_label.SetLabelText("Complete")

        print("done confirm")

    def update_progress(self, progress):
        self.uploaded_size += progress
        self.percentage = math.ceil((self.uploaded_size / self.total_size) * 100)

        if self.percentage == 0:
            # self.percentage = 1
            return

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

    # def convert_test(self, e):
    #
    #     # get the preset name
    #     preset_name = self.presets_radio_box.GetStringSelection()
    #     # and now get the preset itself
    #     preset = [x for x in self.presets if x.name == preset_name][0]
    #
    #     self.conv_start_time = time.time()
    #
    #     video_to_conv = self.file_picker.GetPath()
    #
    #     video_info = self.get_video_info(video_to_conv)
    #
    #     self.converted_video = self.temp_dir.name + "\\" + str(uuid.uuid4()) + "_" + str(self.t["user_id"]) + ".mp4"
    #     print(self.converted_video)
    #
    #     log_file = open(self.temp_dir.name + '\\' + "conv.log", 'w')
    #
    #     convert_thr = EncodeWithKeyFrames(in_video=video_to_conv, in_video_info=video_info,
    #                                       out_video=self.converted_video,
    #                                       callback=self.update_conv_progress,
    #                                       preset=preset)
    #     convert_thr.start()
    #
    #     while convert_thr.is_alive():
    #         dummy_event = threading.Event()
    #         dummy_event.wait(timeout=0.01)
    #         # self.upload_progress_gauge.SetValue(self.percentage)
    #         self.conversion_progress_gauge.SetValue(self.conv_progress)
    #         if len(self.conv_data_points) > 0:
    #
    #             remain = (sum(self.conv_data_points) / len(self.conv_data_points))
    #             # print(remain)
    #             s = int(remain % 60)
    #             m = int((remain / 60))
    #             h = int((remain / (60 * 60)))
    #
    #             self.conv_progress_label.SetLabelText(str(self.conv_progress) + "%      " +
    #                                                   str(h) + "h " + str(m) + "m " + str(s) + "s" +
    #                                                   " remaining to completion"
    #                                                   )
    #
    #         wx.Yield()
    #         self.Update()
    #
    #     self.conversion_progress_gauge.SetValue(100)
    #     self.conv_progress_label.SetLabelText("Complete")
    #     self.conversion_done = True
    #     self.total_size = os.stat(self.converted_video).st_size
    #
    # def update_conv_progress(self, progress):
    #     self.conv_progress = progress
    #     if progress == 0:
    #         progress = 1
    #
    #     # calc estimated time
    #     delta = time.time() - self.conv_start_time
    #     eta = (delta * 100) / progress
    #     remaining = eta - delta
    #
    #     # print("d:", delta, "p:", progress, "e:", eta, "r:", remaining)
    #
    #     # create data point
    #     self.conv_data_points.append(remaining)
    #     if len(self.conv_data_points) > 5:
    #         # remove the earliest data point
    #         self.conv_data_points.pop(0)

    def get_video_info(self, video_path):

        print("VIDEO_PATH", video_path)

        print("EXITS", os.path.exists(ffprobe_path), os.path.exists(video_path))

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
            ], universal_newlines=True, **subprocess_args(False))

            info_json = json.loads(out)

            has_sound = False

            video_info = VideoInfo()
            for stream in info_json["streams"]:
                if stream["codec_type"] == "video":
                    video_info.set_w_and_h(stream["width"], stream["height"])
                    video_info.set_bitrate(stream.get("bit_rate"))
                    video_info.set_framerate(stream["avg_frame_rate"])
                    video_info.set_video_codec(stream.get("codec_name"))
                if stream["codec_type"] == "audio":
                    video_info.set_audio_codec(stream.get("codec_name"))
                    has_sound = True

            if video_info.bitrate is None:
                video_info.set_bitrate(info_json.get("format").get("bit_rate"))

            video_info.set_has_sound(has_sound)

            video_info.set_duration(info_json["format"]["duration"])

            return video_info

        except CalledProcessError as cpe:
            print("FFPROBE OUT", cpe.output)

    def join_files(self, e):

        # get the preset name
        preset_name = self.presets_radio_box.GetStringSelection()
        # and now get the preset itself
        preset = [x for x in self.presets if x.name == preset_name][0]

        # get the files
        filenames = []
        video_infos = []
        for x in range(self.join_list_view.GetItemCount()):
            item = self.join_list_view.GetItem(x)
            filenames.append(item.GetText())
            video_infos.append(self.get_video_info(item.GetText()))

        print("FILENAMES DO CENA", filenames)

        # do we have similar videos or do we need to use a fixed preset?
        codecs_match = True
        first_info = video_infos[0]
        for info in video_infos:
            if not first_info.codecs_match(info):
                codecs_match = False

        if preset_name == "Original" and len(filenames) > 1 and not codecs_match:
            print("NO JOIN ON ORIGINAL")

            # show dialog to user
            dialog = wx.Dialog(parent=self, id=wx.ID_ANY, title="Cannot use original preset for joining")
            sizer = wx.BoxSizer(wx.VERTICAL)
            msg = wx.StaticText(parent=dialog, id=wx.ID_ANY, label="Cannot use original preset for joining two or more different kinds of files\nCodec or resolution mismatch")
            sizer.Add(msg)
            ok_btn = wx.Button(parent=dialog, id=wx.ID_OK, label="Ok")
            sizer.Add(ok_btn)
            dialog.SetSizer(sizer)
            sizer.SetSizeHints(dialog)
            dialog.ShowModal()

            return

        self.conv_start_time = time.time()

        out_video = self.destination_picker.GetPath() + path_separator + self.final_name.GetValue() + ".mp4"

        join_thr = JoinFiles(in_videos=filenames, out_video=out_video, tmp_dir=self.temp_dir,
                             preset=preset, callback=self.update_join_progress)

        join_thr.start()

        while join_thr.is_alive():
            dummy_event = threading.Event()
            dummy_event.wait(timeout=0.01)

            self.conversion_progress_gauge.SetValue(self.conv_progress)
            if len(self.conv_data_points) > 0:

                remain = (sum(self.conv_data_points) / len(self.conv_data_points))
                # print(remain)
                s = int(remain % 60)
                m = int((remain / 60) % 60)
                h = int((remain / (60 * 60)) % 60)

                self.conv_progress_label.SetLabelText(str(self.conv_progress) + "%      " +
                                                      str(h) + "h " + str(m) + "m " + str(s) + "s" +
                                                      " remaining to completion"
                                                      )

            wx.Yield()
            self.Update()

        self.conversion_progress_gauge.SetValue(100)
        self.conv_progress_label.SetLabelText("Join Complete")
        self.conversion_done = True

        self.upload_file_picker.SetPath(out_video)

    def update_join_progress(self, progress):
        self.conv_progress = progress
        if progress == 0:
            progress = 1

        # calc estimated time
        delta = time.time() - self.conv_start_time
        eta = (delta * 100) / progress
        remaining = eta - delta

        # create data point
        self.conv_data_points.append(remaining)
        if len(self.conv_data_points) > 5:
            # remove the earliest data point
            self.conv_data_points.pop(0)

    def add_files_to_join(self, filenames):
        for file in filenames:
            self.join_list_view.Append([file])

        # place the first file as the output sugestion
        base = os.path.basename(filenames[0])
        no_ext = base.split(".")[0]
        final = no_ext + "_vo_converted"
        self.final_name.SetValue(final)

    def add_single_file(self, e):
        path = ""
        dlg = wx.FileDialog(self, "Video file", "", "", "*.*", wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()

        dlg.Destroy()
        if path != "":
            self.add_files_to_join([path])

    def join_list_remove(self, e):
        print("index", e.GetIndex())
        self.join_list_view.DeleteItem(e.GetIndex())


app = wx.App(False)
frame = MainWindow(None, "Uploadamos")
app.MainLoop()
