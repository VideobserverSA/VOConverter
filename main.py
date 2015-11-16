from tkinter import *
from tkinter import filedialog
import xml.etree.ElementTree as xmlParser
from subprocess import *
import os
import tempfile
import sys
import urllib.parse
import threading
import time
import json
from PIL import Image
import math
import base64
from easysettings import EasySettings
import configparser
import gettext
import urllib.request
import urllib.error
from distutils.version import LooseVersion
import platform
import shlex

__author__ = 'Rui'

# current_locale = 'en'

lang_conf = configparser.ConfigParser()
lang_conf.read("lang.ini")

current_locale = lang_conf["Language"]["Default Locale"]
# current_locale = locale.getdefaultlocale()[0]

locale_path = 'lang/'
language = gettext.translation('voconv', locale_path, [current_locale])
language.install()

# so that we can write shorthands
t = language.gettext

ffmpeg_path = "ffmpeg.exe"
ffprobe_path = "ffprobe.exe"

# we must use shell=True in windows, but shell=False in Mac OS
shell_status = True
# and the path separator is also different ffs
path_separator = "\\"

def shell_quote(s):
    return s.replace(" ", "\ ")

if platform.system() == "Darwin":

    #ffmpeg_path =  shell_quote(os.path.dirname(__file__) + "/ffmpeg")
    ffmpeg_path = "./ffmpeg"
    ffprobe_path = "./ffprobe"

    shell_status = False
    path_separator = "/"

root = Tk()
root.title(t("Vo Converter"))
root.iconbitmap("icon.ico")


class VideoInfo:

    def __init__(self):
        self.width = 0
        self.height = 0
        self.has_sound = True

    def set_w_and_h(self, w, h):
        self.width = w
        self.height = h

    def set_has_sound(self, has_sound):
        self.has_sound = has_sound


class Drawing:

    def __init__(self, uid, screenshot, bitmap, drawing_time):
        self.uid = uid
        self.screenshot = screenshot
        self.bitmap = bitmap
        self.drawing_time = drawing_time


class CheckForUpdate(threading.Thread):

    def __init__(self, current_version, tmp_dir):
        super().__init__()
        self.current_version = current_version
        self.download_url = ''
        self.tmp_dir = tmp_dir

    def download_upgrade(self):
        print("downloading upgrade from: " + self.download_url)
        voconv_filename = self.tmp_dir.name + '\\' + 'vo_converter_install.exe'
        urllib.request.urlretrieve(url=self.download_url, filename=voconv_filename)
        os.startfile(voconv_filename)
        sys.exit(0)

    def run(self):
        try:
            # grab the file from server
            with urllib.request.urlopen("http://staging.videobserver.com/app/converter_version.json") as version_file:
                version_json = json.loads(version_file.read().decode('utf-8'))
                if LooseVersion(self.current_version) < LooseVersion(version_json['version']):
                    self.download_url = version_json['url']
                    print('Upgrade found on server... ' + version_json['version'])

                    # create a window
                    upgrade_pop = Toplevel(padx=20, pady=20)
                    upgrade_pop.title(t("Upgrade"))
                    upgrade_pop.iconbitmap("icon.ico")

                    upgrade_message = Label(upgrade_pop, text=t("There is a new version available for download. Do you wish to:"))
                    upgrade_message.pack()

                    btn_frame = Frame(upgrade_pop)
                    btn_frame.pack(padx=10, pady=10)

                    close_btn = Button(btn_frame, text=t("Ignore this time"), command=upgrade_pop.destroy)
                    close_btn.pack(side=LEFT, padx=20)

                    download_btn = Button(btn_frame, text=t("Download"), command=self.download_upgrade)
                    download_btn.pack(side=LEFT, padx=20)
                else:
                    print('Current version installed')

        except urllib.error.URLError as ue:
            print('Could not reach server to check version... ' + str(ue.reason))


class SleepThreaded(threading.Thread):

    def __init__(self, seconds):
        super().__init__()
        self.seconds = seconds

    def run(self):
        time.sleep(self.seconds)


class GetScreenshot(threading.Thread):

    def __init__(self, input_video, out_file, video_time):

        super().__init__()

        self.input_video = input_video
        self.out_file = out_file
        self.video_time = video_time

    def run(self):
        try:
            check_call([
                ffmpeg_path,
                "-y",
                "-i",
                self.input_video,
                "-ss",
                str(self.video_time),
                "-f",
                "image2",
                "-vcodec",
                "mjpeg",
                "-vframes",
                "1",
                self.out_file
            ], stderr=STDOUT,
                shell=shell_status)
        except CalledProcessError as cpe:
            print("SCREEN OUT", cpe.output)


class AddSeparator(threading.Thread):

    def __init__(self, temp_dir, cut_number, input_video, video_info, duration, image_path, tmp_out):

        super().__init__()

        self.cut_number = cut_number
        self.input_video = input_video
        self.duration = duration
        self.tmp_out = tmp_out
        self.temp_dir = temp_dir
        self.video_info = video_info
        self.image_path = image_path

    def run(self):
        try:
            check_call([
                ffmpeg_path,
                "-y",
                "-loop",
                "1",
                # video stream
                "-i",
                self.image_path,
                "-c:v",
                "libx264",
                # duration
                "-t",
                "1",
                "-pix_fmt",
                "yuv444p",
                "-vf",
                "scale=" + str(self.video_info.width) + "x" + str(self.video_info.height) + ",setsar=1:1",
                self.temp_dir.name + path_separator + str(self.cut_number) + "_sep_no_sound.mp4"
            ], stderr=STDOUT,
                shell=shell_status)
        except CalledProcessError as cpe:
            print("IMAGE OUT", cpe.output)

        try:
            check_call([
                ffmpeg_path,
                "-y",
                # sound stream
                "-ar",
                "48000",
                "-ac",
                "2",
                "-f",
                "s16le",
                "-i",
                "silence.wav",
                "-i",
                self.temp_dir.name + path_separator + str(self.cut_number) + "_sep_no_sound.mp4",
                "-shortest",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-strict",
                "-2",
                self.temp_dir.name + path_separator + str(self.cut_number) + "_sep.mp4"
            ], stderr=STDOUT,
                shell=shell_status)
        except CalledProcessError as cpe:
            print("SOUND OUT", cpe.output)

        try:
            check_call([
                ffmpeg_path,
                # overwrite
                "-y",
                # separator
                "-i",
                self.temp_dir.name + path_separator + str(self.cut_number) + "_sep.mp4",
                # the clip
                "-i",
                self.input_video,
                # the concat filter
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-filter_complex",
                "[0:0] [0:1] [1:0] [1:1] concat=n=2:v=1:a=1 [v] [a]",
                self.tmp_out
            ], stderr=STDOUT,
                shell=shell_status)
        except CalledProcessError as cpe:
            print("CAT OUT", cpe.output)


class BurnLogo(threading.Thread):

    def __init__(self, temp_dir, cut_number, input_video, time_start, duration, tmp_out, video_info):

        super().__init__()

        self.temp_dir = temp_dir
        self.cut_number = cut_number
        self.input_video = input_video
        self.time_start = time_start
        self.duration = duration
        self.tmp_out = tmp_out
        self.video_info = video_info

    def run(self):

        # video height - image height - 20 padding
        bottom = self.video_info.height - 22 - 20
        left = 20

        # add the overlay to the pause image
        try:
            check_call([
                ffmpeg_path,
                # overwrite
                "-y",
                # start time
                "-ss",
                str(self.time_start),
                # video input
                "-i",
                self.input_video,
                # image input
                "-i",
                "watermark.png",
                # filter
                "-filter_complex",
                "[0:v][1:v] overlay=" + str(left) + ":" + str(bottom),
                "-pix_fmt",
                "yuv420p",
                # pass the audio
                "-c:a",
                "copy",
                # duration
                "-t",
                str(self.duration),
                # output
                self.tmp_out

            ], stderr=STDOUT,
                shell=shell_status)
        except CalledProcessError as cpe:
            print("BURN LOGO", cpe.output)


