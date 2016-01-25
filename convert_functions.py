import threading
from subprocess import *
import subprocess
import re
import platform
from qtfaststart import processor
import json
import sys
import os

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


