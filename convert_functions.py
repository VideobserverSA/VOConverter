import threading
from subprocess import *
import subprocess
import re
import platform
from qtfaststart import processor
import json
import sys
import os
from PIL import Image
import base64
import shutil


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
                'env': env})
    return ret


# some initalization
ffmpeg_path = "ffmpeg.exe"
ffprobe_path = "ffprobe.exe"
path_separator = "\\"
shell_status = True
os_prefix = ""

if platform.system() == "Darwin":
    os_prefix = os.getcwd() + "/VoConverter.app/Contents/Resources/"

    ffmpeg_path = os_prefix + "ffmpeg"
    ffprobe_path = os_prefix + "ffprobe"

    shell_status = False
    path_separator = "/"


# useful classes to keep data around
class EncodingPreset:

    def __init__(self, name, width, height, bitrate, framerate, keyframes):
        self.name = name
        self.width = width
        self.height = height
        self.bitrate = bitrate
        self.framerate = framerate
        self.keyframes = keyframes


class Drawing:

    def __init__(self, uid, screenshot, bitmap, drawing_time):
        self.uid = uid
        self.screenshot = screenshot
        self.bitmap = bitmap
        self.drawing_time = drawing_time


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


class FileToConvert:
    pass


# parse the presets
def get_presets():

    presets = []
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
        presets.append(preset)
        preset_choices.append(preset.name)
    original_preset = EncodingPreset(name="Original",
                                     width=0,
                                     height=0,
                                     bitrate=0,
                                     framerate=0,
                                     keyframes=0)
    preset_choices.append(original_preset.name)
    presets.append(original_preset)

    return presets, preset_choices


def get_preset(preset):
    presets, choices = get_presets()
    return [x for x in presets if x.name == preset][0]


def get_video_info(video_path):

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


# the convert functions
class EncodeWithKeyFrames(threading.Thread):

    def __init__(self, in_video, in_video_info, out_video, callback, preset):

        super().__init__()

        self.in_video = in_video
        self.in_video_info = in_video_info
        self.out_video = out_video
        self.callback = callback
        self.preset = preset

    def run(self):

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
            video_info = video.video_info

            convert_thr = EncodeWithKeyFrames(in_video=video.file,
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

    def abort(self):
        print("ABORT THE THREAD")


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

class AddMultipleDrawings(threading.Thread):

    def __init__(self, temp_dir, cut_number, input_video, video_info, tmp_out, drawings, pause_time,
                 duration, watermark, callback):

        super().__init__()

        self.cut_number = cut_number
        self.input_video = input_video
        self.tmp_out = tmp_out
        self.temp_dir = temp_dir
        self.video_info = video_info
        self.drawings = drawings
        self.pause_time = pause_time
        self.duration = duration
        self.watermark = watermark
        self.callback = callback

    def run(self):

        # this is the logo position to burn
        # video height - image height - 20 padding
        bottom = self.video_info.height - 22 - 20
        left = 20

        if self.watermark:
            watermark_file = "watermark.png"
        else:
            watermark_file = "trans_watermark.png"

        # sort the drawings by time
        self.drawings = sorted(self.drawings, key=lambda drw: drw.drawing_time)

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
                os_prefix + watermark_file,
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
            os_prefix + watermark_file,
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
        self.callback(0)
        print("DRAWWWINGS >>>>>>>>>>>>>>>>")
        for drawing in self.drawings:
            print(drawing.drawing_time)

            raw_png = base64.b64decode(drawing.bitmap)
            f = open(self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) +
                     "_overlay.png", "wb")
            f.write(raw_png)
            f.close()
            pil_png = Image.open(self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) +
                                 "_overlay.png")

            raw_jpeg = base64.b64decode(drawing.screenshot)
            jf = open(self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) +
                      "_screenshot.jpg", "wb")
            jf.write(raw_jpeg)
            jf.close()
            pil_jpeg = Image.open(self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(drawing_number) +
                                  "_screenshot.jpg")
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
                    os_prefix + watermark_file,
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
                    os_prefix + "silence.wav",
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
                    os_prefix + watermark_file,
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

            progress = int(((drawing_number / len(self.drawings)) * 100) / 2)
            self.callback(progress)
            # do the next drawing
            drawing_number += 1

        if self.video_info.has_sound:
            # and join all the bits and pieces

            # now we must concat the whole thing, since we have a start, end, middle, and thumbs for all drawings
            for x in range(0, len(self.drawings)):

                # first drawing
                if x == 0:
                    self.callback(50)
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
                    self.callback(((x / len(self.drawings) * 100) / 2) + 50)
                    print("cenas", ((x / len(self.drawings) * 100) / 2) + 50)
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
                        self.callback(100)
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
                    # copy the done to the final video
                    shutil.copy(
                                self.temp_dir.name + path_separator + str(self.cut_number) + "_" + str(x) + "_done.mp4",
                                self.tmp_out
                                )

        else:
            # and join all the bits and pieces

            # now we must concat the whole thing, since we have a start, end, middle, and thumbs for all drawings
            for x in range(0, len(self.drawings)):

                # first drawing
                if x == 0:
                    self.callback(50)
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
                    self.callback(((x / len(self.drawings) * 100) / 2) + 50)
                    print("cenas", ((x / len(self.drawings) * 100) / 2) + 50)
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
                    self.callback(100)
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


class EncodeSubtitles(threading.Thread):

    def __init__(self, temp_dir, cut_number, video_path, video_info, time_start, duration, comments, tmp_out,
                 font_size, watermark):

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
        self.watermark = watermark

    def run(self):

        # write srt file
        # ass_log_path = self.temp_dir.name + path_separator + str(self.cut_number) + ".ass.log"
        # ass_log_file = open(ass_log_path, "wb")

        # video height - image height - 20 padding
        bottom = self.video_info.height - 22 - 20
        left = 20

        if self.watermark:
            watermark_file = "watermark.png"
        else:
            watermark_file = "trans_watermark.png"

        ass_contents = "[Script Info]\n"
        ass_contents += "PlayResY: 600\n"
        ass_contents += "PlayResX: 800\n"
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
                shell=True,
                universal_newlines=True,
                #stderr=STDOUT,
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
                os_prefix + watermark_file,
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