class AddOverlay(threading.Thread):

    def __init__(self, temp_dir, cut_number, input_video, video_info, video_time, image_path, tmp_out, pause_time):

        super().__init__()

        self.cut_number = cut_number
        self.input_video = input_video
        self.video_time = video_time
        self.tmp_out = tmp_out
        self.temp_dir = temp_dir
        self.video_info = video_info
        self.image_path = image_path
        self.pause_time = pause_time

    def run(self):

        # this is the logo position to burn
        # video height - image height - 20 padding
        bottom = self.video_info.height - 22 - 20
        left = 20

        # lets resize the image
        ori_img = Image.open(self.image_path)
        res_img = ori_img.resize((self.video_info.width, self.video_info.height), Image.ANTIALIAS)
        res_img.save(self.temp_dir.name + path_separator + str(self.cut_number) + "_overlay_res.png")

        # create the pause image
        try:
            check_call([
                ffmpeg_path,
                "-y",
                "-loop",
                "1",
                # video stream
                "-i",
                self.temp_dir.name + path_separator+ str(self.cut_number) + "_overlay_res.png",
                # we have the full image no need to get the screenshot
                # self.temp_dir.name + path_separator + str(self.cut_number) + "_thumb.png",
                "-c:v",
                "libx264",
                # duration
                "-t",
                str(self.pause_time),
                "-pix_fmt",
                "yuv444p",
                "-vf",
                "scale=" + str(self.video_info.width) + "x" + str(self.video_info.height) + ",setsar=1:1",
                self.temp_dir.name + path_separator + str(self.cut_number) + "_thumb.mp4"
            ], stderr=STDOUT,
                shell=shell_status)
        except CalledProcessError as cpe:
            print("IMAGE OUT", cpe.output)

        # add the overlay to the pause image
        try:
            check_call([
                ffmpeg_path,
                # overwrite
                "-y",
                # video input
                "-i",
                self.temp_dir.name + path_separator + str(self.cut_number) + "_thumb.mp4",
                # image input
                "-i",
                self.temp_dir.name + path_separator + str(self.cut_number) + "_overlay_res.png",
                # logo
                "-i",
                "watermark.png",
                # filter
                "-filter_complex",
                "overlay [tmp]; [tmp] overlay=" + str(left) + ":" + str(bottom),
                "-pix_fmt",
                "yuv420p",
                # pass the audio
                "-c:a",
                "copy",
                # output
                self.temp_dir.name + path_separator + str(self.cut_number) + "_thumb_overlay.mp4",

            ], stderr=STDOUT,
                shell=shell_status)
        except CalledProcessError as cpe:
            print("OVERLAY OUT", cpe.output)

        # add sound track to pause overlay
        try:
            check_call([
                ffmpeg_path,
                "-y",
                # sound stream
                "-ar",
                "48000",
                "-ac",
                "2",
                "-f",
                "s16le",
                "-i",
                "silence.wav",
                "-i",
                self.temp_dir.name + path_separator + str(self.cut_number) + "_thumb_overlay.mp4",
                "-shortest",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-strict",
                "-2",
                self.temp_dir.name + path_separator + str(self.cut_number) + "_thumb_overlay_sound.mp4"
            ], stderr=STDOUT,
                shell=shell_status)
        except CalledProcessError as cpe:
            print("SOUND OUT", cpe.output)

        # start_file = open(self.temp_dir.name + "\\" + str(self.cut_number) + "_start.log", "wb")
        try:
            # cut from the begging to the overlay
            check_call([
                # path to ffmpeg
                ffmpeg_path,
                # overwrite
                "-y",
                # input file
                "-i",
                self.input_video,
                # watermark
                "-i",
                "watermark.png",
                # duration
                "-t",
                str(max(self.video_time, 1)),
                # filter
                "-filter_complex",
                "[0:v][1:v] overlay=" + str(left) + ":" + str(bottom),
                "-pix_fmt",
                "yuv420p",
                # pass the audio
                "-c:a",
                "copy",
                # output file
                self.temp_dir.name + path_separator + str(self.cut_number) + "_start.mp4"
            ],
                stderr=STDOUT,
                shell=shell_status)
        except CalledProcessError as cpe:
            print("START OUT", cpe.output)

        # cut from the pause to the end
        check_call([
            # path to ffmpeg
            ffmpeg_path,
            # overwrite
            "-y",
            # input file
            "-i",
            self.input_video,
            # watermark
            "-i",
            "watermark.png",
            # start time
            "-ss",
            str(max(self.video_time, 1)),
            # filter
            "-filter_complex",
            "[0:v][1:v] overlay=" + str(left) + ":" + str(bottom),
            "-pix_fmt",
            "yuv420p",
            # pass the audio
            "-c:a",
            "copy",
            # output file
            self.temp_dir.name + path_separator + str(self.cut_number) + "_end.mp4"
        ],
            stderr=STDOUT,
            shell=shell_status)

        print(" ", " ", " ", " ", " VIDEO TIME: ", self.video_time)

        if self.video_info.has_sound:
            # and now join the three files
            # first stitch the start to the overlay
            try:
                check_call([
                    ffmpeg_path,
                    # overwrite
                    "-y",
                    # start
                    "-i",
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_start.mp4",
                    # the overlay
                    "-i",
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_thumb_overlay_sound.mp4",
                    # audio codec
                    "-c:a",
                    "aac",
                    "-strict",
                    "-2",
                    # the concat filter
                    "-map",
                    "[v]",
                    "-map",
                    "[a]",
                    "-filter_complex",
                    # "[0:0] setsar=1:1 [in1]; [0:1] [1:0] setsar=1:1 [in2]; [1:1] concat=n=2:v=1:a=1 [v] [a]",
                    "[0:0] setsar=sar=1/1 [in1]; [1:0] setsar=sar=1/1 [in2];"
                    "[in1][in2] concat [v]; [0:1][1:1] concat=v=0:a=1 [a]",
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_start_and_over.mp4"
                ], stderr=STDOUT,
                    shell=shell_status)
            except CalledProcessError as cpe:
                print("CAT OUT", cpe.output)

            # and now join the three files
            try:
                check_call([
                    ffmpeg_path,
                    # overwrite
                    "-y",
                    # start
                    "-i",
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_start_and_over.mp4",
                    # the overlay
                    "-i",
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_end.mp4",
                    # audio codec
                    "-c:a",
                    "aac",
                    "-strict",
                    "-2",
                    # the concat filter
                    "-map",
                    "[v]",
                    "-map",
                    "[a]",
                    "-filter_complex",
                    # "[0:0] [0:1] [1:0] [1:1] concat=n=2:v=1:a=1 [v] [a],scale=1270x720,setsar=1:1",
                    "[0:0] setsar=sar=1/1 [in1]; [1:0] setsar=sar=1/1 [in2];"
                    "[in1][in2] concat [v]; [0:1][1:1] concat=v=0:a=1 [a]",
                    self.tmp_out,
                ], stderr=STDOUT,
                    shell=shell_status)
            except CalledProcessError as cpe:
                print("CAT OUT", cpe.output)

        else:
            # NO AUDIO, SO DO NOT CONCAT [a] STREAM
            # and now join the three files
            # first stitch the start to the overlay
            try:
                check_call([
                    ffmpeg_path,
                    # overwrite
                    "-y",
                    # start
                    "-i",
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_start.mp4",
                    # the overlay
                    "-i",
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_thumb_overlay_sound.mp4",
                    # audio codec
                    "-c:a",
                    "aac",
                    "-strict",
                    "-2",
                    # the concat filter
                    "-map",
                    "[v]",
                    "-filter_complex",
                    "[0:0] setsar=sar=1/1 [in1]; [1:0] setsar=sar=1/1 [in2];"
                    "[in1][in2] concat [v]",
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_start_and_over.mp4"
                ], stderr=STDOUT,
                    shell=shell_status)
            except CalledProcessError as cpe:
                print("CAT OUT", cpe.output)

            # and now join the three files
            try:
                check_call([
                    ffmpeg_path,
                    # overwrite
                    "-y",
                    # start
                    "-i",
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_start_and_over.mp4",
                    # the overlay
                    "-i",
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_end.mp4",
                    # audio codec
                    "-c:a",
                    "aac",
                    "-strict",
                    "-2",
                    # the concat filter
                    "-map",
                    "[v]",
                    "-filter_complex",
                    "[0:0] setsar=sar=1/1 [in1]; [1:0] setsar=sar=1/1 [in2];"
                    "[in1][in2] concat [v]",
                    self.tmp_out,
                ], stderr=STDOUT,
                    shell=shell_status)
            except CalledProcessError as cpe:
                print("CAT OUT", cpe.output)


class AddMultipleDrawings(threading.Thread):

    def __init__(self, temp_dir, cut_number, input_video, video_info, tmp_out, drawings, pause_time, duration):

        super().__init__()

        self.cut_number = cut_number
        self.input_video = input_video
        self.tmp_out = tmp_out
        self.temp_dir = temp_dir
        self.video_info = video_info
        self.drawings = drawings
        self.pause_time = pause_time
        self.duration = duration

    def run(self):

        # this is the logo position to burn
        # video height - image height - 20 padding
        bottom = self.video_info.height - 22 - 20
        left = 20

        # cut the start of the clip that is until the first drawing time
        try:
            # cut from the begging to the overlay
            check_call([
                # path to ffmpeg
                ffmpeg_path,
                # overwrite
                "-y",
                # input file
                "-i",
                self.input_video,
                # watermark
                "-i",
                "watermark.png",
                # duration
                "-t",
                str(max(self.drawings[0].drawing_time, 1)),
                # filter
                "-filter_complex",
                "[0:v][1:v] overlay=" + str(left) + ":" + str(bottom),
                "-pix_fmt",
                "yuv420p",
                # pass the audio
                "-c:a",
                "copy",
                # output file
                self.temp_dir.name + path_separator + str(self.cut_number) + "_start.mp4"
            ],
                stderr=STDOUT,
                shell=shell_status)
        except CalledProcessError as cpe:
            print("START OUT", cpe.output)

        # cut from the last drawing to the end
        check_call([
            # path to ffmpeg
            ffmpeg_path,
            # overwrite
            "-y",
            # input file
            "-i",
            self.input_video,
            # watermark
            "-i",
            "watermark.png",
            # start time
            "-ss",
            str(max(self.drawings[len(self.drawings) - 1].drawing_time, 1)),
            # filter
            "-filter_complex",
            "[0:v][1:v] overlay=" + str(left) + ":" + str(bottom),
            "-pix_fmt",
            "yuv420p",
            # pass the audio
            "-c:a",
            "copy",
            # output file
            self.temp_dir.name + path_separator + str(self.cut_number) + "_end.mp4"
        ],
            stderr=STDOUT,
            shell=shell_status)

        drawing_number = 0
        print("DRAWWWINGS >>>>>>>>>>>>>>>>")
        for drawing in self.drawings:
            print(drawing.drawing_time)

            # self.status_bar.set(t("Adding drawing to item %i"), self.cut_number + 1)
            raw_png = base64.b64decode(drawing.bitmap)
            f = open(self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) +
                     "_overlay.png", "wb")
            f.write(raw_png)
            f.close()
            pil_png = Image.open(self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) +
                                 "_overlay.png")

            raw_jpeg = base64.b64decode(drawing.screenshot)
            jf = open(self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) +
                      "_screenshot.png", "wb")
            jf.write(raw_jpeg)
            jf.close()
            pil_jpeg = Image.open(self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) +
                                  "_screenshot.png")
            pil_jpeg_converted = pil_jpeg.convert(mode="RGBA")

            # and now join the two?
            pil_composite = Image.alpha_composite(pil_jpeg_converted, pil_png)
            pil_composite.save(self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) +
                               "_composite.png", "PNG")

            # lets resize the image
            ori_img = Image.open(self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) +
                                 "_composite.png")
            res_img = ori_img.resize((self.video_info.width, self.video_info.height), Image.ANTIALIAS)
            res_img.save(self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) +
                         "_overlay_res.png")

            # create the pause image
            try:
                check_call([
                    ffmpeg_path,
                    "-y",
                    "-loop",
                    "1",
                    # video stream
                    "-i",
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) + "_overlay_res.png",
                    # we have the full image no need to get the screenshot
                    # self.temp_dir.name + "\\" + str(self.cut_number) + "_thumb.png",
                    "-c:v",
                    "libx264",
                    # duration
                    "-t",
                    str(self.pause_time),
                    "-pix_fmt",
                    "yuv444p",
                    "-vf",
                    "scale=" + str(self.video_info.width) + "x" + str(self.video_info.height) + ",setsar=1:1",
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) + "_thumb.mp4"
                ], stderr=STDOUT,
                    shell=shell_status)
            except CalledProcessError as cpe:
                print("IMAGE OUT", cpe.output)

            # add the overlay to the pause image
            try:
                check_call([
                    ffmpeg_path,
                    # overwrite
                    "-y",
                    # video input
                    "-i",
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) + "_thumb.mp4",
                    # image input
                    "-i",
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) + "_overlay_res.png",
                    # logo
                    "-i",
                    "watermark.png",
                    # filter
                    "-filter_complex",
                    "overlay [tmp]; [tmp] overlay=" + str(left) + ":" + str(bottom),
                    "-pix_fmt",
                    "yuv420p",
                    # pass the audio
                    "-c:a",
                    "copy",
                    # output
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) + "_thumb_overlay.mp4",

                ], stderr=STDOUT,
                    shell=shell_status)
            except CalledProcessError as cpe:
                print("OVERLAY OUT", cpe.output)

            # add sound track to pause overlay
            try:
                check_call([
                    ffmpeg_path,
                    "-y",
                    # sound stream
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    "-f",
                    "s16le",
                    "-i",
                    "silence.wav",
                    "-i",
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) + "_thumb_overlay.mp4",
                    "-shortest",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-strict",
                    "-2",
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) +
                    "_thumb_overlay_sound.mp4"
                ], stderr=STDOUT,
                    shell=shell_status)
            except CalledProcessError as cpe:
                print("SOUND OUT", cpe.output)

            # if we are not at the last drawing?
            if drawing_number < len(self.drawings) - 1:
                # we cut the middle between one drawing and the other

                # check the start and duration
                middle_start = drawing.drawing_time;
                middle_duration = self.drawings[drawing_number + 1].drawing_time - middle_start

                # cut from the last drawing to the end
                check_call([
                    # path to ffmpeg
                    ffmpeg_path,
                    # overwrite
                    "-y",
                    # input file
                    "-i",
                    self.input_video,
                    # watermark
                    "-i",
                    "watermark.png",
                    # start time
                    "-ss",
                    str(max(middle_start, 1)),
                    # duration
                    "-t",
                    str(max(middle_duration, 1)),
                    # filter
                    "-filter_complex",
                    "[0:v][1:v] overlay=" + str(left) + ":" + str(bottom),
                    "-pix_fmt",
                    "yuv420p",
                    # pass the audio
                    "-c:a",
                    "copy",
                    # output file
                    self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) + "_middle.mp4"
                ],
                    stderr=STDOUT,
                    shell=shell_status)

            # do the next drawing
            drawing_number += 1

        if self.video_info.has_sound:
            # and join all the bits and pieces

            # now we must concat the whole thing, since we have a start, end, middle, and thumbs for all drawings
            for x in range(0, len(self.drawings)):

                # first drawing
                if x == 0:
                    # start by concatenating the start to the first thumb
                    try:
                        check_call([
                            ffmpeg_path,
                            # overwrite
                            "-y",
                            # start
                            "-i",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_start.mp4",
                            # the overlay
                            "-i",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x) + "_" +
                            "thumb_overlay_sound.mp4",
                            # audio codec
                            "-c:a",
                            "aac",
                            "-strict",
                            "-2",
                            # the concat filter
                            "-map",
                            "[v]",
                            "-map",
                            "[a]",
                            "-filter_complex",
                            # "[0:0] setsar=1:1 [in1]; [0:1] [1:0] setsar=1:1 [in2]; [1:1] concat=n=2:v=1:a=1 [v] [a]",
                            "[0:0] setsar=sar=1/1 [in1]; [1:0] setsar=sar=1/1 [in2];"
                            "[in1][in2] concat [v]; [0:1][1:1] concat=v=0:a=1 [a]",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x) + "_done.mp4"
                        ],
                            stderr=STDOUT,
                            shell=shell_status)
                    except CalledProcessError as cpe:
                        print("DRAWING JOIN START", cpe.output)

                # all the others except the last but including the first
                if x < len(self.drawings) - 1:
                    # add the middle between this drawing and the next
                    try:
                        check_call([
                            ffmpeg_path,
                            # overwrite
                            "-y",
                            # start
                            "-i",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x) + "_done.mp4",
                            # the overlay
                            "-i",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x) + "_" +
                            "middle.mp4",
                            # audio codec
                            "-c:a",
                            "aac",
                            "-strict",
                            "-2",
                            # the concat filter
                            "-map",
                            "[v]",
                            "-map",
                            "[a]",
                            "-filter_complex",
                            # "[0:0] setsar=1:1 [in1]; [0:1] [1:0] setsar=1:1 [in2]; [1:1] concat=n=2:v=1:a=1 [v] [a]",
                            "[0:0] setsar=sar=1/1 [in1]; [1:0] setsar=sar=1/1 [in2];"
                            "[in1][in2] concat [v]; [0:1][1:1] concat=v=0:a=1 [a]",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x + 1) + "_" +
                            "_after_middle.mp4"
                        ],
                            stderr=STDOUT,
                            shell=shell_status)
                    except CalledProcessError as cpe:
                        print("DRAWING JOIN MIDDLE " + str(x), cpe.output)

                    # add the next drawing
                    try:
                        check_call([
                            ffmpeg_path,
                            # overwrite
                            "-y",
                            # start
                            "-i",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x + 1) + "_" +
                            "_after_middle.mp4",
                            # the overlay
                            "-i",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x + 1) + "_" +
                            "thumb_overlay_sound.mp4",
                            # audio codec
                            "-c:a",
                            "aac",
                            "-strict",
                            "-2",
                            # the concat filter
                            "-map",
                            "[v]",
                            "-map",
                            "[a]",
                            "-filter_complex",
                            # "[0:0] setsar=1:1 [in1]; [0:1] [1:0] setsar=1:1 [in2]; [1:1] concat=n=2:v=1:a=1 [v] [a]",
                            "[0:0] setsar=sar=1/1 [in1]; [1:0] setsar=sar=1/1 [in2];"
                            "[in1][in2] concat [v]; [0:1][1:1] concat=v=0:a=1 [a]",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x + 1) + "_done.mp4"
                        ],
                            stderr=STDOUT,
                            shell=shell_status)
                    except CalledProcessError as cpe:
                        print("DRAWING JOIN START", cpe.output)

                last_drawing = self.drawings[len(self.drawings) - 1]
                last_drawing_delta = self.duration - last_drawing.drawing_time
                if last_drawing_delta > 1:
                    # last drawing
                    if x == len(self.drawings) - 1:
                        # just add the end, since this drawing was joined in the last step
                        try:
                            check_call([
                                ffmpeg_path,
                                # overwrite
                                "-y",
                                # start
                                "-i",
                                self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x) + "_done.mp4",
                                # the overlay
                                "-i",
                                self.temp_dir.name + path_separator + str(self.cut_number) + "_" + "end.mp4",
                                # audio codec
                                "-c:a",
                                "aac",
                                "-strict",
                                "-2",
                                # the concat filter
                                "-map",
                                "[v]",
                                "-map",
                                "[a]",
                                "-filter_complex",
                                # "[0:0] setsar=1:1 [in1]; [0:1] [1:0] setsar=1:1 [in2]; [1:1] concat=n=2:v=1:a=1 [v] [a]",
                                "[0:0] setsar=sar=1/1 [in1]; [1:0] setsar=sar=1/1 [in2];"
                                "[in1][in2] concat [v]; [0:1][1:1] concat=v=0:a=1 [a]",
                                self.tmp_out,
                            ],
                                stderr=STDOUT,
                                shell=shell_status)
                        except CalledProcessError as cpe:
                            print("DRAWING JOIN START", cpe.output)

        else:
            # and join all the bits and pieces

            # now we must concat the whole thing, since we have a start, end, middle, and thumbs for all drawings
            for x in range(0, len(self.drawings)):

                # first drawing
                if x == 0:
                    # start by concatenating the start to the first thumb
                    try:
                        check_call([
                            ffmpeg_path,
                            # overwrite
                            "-y",
                            # start
                            "-i",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_start.mp4",
                            # the overlay
                            "-i",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x) + "_" +
                            "thumb_overlay_sound.mp4",
                            # audio codec
                            "-c:a",
                            "aac",
                            "-strict",
                            "-2",
                            # the concat filter
                            "-map",
                            "[v]",
                            "-filter_complex",
                            "[0:0] setsar=sar=1/1 [in1]; [1:0] setsar=sar=1/1 [in2];"
                            "[in1][in2] concat [v]",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x) + "_done.mp4"
                        ],
                            stderr=STDOUT,
                            shell=shell_status)
                    except CalledProcessError as cpe:
                        print("DRAWING JOIN START", cpe.output)

                # all the others except the last but including the first
                if x < len(self.drawings) - 1:
                    # add the middle between this drawing and the next
                    try:
                        check_call([
                            ffmpeg_path,
                            # overwrite
                            "-y",
                            # start
                            "-i",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x) + "_done.mp4",
                            # the overlay
                            "-i",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x) + "_" +
                            "middle.mp4",
                            # audio codec
                            "-c:a",
                            "aac",
                            "-strict",
                            "-2",
                            # the concat filter
                            "-map",
                            "[v]",
                            "-filter_complex",
                            "[0:0] setsar=sar=1/1 [in1]; [1:0] setsar=sar=1/1 [in2];"
                            "[in1][in2] concat [v]",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x + 1) + "_" +
                            "_after_middle.mp4"
                        ],
                            stderr=STDOUT,
                            shell=shell_status)
                    except CalledProcessError as cpe:
                        print("DRAWING JOIN MIDDLE " + str(x), cpe.output)

                    # add the next drawing
                    try:
                        check_call([
                            ffmpeg_path,
                            # overwrite
                            "-y",
                            # start
                            "-i",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x + 1) + "_" +
                            "_after_middle.mp4",
                            # the overlay
                            "-i",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x + 1) + "_" +
                            "thumb_overlay_sound.mp4",
                            # audio codec
                            "-c:a",
                            "aac",
                            "-strict",
                            "-2",
                            # the concat filter
                            "-map",
                            "[v]",
                            "-filter_complex",
                            "[0:0] setsar=sar=1/1 [in1]; [1:0] setsar=sar=1/1 [in2];"
                            "[in1][in2] concat [v]",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x + 1) + "_done.mp4"
                        ],
                            stderr=STDOUT,
                            shell=shell_status)
                    except CalledProcessError as cpe:
                        print("DRAWING JOIN START", cpe.output)

                # last drawing
                if x == len(self.drawings) - 1:
                    # just add the end, since this drawing was joined in the last step
                    try:
                        check_call([
                            ffmpeg_path,
                            # overwrite
                            "-y",
                            # start
                            "-i",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x) + "_done.mp4",
                            # the overlay
                            "-i",
                            self.temp_dir.name + path_separator + str(self.cut_number) + "_" + "end.mp4",
                            # audio codec
                            "-c:a",
                            "aac",
                            "-strict",
                            "-2",
                            # the concat filter
                            "-map",
                            "[v]",
                            "-filter_complex",
                            "[0:0] setsar=sar=1/1 [in1]; [1:0] setsar=sar=1/1 [in2];"
                            "[in1][in2] concat [v]",
                            self.tmp_out,
                        ],
                            stderr=STDOUT,
                            shell=shell_status)
                    except CalledProcessError as cpe:
                        print("DRAWING JOIN START", cpe.output)


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
            shell=shell_status)


class CutFastCopy(threading.Thread):

    def __init__(self, temp_dir, cut_number, video_path, time_start, duration, tmp_out):

        super().__init__()

        self.cut_number = cut_number
        self.video_path = video_path
        self.time_start = time_start
        self.duration = duration
        self.tmp_out = tmp_out
        self.temp_dir = temp_dir

    def run(self):

        # log_path = self.temp_dir.name + path_separator + str(self.cut_number) + "_fast_cut.log"
        # log_file = open(log_path, "wb")

        out = check_call([
            # path to ffmpeg
            ffmpeg_path,
            # overwrite
            "-y",
            # input file
            "-i",
            self.video_path,
            # duration
            "-t",
            str(self.duration),
            # codec
            "-c",
            "copy",
            "-bsf:v",
            "h264_mp4toannexb",
            "-f",
            "mpegts",
            # start time
            "-ss",
            str(self.time_start),
            # output file
            self.tmp_out
        ],
            stderr=STDOUT,
            shell=shell_status
            )


class CutWithKeyFrames(threading.Thread):

    def __init__(self, temp_dir, cut_number, video_path, time_start, duration, tmp_out, key_frames):

        super().__init__()

        self.cut_number = cut_number
        self.video_path = video_path
        self.time_start = time_start
        self.duration = duration
        self.tmp_out = tmp_out
        self.temp_dir = temp_dir
        self.key_frames = key_frames

    def run(self):

        # log_path = self.temp_dir.name + path_separator + str(self.cut_number) + "_cut_key_frames.log"
        # log_file = open(log_path, "wb")

        out = check_call([
            # path to ffmpeg
            ffmpeg_path,
            # overwrite
            "-y",
            # start time
            "-ss",
            str(self.time_start),
            # duration
            "-t",
            str(self.duration),
            # input file
            "-i",
            self.video_path,
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
            self.tmp_out
        ],
            stderr=STDOUT,
            shell=shell_status)


class EncodeSubtitles(threading.Thread):

    def __init__(self, temp_dir, cut_number, video_path, video_info, time_start, duration, comments, tmp_out, font_size):

        super().__init__()

        self.cut_number = cut_number
        self.video_path = video_path
        self.time_start = time_start
        self.duration = duration
        self.comments = comments
        self.tmp_out = tmp_out
        self.temp_dir = temp_dir
        self.video_info = video_info
        self.font_size = font_size

    def run(self):

        # write srt file
        # ass_log_path = self.temp_dir.name + path_separator + str(self.cut_number) + ".ass.log"
        # ass_log_file = open(ass_log_path, "wb")

        # video height - image height - 20 padding
        bottom = self.video_info.height - 22 - 20
        left = 20

        ass_contents = "[Script Info]\n"
        ass_contents += "PlayResY: 600\n"
        ass_contents += "\n"
        ass_contents += "[V4 Styles]\n"
        ass_contents += "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, TertiaryColour," \
                        "BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment," \
                        "MarginL, MarginR, MarginV, AlphaLevel, Encoding\n"
        ass_contents += "Style: Default,Arial," + str(self.font_size) + ",16777215,65535,65535,"\
                        "-2147483640,0,0,1,3,0,2,30,30,30,0,0\n"
        ass_contents += "\n"
        ass_contents += "[Events]\n"
        ass_contents += "Format: Marked, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        ass_contents += "Dialogue: Marked=0,0:00:00.00,5:00:00.00,Default,,0000,0000,0000,," + self.comments + "\n"

        ass_path = self.temp_dir.name + path_separator + str(self.cut_number) + ".ass"
        ass_file = open(ass_path, "wb")
        ass_file.write(ass_contents.encode("utf8"))
        ass_file.close()

        escaped_ass_path = ""
        if platform.system() == "Darwin":
            escaped_ass_path = ass_path
        else:
            escaped_ass_path = ass_path.replace("\\", "\\\\").replace(":", "\:").replace(" ", "\ ")

        try:
            check_call([
                ffmpeg_path,
                # overwrite
                "-y",
                # start time
                "-ss",
                str(self.time_start),
                # input file
                "-i",
                self.video_path,
                "-t",
                str(self.duration),
                # codec
                "-codec:v",
                "libx264",
                "-crf",
                "23",
                "-codec:a",
                "copy",
                "-vf",
                "ass=" + "'" + escaped_ass_path + "'",
                # self.tmp_out
                self.temp_dir.name + path_separator + str(self.cut_number) + "_no_water.mp4"
            ],
                shell=shell_status,
                universal_newlines=True,
                stderr=STDOUT,
            )
        except CalledProcessError as cpe:
            print("SUB ASS OUT", cpe.output)

        try:
            check_call([
                ffmpeg_path,
                # overwrite
                "-y",
                # start time
                # input file
                "-i",
                self.temp_dir.name + path_separator + str(self.cut_number) + "_no_water.mp4",
                # watermark
                "-i",
                "watermark.png",
                # filter
                "-filter_complex",
                "[0:v][1:v] overlay=" + str(left) + ":" + str(bottom),
                "-pix_fmt",
                "yuv420p",
                # pass the audio
                "-c:a",
                "copy",
                # self.tmp_out
                self.tmp_out
            ],
                shell=shell_status,
                universal_newlines=True,
                stderr=STDOUT,
            )
        except CalledProcessError as cpe:
            print("SUB ASS OUT", cpe.output)


class FileChooser(object):

    def __init__(self):

        settings_path = os.path.expanduser("~/voconverter.conf")

        self.settings = EasySettings(settings_path)

        pause_frame = Frame(root)
        pause_frame.pack(fill=X, padx="5")

        pause_label = Label(pause_frame, text=t("Drawings Pause Time"))
        pause_label.pack(side=LEFT)

        self.pause_duration = Scale(pause_frame, from_=1, to=10, orient=HORIZONTAL, length="180")
        self.pause_duration.pack(side=RIGHT)
        # default value
        if self.settings.has_option("pause"):
            pause_val = self.settings.get("pause")
        else:
            pause_val = 4
        self.pause_duration.set(pause_val)

        font_frame = Frame(root)
        font_frame.pack(fill=X, padx="5")

        font_size_label = Label(font_frame, text=t("Font Size"))
        font_size_label.pack(side=LEFT)

        slow_and_better_frame = Frame(root)
        slow_and_better_frame.pack(fill=X, padx=5)

        self.slow_and_better = IntVar(value=0)
        slow_and_better_cb = Checkbutton(slow_and_better_frame, text=t("Slow but better"),
                                         variable=self.slow_and_better)
        slow_and_better_cb.pack(side=LEFT)

        self.font_size = Scale(font_frame, from_=10, to=50, orient=HORIZONTAL, length="180")
        self.font_size.pack(side=RIGHT)
        # default value
        if self.settings.has_option("font_size"):
            font_val = self.settings.get("font_size")
        else:
            font_val = 30
        self.font_size.set(font_val)

        # key_frame_frame = Frame(root)
        # key_frame_frame.pack(fill=X, padx="5")
        #
        # key_frame_label = Label(key_frame_frame, text=t("Key Frames"))
        # key_frame_label.pack(side=LEFT)
        #
        # self.key_frame_scale = Scale(key_frame_frame, from_=1, to=24, orient=HORIZONTAL, length="180")
        # self.key_frame_scale.set(12)
        # self.key_frame_scale.pack(side=LEFT)

        self.meter = Meter(root, bg="white", fillcolor="light blue")
        self.meter.pack(pady="10", padx="10")

        destination_frame = Frame(root)
        destination_frame.pack(padx="10", pady="10", fill=X)

        dest_label = Label(destination_frame, text=t("Destination:"))
        dest_label.pack(side=LEFT)

        if self.settings.has_option("destination_path"):
            self.final_destination_path = self.settings.get("destination_path")
        else:
            self.final_destination_path = os.path.expanduser("~/Desktop")

        self.destination_path = Label(destination_frame, text=self.final_destination_path)
        self.destination_path.pack(side=LEFT)

        self.dest_btn = Button(destination_frame, text=t("Choose"), command=self.choose_destination)
        self.dest_btn.pack(side=RIGHT)

        btn_frame = Frame(root)
        btn_frame.pack(padx="10", pady="10")

        btn = Button(btn_frame, text=t("Open File"), command=self.open_dialog)
        btn.pack(side=LEFT, padx="10")

        another = Button(btn_frame, text=t("Quit"), command=self.quit_app)
        another.pack(side=LEFT, padx="10")

        self.status_bar = StatusBar(root)
        self.status_bar.pack(fill=X)

        # get the version from the ini
        config = configparser.ConfigParser()
        config.read("version.ini")
        version = config["Vo Converter"]["version"]
        date = config["Vo Converter"]["date"]
        print("VERSION, DATE>>", version, date)
        self.status_bar.set(t("Version: %s , date: %s"), version, date)

        self.temp_dir = tempfile.TemporaryDirectory()
        self.num_items = 0

        self.base_name = ""

        self.video_info = ""

        self.start_time = ""
        self.end_time = ""

        self.final_path = ""

        version_thr = CheckForUpdate(version, self.temp_dir)
        version_thr.start()

    def open_dialog(self):

        initial_dir = os.path.expanduser("~/Documents/VideoObserver/Playlist")

        fn = filedialog.askopenfilename(filetypes=((t("VO Playlist"), "*.vopl"),
                                                   (t("All Files"), "*.*")),
                                        initialdir=initial_dir
                                        )
        self.parse_playlist(filename=fn)

    def quit_app(self):

        # save settings for next time
        self.settings.set("pause", self.pause_duration.get())
        self.settings.set("font_size", self.font_size.get())
        self.settings.set("destination_path", self.final_destination_path)

        self.settings.save()

        # Cleanup
        self.temp_dir.cleanup()

        sys.exit(0)

    def choose_destination(self):
        # get dir from user, using the saved dir as the starting point
        fn = filedialog.askdirectory(initialdir=self.final_destination_path)

        # if fn is the empty string the user pressed cancel, so no need to do the checks
        if fn != '':
            # check if the directory exists and is writable
            try:
                file = fn + '/test_write.txt'
                test = open(file, 'w')
                # if we get here the file is writable or we would be in the except block
                # so cleanup
                test.close()
                os.remove(file)
                # and this means we can save the directory
                self.final_destination_path = fn
                self.destination_path.config(text=fn)
            except IOError as ioe:
                print('directory not writable: ' + str(ioe))
                # so we better popup a warning
                warn_pop = Toplevel(padx=20, pady=20)
                warn_pop.title(t("Error"))
                warn_pop.iconbitmap("icon.ico")

                warn_msg = Label(warn_pop, text=t("The directory you selected is not valid. Write error.") + " " + fn)
                warn_msg.pack()

                warn_btn = Button(warn_pop, text=t("Ok"), command=warn_pop.destroy)
                warn_btn.pack()

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
            ], stderr=STDOUT, shell=shell_status, universal_newlines=True)

            info_json = json.loads(out)

            has_sound = False

            video_info = VideoInfo()
            for stream in info_json["streams"]:
                if stream["codec_type"] == "video":
                    video_info.set_w_and_h(stream["width"], stream["height"])
                if stream["codec_type"] == "audio":
                    has_sound = True

            video_info.set_has_sound(has_sound)
            return video_info

        except CalledProcessError as cpe:
            print("FFPROBE OUT", cpe.output)

    def parse_playlist(self, filename):

        tree = xmlParser.parse(filename)
        base = tree.getroot()

        # if the file name has spaces we end up with %20 in the url
        video_path = urllib.parse.unquote(base.get("video_path"))

        if platform.system() == "Darwin":
            # now if we have the file:// present we remove it
            video_path = video_path.replace("file://", "")
        else:
            video_path = video_path.replace("file:///", "")

        # first we check for the file existence
        if not os.path.isfile(video_path):
            # then we need to ask the user for a new file
            fn = filedialog.askopenfile(mode='r', title=t("Video file not found, please select another"))
            if fn is not None:
                video_path = fn.name
            else:
                return

        # record start time
        self.start_time = time.time()

        # to keep the cut files
        self.status_bar.set("%s", t("Processing..."))

        # we have a name so make sure we create the dir
        if not os.path.exists(self.temp_dir.name):
            os.makedirs(self.temp_dir.name)

        self.base_name = base.get("name")
        if self.base_name is None:
            self.base_name = os.path.basename(filename)

        # get playlist length
        play_len = len(base.findall('.items/item'))
        print("NItems>> ", play_len)
        # we say that the join is the last step
        play_len += 1
        self.num_items = play_len
        self.meter.set(0.0, t("Converting: ") + self.base_name + " " + "0%")

        self.video_info = self.get_video_info(video_path)

        print("VPath>> ", video_path)
        print("Resolution>>>", str(self.video_info.width) + "x" + str(self.video_info.height))
        print("Has Sound>>>", self.video_info.has_sound)

        print("SLOW AND BETTER>>", self.slow_and_better.get() == 1)

        print("")

        cut_number = 0
        # start parsing each item
        for child in base.findall('.items/item'):

            self.status_bar.set(t("Processing item %i"), cut_number + 1)

            item_type = child.find("type").text
            print("ItemType>> ", item_type)

            time_start = ""
            time_end = ""
            real_time_start = ""
            real_time_end = ""

            comments = ""
            enable_comments = True
            has_comments = False

            has_drawing = False
            drawing = ""
            drawing_time = ""
            screenshot = ""

            has_multiple_drawings = False
            multiple_drawings = []

            if item_type == "ga":
                real_time_start = float(child.find("game_action").find("video_time_start").text)
                time_start = int(real_time_start)
                real_time_end = float(child.find("game_action").find("video_time_end").text)
                time_end = int(real_time_end)
                comments = child.find("game_action").find("comments").text
                ec = child.find("game_action").find("comments_enabled")
                if ec is not None:
                    enable_comments = ec.text
                # one drawing only for backwards compatibility
                drw = child.find("game_action").find("drawing")
                if drw is not None:
                    drawing = drw.find("bitmap").text
                    drawing_time = float(drw.find("time").text) - real_time_start
                    screenshot = drw.find("screenshot").text

                    the_drawing = Drawing(uid="None", screenshot=screenshot,
                                          bitmap=drawing, drawing_time=drawing_time)
                    multiple_drawings.append(the_drawing)

                    has_multiple_drawings = True
                # multiple drawings going forward
                temp_multiple_drawings = child.find("game_action").find("drawings")
                if temp_multiple_drawings is not None:
                    has_multiple_drawings = True
                    # loop the drawings and add to array
                    for temp_drawing in temp_multiple_drawings:
                        temp_uid = temp_drawing.find("uid").text
                        temp_screenshot = temp_drawing.find("screenshot").text
                        temp_bitmap = temp_drawing.find("bitmap").text
                        # we need the time within the clip and not relative to the full video
                        temp_time = float(temp_drawing.find("time").text) - real_time_start
                        the_drawing = Drawing(uid=temp_uid, screenshot=temp_screenshot,
                                              bitmap=temp_bitmap, drawing_time=temp_time)
                        multiple_drawings.append(the_drawing)

            if item_type == "cue":
                real_time_start = float(child.find("action_cue").find("starting_time").text)
                time_start = int(real_time_start)
                real_time_end = float(child.find("action_cue").find("ending_time").text)
                time_end = int(real_time_end)
                comments = child.find("action_cue").find("comments").text
                ec = child.find("action_cue").find("comments_enabled")
                if ec is not None:
                    enable_comments = ec.text
                drw = child.find("action_cue").find("drawing")
                if drw is not None:
                    drawing = drw.find("bitmap").text
                    drawing_time = float(drw.find("time").text) - real_time_start
                    screenshot = drw.find("screenshot").text

                    the_drawing = Drawing(uid="None", screenshot=screenshot,
                                          bitmap=drawing, drawing_time=drawing_time)
                    multiple_drawings.append(the_drawing)

                    has_multiple_drawings = True
                # multiple drawings going forward
                temp_multiple_drawings = child.find("action_cue").find("drawings")
                if temp_multiple_drawings is not None:
                    has_multiple_drawings = True
                    # loop the drawings and add to array
                    for temp_drawing in temp_multiple_drawings:
                        temp_uid = temp_drawing.find("uid").text
                        temp_screenshot = temp_drawing.find("screenshot").text
                        temp_bitmap = temp_drawing.find("bitmap").text
                        # we need the time within the clip and not relative to the full video
                        temp_time = float(temp_drawing.find("time").text) - real_time_start
                        the_drawing = Drawing(uid=temp_uid, screenshot=temp_screenshot,
                                              bitmap=temp_bitmap, drawing_time=temp_time)
                        multiple_drawings.append(the_drawing)

            # add some padding
            # time_start += 2
            # time_end += 2

            print("TimeStart>> ", time_start)
            print("TimeEnd>> ", time_end)
            print("Comments>> ", comments)
            print("Enable Comments>> ", enable_comments)

            print("")

            # for drw in multiple_drawings:
            #    print(drw.drawing_time)

            duration = time_end - time_start
            real_duration = real_time_end - real_time_start
            tmp_out = self.temp_dir.name + path_separator + str(cut_number) + ".mp4"

            # now we see what we need to do...

            #  first check for comments
            if (comments is not None and enable_comments == "true") or self.slow_and_better.get() == 1:
                if self.slow_and_better.get() == 1 and comments is None:
                    self.status_bar.set(t("Better converting %i"), cut_number + 1)

                    burn_thr = BurnLogo(temp_dir=self.temp_dir, cut_number=cut_number, input_video=video_path,
                                        time_start=time_start, duration=duration,
                                        tmp_out=self.temp_dir.name + path_separator + str(cut_number) + "_comments.mp4",
                                        video_info=self.video_info)
                    burn_thr.start()
                    while burn_thr.is_alive():
                        dummy_event = threading.Event()
                        dummy_event.wait(timeout=1)

                else:
                    self.status_bar.set(t("Adding subtitles to item %i"), cut_number + 1)

                    has_comments = True
                    sub_thr = EncodeSubtitles(temp_dir=self.temp_dir, cut_number=cut_number, video_path=video_path,
                                              video_info=self.video_info,
                                              time_start=time_start, duration=duration, comments=comments,
                                              tmp_out=self.temp_dir.name + path_separator + str(cut_number) + "_comments.mp4",
                                              font_size=self.font_size.get())
                    sub_thr.start()
                    while sub_thr.is_alive():
                        # print("sleeping...")
                        dummy_event = threading.Event()
                        dummy_event.wait(timeout=1)

            elif has_drawing or has_multiple_drawings:
                # we need to convert without fast copy so that the further cuts work out right
                key_thr = CutWithKeyFrames(temp_dir=self.temp_dir, cut_number=cut_number, video_path=video_path,
                                           time_start=real_time_start, duration=real_duration,
                                           tmp_out=self.temp_dir.name + path_separator + str(cut_number) + "_comments.mp4",
                                           key_frames=12)
                key_thr.start()
                while key_thr.is_alive():
                    dummy_event = threading.Event()
                    dummy_event.wait(timeout=1)
            else:
                # just cut in time since we need no further processing
                self.status_bar.set(t("Fast cutting item %i"), cut_number + 1)
                fast_cut_thr = CutFastCopy(temp_dir=self.temp_dir, cut_number=cut_number, video_path=video_path,
                                           time_start=time_start, duration=duration,
                                           tmp_out=self.temp_dir.name + path_separator + str(cut_number) + "_comments.mp4")
                fast_cut_thr.start()
                while fast_cut_thr.is_alive():
                    dummy_event = threading.Event()
                    dummy_event.wait(timeout=1)

            # do we add an overlay?
            if has_drawing:
                self.status_bar.set(t("Adding drawing to item %i"), cut_number + 1)
                raw_png = base64.b64decode(drawing)
                f = open(self.temp_dir.name + path_separator + str(cut_number) + "_overlay.png", "wb")
                f.write(raw_png)
                f.close()
                pil_png = Image.open(self.temp_dir.name + path_separator + str(cut_number) + "_overlay.png")

                raw_jpeg = base64.b64decode(screenshot)
                jf = open(self.temp_dir.name + path_separator + str(cut_number) + "_screenshot.png", "wb")
                jf.write(raw_jpeg)
                jf.close()
                pil_jpeg = Image.open(self.temp_dir.name + path_separator + str(cut_number) + "_screenshot.png")
                pil_jpeg_converted = pil_jpeg.convert(mode="RGBA")

                # and now join the two?
                pil_composite = Image.alpha_composite(pil_jpeg_converted, pil_png)
                pil_composite.save(self.temp_dir.name + path_separator + str(cut_number) + "_composite.png", "PNG")

                # sanity check so that if we have time after the end of the clop the conversion still works
                # more or less that is...
                video_time = float(drawing_time) - time_start
                if video_time > duration:
                    video_time = duration - 1

                overlay_thr = AddOverlay(temp_dir=self.temp_dir, cut_number=cut_number,
                                         input_video=self.temp_dir.name + path_separator + str(cut_number) + "_comments.mp4",
                                         video_info=self.video_info,
                                         video_time=video_time,
                                         tmp_out=self.temp_dir.name + path_separator + str(cut_number) + "_overlay.mp4",
                                         image_path=self.temp_dir.name + path_separator + str(cut_number) + "_composite.png",
                                         pause_time=self.pause_duration.get())
                overlay_thr.start()
                while overlay_thr.is_alive():
                    # print("sleeping...")
                    dummy_event = threading.Event()
                    dummy_event.wait(timeout=1)

            if has_multiple_drawings:
                multiple_thr = AddMultipleDrawings(temp_dir=self.temp_dir,
                                                   cut_number=cut_number,
                                                   input_video=self.temp_dir.name + path_separator + str(cut_number) +
                                                   "_comments.mp4",
                                                   video_info=self.video_info,
                                                   tmp_out=self.temp_dir.name + path_separator + str(cut_number) + "_overlay.mp4",
                                                   drawings=multiple_drawings,
                                                   pause_time=self.pause_duration.get(),
                                                   duration=real_duration)
                multiple_thr.start()
                while multiple_thr.is_alive():
                    # print("sleeping...")
                    dummy_event = threading.Event()
                    dummy_event.wait(timeout=1)

            # lastly we convert to fast copy for the final join
            if has_drawing or has_multiple_drawings:
                fast_copy_input = self.temp_dir.name + path_separator + str(cut_number) + "_overlay.mp4"
            else:
                fast_copy_input = self.temp_dir.name + path_separator + str(cut_number) + "_comments.mp4"

            fast_copy_thr = ConvertToFastCopy(temp_dir=self.temp_dir, cut_number=cut_number,
                                              input_video=fast_copy_input, tmp_out=tmp_out)
            fast_copy_thr.start()
            while fast_copy_thr.is_alive():
                self.status_bar.set(t("Finishing item %i"), cut_number + 1)
                # print("sleeping...")
                dummy_event = threading.Event()
                dummy_event.wait(timeout=1)

            # calc progress
            progress = cut_number / self.num_items
            progress_str = str(math.ceil(progress * 100))
            self.meter.set(progress, t("Converting: ") + self.base_name + " " + progress_str + "%")

            cut_number += 1

        self.status_bar.set(t("Joining final video"))
        # JOIN THE THINGS
        join_args = []
        # path to ffmpeg
        join_args.append(ffmpeg_path)
        # overwrite
        join_args.append("-y")
        # input
        join_args.append("-i")
        # the concat files
        concat = "concat:"
        for x in range(0, cut_number):
            concat += self.temp_dir.name + path_separator + str(x) + ".mp4" + "|"
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
        out_filename = self.base_name.replace(".vopl", "")
        # put it on desktop for now
        join_args.append("" + self.final_destination_path + path_separator + out_filename + ".mp4" + "")

        self.final_path = self.final_destination_path + path_separator + out_filename + ".mp4"

        # sys.stdout.write("JOINARGS>>" + ' '.join(join_args))

        # join_log_path = self.temp_dir.name + path_separator + "join.log"
        # join_log_file = open(join_log_path, "wb")

        try:
            out = check_call(join_args, stderr=STDOUT, shell=False)
        except CalledProcessError as cpe:
            print("ERROR>>", cpe.output)

        self.meter.set(1, t("Done: ") + self.base_name + " " + "100" + "%")

        self.end_time = time.time()
        time_delta = self.end_time - self.start_time

        seconds = int(time_delta % 60)
        minutes = int(time_delta / 60)
        hours = int(time_delta / (60 * 60))

        self.status_bar.set(t("Done in %s:%s:%s ..."), format(hours, "02d"),
                            format(minutes, "02d"), format(seconds, "02d"))

        print("")
        print("")
        print("")
        print("")
        print("")
        print(t("Done in"), format(hours, "02d"), ":", format(minutes, "02d"), ":", format(seconds, "02d"))

        done_pop = Toplevel(padx=20, pady=20)
        done_pop.title(t("Done..."))
        done_pop.iconbitmap("icon.ico")

        done_msg = Label(done_pop, text=t("Playlist done..."))
        done_msg.pack()

        done_btn = Button(done_pop, text=t("Ok"), command=done_pop.destroy)
        done_btn.pack()

        open_btn = Button(done_pop, text=t("Open Video"), command=self.open_file_with_app)
        open_btn.pack()

    def open_file_with_app(self):
        # os.system("start " + "\"" + self.final_path + "\"")
        if platform.system() == "Darwin":
            call(["open", self.final_path])
        else:
            os.startfile(self.final_path)

# CODE FOR PROGRESS BAR
class Meter(Frame):
    def __init__(self, master, width=300, height=20, bg='white', fillcolor='orchid1',
                 value=0.0, text=None, font=None, textcolor='black', *args, **kw):
        Frame.__init__(self, master, bg=bg, width=width, height=height, *args, **kw)
        self._value = value

        self._canv = Canvas(self, bg=self['bg'], width=self['width'], height=self['height'],
                            highlightthickness=0, relief='flat', bd=0)
        self._canv.pack(fill='both', expand=1)
        self._rect = self._canv.create_rectangle(0, 0, 0, self._canv.winfo_reqheight(), fill=fillcolor,
                                                 width=0)
        self._text = self._canv.create_text(self._canv.winfo_reqwidth()/2, self._canv.winfo_reqheight()/2,
                                            text='', fill=textcolor)
        if font:
            self._canv.itemconfigure(self._text, font=font)

        self.set(value, text)
        self.bind('<Configure>', self._update_coords)

    def _update_coords(self, event):
        # Updates the position of the text and rectangle inside the canvas when the size of
        # the widget gets changed.
        # looks like we have to call update_idletasks() twice to make sure
        # to get the results we expect
        self._canv.update_idletasks()
        self._canv.coords(self._text, self._canv.winfo_width()/2, self._canv.winfo_height()/2)
        self._canv.coords(self._rect, 0, 0, self._canv.winfo_width()*self._value, self._canv.winfo_height())
        self._canv.update_idletasks()

    def get(self):
        return self._value, self._canv.itemcget(self._text, 'text')

    def set(self, value=0.0, text=None):
        # make the value failsafe:
        if value < 0.0:
            value = 0.0
        elif value > 1.0:
            value = 1.0
        self._value = value
        if text is None:
            # if no text is specified use the default percentage string:
            text = str(int(round(100 * value))) + ' %'
        self._canv.coords(self._rect, 0, 0, self._canv.winfo_width()*value, self._canv.winfo_height())
        self._canv.itemconfigure(self._text, text=text)
        self._canv.update_idletasks()


# Code for status bar
class StatusBar(Frame):

    def __init__(self, master):
        Frame.__init__(self, master)
        self.label = Label(self, bd=1, relief=SUNKEN, anchor=W)
        self.label.pack(fill=X)

    def set(self, fmt, *args):
        self.label.config(text=fmt % args)
        self.label.update_idletasks()

    def clear(self):
        self.label.config(text="")
        self.label.update_idletasks()

if __name__ == '__main__':
    fc = FileChooser()
    mainloop()
