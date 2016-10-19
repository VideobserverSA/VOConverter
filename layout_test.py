import wx
import webbrowser
import os
import platform
import convert_functions
import aws
import tempfile
import threading
import time
import subprocess
import html.parser
from boto3.session import Session
import math
import sys
from easysettings import EasySettings
import xml.etree.ElementTree as xmlParser
import urllib
import base64
from PIL import Image
import hashlib
import errno
import shutil
import configparser

# we need this because: https://github.com/pyinstaller/pyinstaller/wiki/Recipe-subprocess
if getattr(sys, 'frozen', False):
    isFrozen = True
else:
    isFrozen = False


def print_mine(*args):
    pass
    # print(args)

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
else:
    # so check for 32 bit windows
    if 'PROGRAMFILES(X86)' in os.environ:
        # were 64!!!
        ffmpeg_path = "ffmpeg_64.exe"
        ffprobe_path = "ffprobe_64.exe"
    else:
        # were 32!
        ffmpeg_path = "ffmpeg_32.exe"
        ffprobe_path = "ffprobe_32.exe"

# some colors
color_dark_grey = wx.Colour(44, 49, 56)
color_orange = wx.Colour(255, 122, 0)
color_background_grey = wx.Colour(226, 228, 234)
color_home_back = wx.Colour(243, 245, 250)
color_home_text = wx.Colour(44, 49, 56)
color_home_headers = wx.Colour(155, 160, 167)
color_white = wx.WHITE
color_black = wx.BLACK
color_dark_green = wx.Colour(61, 209, 2)

lang_conf = configparser.ConfigParser()
lang_conf.read("lang.ini")
current_version = lang_conf["Version"]["Version"]



class ConvertFileDrop(wx.FileDropTarget):

    def __init__(self, callback, estimate=None):
        super().__init__()
        self.callback = callback
        self.estimate = estimate

    def OnDropFiles(self, x, y, filenames):
        self.callback([x.lower() for x in filenames], self.estimate)
        return True


class UploadFileDrop(wx.FileDropTarget):

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def OnDropFiles(self, x, y, filenames):
        self.callback(filenames)
        return True


class MainWindow(wx.Frame):

    # main init
    def __init__(self, parent, title):

        # we don't want to allow resizing
        wx.Frame.__init__(self, parent, title=title, size=(600, 530),
                          style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX))

        # some necessary cruft
        self.destination_dir = settings.get("destination_dir", os.path.expanduser("~" + "\\" + "Desktop"))
        # self.destination_dir = ""
        self.filenames = []
        self.preset = ""

        self.temp_dir = tempfile.TemporaryDirectory()

        self.current_progress = 0
        self.progress_start_time = time.time()
        self.data_points = []

        self.final_path = ""
        self.final_filename = ""

        self.current_thread = threading.Thread()

        self.logged_in = False
        self.token = {}
        self.aws_data = {}
        self.login_dialog = None
        self.username_to_display = ""

        self.current_upload_size = 0

        # playlist cruft
        self.watermark = settings.get("watermark", 0)
        self.pause_duration = settings.get("pause_duration", 4)
        self.font_size = settings.get("font_size", 30)

        self.canceled = False

        # init the main screen
        # next calls will be via the replace view method
        self.main_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        self.current_window = self.create_main_screen()
        self.main_sizer.Add(self.current_window)
        self.SetSizer(self.main_sizer)

        self.time_delta = 0

        # redraw the window
        self.Layout()
        self.Refresh()
        self.SendSizeEvent()
        self.Update()

        self.Show()

    # progress funcs
    def mark_progress(self, progress):
        self.current_progress = progress
        if progress == 0:
            progress = 1

        # calc estimated time
        delta = time.time() - self.progress_start_time
        eta = (delta * 100) / progress
        remaining = eta - delta

        # create data point
        self.data_points.append(remaining)
        if len(self.data_points) > 5:
            # remove the earliest data point
            self.data_points.pop(0)

    def update_progress(self, gauge, text):
        gauge.SetValue(self.current_progress)
        if len(self.data_points) > 0:
            remain = (sum(self.data_points) / len(self.data_points))
            # print_mine(remain)
            s = int(remain % 60)
            m = int((remain / 60) % 60)
            h = int((remain / (60 * 60)) % 60)
            time_str = str(h) + "h " + str(m) + "m " + str(s) + "s"
            text.SetLabel("Estimated time: " + time_str + " " + str(self.current_progress) + "%")

    def reset_progress(self):
        self.current_progress = 0
        self.progress_start_time = time.time()
        self.data_points = []

    # open the final path
    def open_final_path(self, e):
        # open the video file
        if platform.system() == "Darwin":
            subprocess.check_call(["open", self.final_path])
        else:
            os.startfile(self.final_path)

    # abandon thread
    def cancel_current_thread(self, e):
        # ask the user if he wants to abort
        self.create_alert_dialog(parent=self, title="Cancel?", message="Cancel current operation?",
                                 # no_click_handler=,
                                 yes_click_handler=self.real_cancel_current_thread)

    def real_cancel_current_thread(self, e):
        self.canceled = True
        self.current_thread.abort()
        self.show_main(e)

    # navigation
    def show_main(self, e):
        print_mine("MAIN!")
        self.replace_view(self.create_main_screen())

    def show_convert_join(self, e):
        print_mine("CONVERT / JOIN!")
        self.replace_view(self.create_convert_join_screen())

    def show_upload(self, e):
        print_mine("UPLOAD")
        if not self.logged_in:
            self.create_alert_dialog(parent=self, title="Please Login.",
                                     message="Login to upload files",
                                     is_ok_type=True)
            return
        self.filenames = []
        self.replace_view(self.create_upload_screen())
        self.canceled = False

    def show_playlist(self, e):
        print_mine("PLAYLIST")
        self.filenames = []
        self.replace_view(self.create_playlist_screen())

    def show_convert(self, e):
        print_mine("CONVERT")
        self.filenames = []
        win, estimate = self.create_convert_screen()
        self.replace_view(win)

    def show_join(self, e):
        print_mine("JOIN!")
        self.filenames = []
        win, estimate, final_file_name = self.create_join_screen()
        self.replace_view(win)

    def show_convert_progress(self, e):
        # sanity check
        if self.destination_dir == "":
            print_mine("NO DESTINATION DIR")
            return
        if len(self.filenames) < 1:
            print_mine("NO FILES TO CONVERT")
            return
        if self.preset == "":
            print_mine("NO PRESET")
            return
        print_mine("CONVERT PROGRESS")
        win, gauge, estimate_text, current_file = self.create_convert_progress()
        self.replace_view(win)

        presets, choices = convert_functions.get_presets()
        the_preset = convert_functions.get_preset(self.preset)

        self.canceled = False

        start_time = time.time()

        current_number = 1
        for one_file in self.filenames:

            current_file.SetLabel(str(current_number) + "/" + str(len(self.filenames)) + " " + one_file.file)

            out_video = self.destination_dir + path_separator + os.path.basename(one_file.file.split(".")[0]) + ".mp4"
            if os.path.exists(out_video):
                out_video = out_video = self.destination_dir + path_separator + os.path.basename(one_file.file.split(".")[0]) + "_1.mp4"

            self.current_thread = join_thr = convert_functions.JoinFiles(in_videos=[one_file],
                                                                         out_video=out_video,
                                                                         tmp_dir=self.temp_dir,
                                                                         preset=the_preset,
                                                                         callback=lambda progress: self.mark_progress(progress)
                                                                         )

            join_thr.start()

            self.reset_progress()

            while join_thr.is_alive():
                dummy_event = threading.Event()
                dummy_event.wait(timeout=0.01)

                self.update_progress(gauge, estimate_text)

                wx.Yield()
                self.Update()
            current_number += 1

        self.final_path = out_video
        self.filenames = [out_video]

        end_time = time.time()
        self.time_delta = end_time - start_time

        self.show_convert_complete(None)

    def show_convert_complete(self, e):
        if not self.canceled:
            print_mine("CONVERT COMPLETE")
            self.replace_view(self.create_convert_complete())

    # utility function
    def convert_add_files(self, filenames, the_list, estimate):
        for file in filenames:
            the_list.Append([file])
            file_to_convert = convert_functions.FileToConvert()
            file_to_convert.file = file
            file_to_convert.video_info = convert_functions.get_video_info(file)
            self.filenames.append(file_to_convert)
        self.calculate_conversion_estimates(estimate)

    def calculate_conversion_estimates(self, estimate):
        total_size = 0
        preset = convert_functions.get_preset(preset=self.preset)
        for video in self.filenames:
            if preset.name == "Original":
                local_size = (float(video.video_info.duration) * float(video.video_info.bitrate)) / 10
            else:
                local_size = (float(video.video_info.duration) * float(preset.bitrate) * 1024) / 10

            print_mine("local_size", local_size)
            total_size += local_size

        print_mine("total_size", total_size)

        size_in_megas = total_size / 1024 / 1024
        size_in_gigas = size_in_megas / 1024
        print_mine("in_megas", size_in_megas)
        print_mine("in_gigas", size_in_gigas)

        if size_in_megas > 1000:
            estimate.SetLabel(str(round(size_in_gigas, 1)) + " Gb")
        else:
            estimate.SetLabel(str(int(size_in_megas)) + " Mb")

        temp_total, temp_used, temp_free = shutil.disk_usage(self.temp_dir.name)
        # do we have enough space
        if (total_size * 2) > temp_free:
            self.create_alert_dialog(parent=self, title="Not enough space",
                                     message="You do not have enough disk space for the conversion\nif you try to continue with these files and presets\nthe conversion will probably fail.",
                                     is_ok_type=True)
            estimate.SetForegroundColour(wx.RED)
        else:
            estimate.SetForegroundColour(color_dark_green)

    def convert_browse_for_files(self, the_list, estimate):
        dlg = wx.FileDialog(self, "Video file", "", "", "*.*", wx.FD_OPEN | wx.FD_MULTIPLE)
        if dlg.ShowModal() == wx.ID_OK:
            paths = dlg.GetPaths()
        dlg.Destroy()
        if len(paths) > 0:
            self.convert_add_files(paths, the_list, estimate=estimate)

    def upload_browse_for_files(self, the_list):
        dlg = wx.FileDialog(self, "Video file", "", "", "*.mp4", wx.FD_OPEN | wx.FD_MULTIPLE)
        if dlg.ShowModal() == wx.ID_OK:
            paths = dlg.GetPaths()
        dlg.Destroy()
        if len(paths) > 0:
            self.upload_add_files(paths, the_list)

    def playlist_browse_for_files(self, the_list):
        dlg = wx.FileDialog(self, "Playlist FIle", "", "", "*.vopl", wx.FD_OPEN | wx.FD_MULTIPLE)
        if dlg.ShowModal() == wx.ID_OK:
            paths = dlg.GetPaths()
        dlg.Destroy()
        if len(paths) > 0:
            self.playlist_add_files(paths, the_list, None)

    def set_destination_dir(self, text_ctrl):
        path = ""
        dlg = wx.DirDialog(self, "Destination Directory")
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            settings.set("destination_dir", path)
            settings.save()

        dlg.Destroy()
        if path != "":
            self.destination_dir = path
            text_ctrl.SetLabel(path)

    def set_current_preset(self, preset, estimate):
        self.preset = preset
        self.calculate_conversion_estimates(estimate=estimate)

    def set_font_size(self, size):
        self.font_size = size
        # update settings
        settings.setsave("font_size", size)

    def set_pause_time(self, duration):
        self.pause_duration = duration
        # update settings
        settings.setsave("pause_duration", duration)

    def set_watermark_enabled(self, enabled):
        self.watermark = (enabled == 1)
        # update settings
        settings.setsave("watermark", enabled)

    def show_join_progress(self, e):
        # sanity check
        if self.destination_dir == "":
            print_mine("NO DESTINATION DIR")
            return
        if len(self.filenames) < 1:
            print_mine("NO FILES TO CONVERT")
            return
        if self.preset == "":
            print_mine("NO PRESET")
            return
        print_mine("CONVERT PROGRESS")
        win, gauge, estimate_text, current_file = self.create_join_progress()
        self.replace_view(win)

        presets, choices = convert_functions.get_presets()
        the_preset = convert_functions.get_preset(self.preset)

        start_time = time.time()

        self.canceled = False

        files_to_join_label = ""
        for file in self.filenames:
            files_to_join_label += os.path.basename(file.file) + " , "

        current_file.SetLabel(files_to_join_label[:-3])

        out_video = self.destination_dir + path_separator + self.final_filename + ".mp4"
        if os.path.exists(out_video):
            out_video = out_video = self.destination_dir + path_separator + self.final_filename + "_1_.mp4"

        self.current_thread = join_thr = convert_functions.JoinFiles(in_videos=self.filenames,
                                                                     out_video=out_video,
                                                                     tmp_dir=self.temp_dir,
                                                                     preset=the_preset,
                                                                     callback=lambda progress: self.mark_progress(progress)
                                                                     )

        join_thr.start()

        self.reset_progress()

        while join_thr.is_alive():
            dummy_event = threading.Event()
            dummy_event.wait(timeout=0.01)

            wx.Yield()
            self.Update()

            self.update_progress(gauge, estimate_text)

        self.final_path = out_video
        self.filenames = [out_video]

        end_time = time.time()
        self.time_delta = end_time - start_time

        print_mine("SHOW JOIN COMPLETE WTF MAN WHY CRASH?")
        self.show_join_complete(None)

    def show_join_complete(self, e):
        if not self.canceled:
            print_mine("JOIN COMPLETE")
            self.replace_view(self.create_join_complete())

    # utility function
    def join_add_files(self, filenames, the_list, estimate, final_name):
        for file in filenames:
            the_list.Append([file])
            file_to_convert = convert_functions.FileToConvert()
            file_to_convert.file = file
            file_to_convert.video_info = convert_functions.get_video_info(file)
            self.filenames.append(file_to_convert)
        self.calculate_conversion_estimates(estimate)

        new_file_name = "_".join(os.path.basename(filenames[0]).split(".")[:-1]) + "_joined"
        final_name.SetValue(new_file_name)

    def set_final_filename(self, event):
        self.final_filename = event.String

    def show_upload_progress(self, e):
        print_mine("DO THE UPLOAD")

        if not self.logged_in:
            self.create_alert_dialog(parent=self, title="Please Login.",
                                     message="Login to upload files",
                                     is_ok_type=True)
            return

        win, gauge, text, label = self.create_upload_progress()
        self.replace_view(win)

        self.canceled = False

        # init s3 session
        aws_session = Session(aws_access_key_id=self.aws_data["AccessKeyId"],
                              aws_secret_access_key=self.aws_data["SecretAccessKey"],
                              aws_session_token=self.aws_data["SessionToken"],
                              region_name=self.aws_data["Region"])

        # first create and object to send
        client = aws_session.client(service_name="s3",
                                    # endpoint_url=self.aws_data["CloudfrontEndpoint"])
                                    )

        current_number = 1
        for file in self.filenames:

            # check for file existance
            if not os.path.exists(file):
                dialog = self.create_alert_dialog(parent=self,
                                                  title="File missing",
                                                  message="The file is missing. Skipping.",
                                                  is_ok_type=True)
                continue

            label.SetLabel(str(current_number) + "/" + str(len(self.filenames)) + " " + file)

            # upload_key = os.path.basename(file)
            # lets create a damn ugly upload key fuck this!
            md5time = hashlib.md5(str(time.time()).encode("UTF-8")).hexdigest()[0:3]
            upload_key = self.aws_data["Folder"] + time.strftime("%Y-%m-%d",
                                                                 time.gmtime()) + "_" + os.path.basename(file)[0:15].replace(".mp4", "") + "_" + md5time + "_" + str(
                self.token["user_id"]) + ".mp4"

            print_mine("Upload key", upload_key)

            self.reset_progress()

            # we cheat so that the user can see some progress at start
            gauge.Pulse()

            total_size = os.stat(file).st_size
            self.current_upload_size = 0

            self.current_thread = upload_thr = aws.UploadFile(s3client=client,
                                                              bucket=self.aws_data["Bucket"],
                                                              key=upload_key,
                                                              file=file,
                                                              progress_callback=lambda progress: self.mark_upload_progress(progress, total_size),
                                                              resume_callback=lambda progress: self.mark_upload_progress(progress, total_size),
                                                              name="upload-thr")
            upload_thr.start()

            while upload_thr.is_alive():
                dummy_event = threading.Event()
                dummy_event.wait(timeout=0.01)

                if self.current_upload_size > 0:
                    self.update_progress(gauge, text)

                wx.Yield()
                self.Update()

            # get the real duration
            final_video_info = convert_functions.get_video_info(file)

            print_mine("file duration", final_video_info.duration)

            aws.confirm_upload(self.token["token"],
                               bucket=self.aws_data["Bucket"],
                               key=upload_key,
                               duration=int(float(final_video_info.duration)),
                               size=total_size)
            current_number += 1

        self.final_path = self.filenames[0]
        self.show_upload_complete(None)

        # show complete

    # utility function
    def upload_add_files(self, filenames, the_list):
        for file in filenames:
            the_list.Append([file])
            self.filenames.append(file)

    def mark_upload_progress(self, progress, total):
        print_mine("UP:", progress, total)
        self.current_upload_size += progress
        percentage = math.ceil((self.current_upload_size / total) * 100)
        self.mark_progress(percentage)

    def show_upload_complete(self, e):
        if not self.canceled:
            print_mine("UPLOAD COMPLETE")
            self.replace_view(self.create_upload_complete())

    def show_playlist_progress(self, e):
        # sanity check
        if self.destination_dir == "":
            print_mine("NO DESTINATION DIR")
            return
        if len(self.filenames) < 1:
            print_mine("NO FILES TO CONVERT")
            return
        print_mine("PLAYLIST PROGRESS")
        win, gauge, estimate_text, current_file = self.create_playlist_progress()
        self.replace_view(win)

        current_number = 1
        for one_file in self.filenames:

            current_file.SetLabel(str(current_number) + "/" + str(len(self.filenames)) + " " + os.path.basename(one_file))

            tree = xmlParser.parse(one_file)
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

                wildcard_ext = "*.mp4;*.mov;*.avi;*.mkv"
                wildcard = "Video Files" + " (" + wildcard_ext + ")" + "|" + wildcard_ext + "|" + "All Files" +\
                           " (*.*)" + "|" + "*.*"

                dlg = wx.FileDialog(self, "Video file not found, please select another", "", "",
                                    wildcard, wx.FD_OPEN)
                if dlg.ShowModal() == wx.ID_OK:
                    path = dlg.GetPath()
                    # self.PushStatusText(path + " video loaded...")

                    video_path = path
                    # self.parse_playlist(filename=path)

                dlg.Destroy()

            self.reset_progress()

            # we have a name so make sure we create the dir
            if not os.path.exists(self.temp_dir.name):
                os.makedirs(self.temp_dir.name)

            # self.base_name = base.get("name")
            # if self.base_name is None:
            #     self.base_name = os.path.basename(one_file)

            # self.username = base.get("username")
            # settings.set("username", self.username)
            # settings.save()

            # get playlist length
            play_len = len(base.findall('.items/item'))
            # we say that the join is the last step
            play_len += 1
            num_items = play_len

            video_info = convert_functions.get_video_info(video_path)

            has_overlap = False
            last_start = 0
            last_end = 0

            for child in base.findall('.items/item'):
                item_type = child.find("type").text
                time_start = ""
                time_end = ""
                if item_type == "ga":
                    real_time_start = float(child.find("game_action").find("video_time_start").text)
                    time_start = int(real_time_start)
                    real_time_end = float(child.find("game_action").find("video_time_end").text)
                    time_end = int(real_time_end)
                if item_type == "cue":
                    real_time_start = float(child.find("action_cue").find("starting_time").text)
                    time_start = int(real_time_start)
                    real_time_end = float(child.find("action_cue").find("ending_time").text)
                    time_end = int(real_time_end)
                if time_start < last_end:
                    has_overlap = True

                last_start = time_start
                last_end = time_end

            cut_number = 0
            # start parsing each item
            for child in base.findall('.items/item'):

                # status_text = t("Processing item %i") % (cut_number + 1)
                # self.PushStatusText(status_text)

                item_type = child.find("type").text
                # print_mine("ItemType>> ", item_type)

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

                        the_drawing = convert_functions.Drawing(uid="None", screenshot=screenshot,
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
                            the_drawing = convert_functions.Drawing(uid=temp_uid, screenshot=temp_screenshot,
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

                        the_drawing = convert_functions.Drawing(uid="None", screenshot=screenshot,
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
                            the_drawing = convert_functions.Drawing(uid=temp_uid, screenshot=temp_screenshot,
                                                                    bitmap=temp_bitmap, drawing_time=temp_time)
                            multiple_drawings.append(the_drawing)

                # add some padding
                # time_start += 2
                # time_end += 2

                # print_mine("TimeStart>> ", time_start)
                # print_mine("TimeEnd>> ", time_end)
                # print_mine("Comments>> ", comments)
                # print_mine("Enable Comments>> ", enable_comments)
                #
                # print_mine("")

                # for drw in multiple_drawings:
                #    print_mine(drw.drawing_time)

                duration = time_end - time_start
                real_duration = real_time_end - real_time_start
                tmp_out = self.temp_dir.name + path_separator + str(cut_number) + ".mp4"

                if has_overlap:
                    if comments is None:
                        comments = " "
                    if enable_comments == "false":
                        enable_comments = "true"

                #  first check for comments
                if comments is not None and enable_comments == "true":
                    if comments is None:
                        # self.PushStatusText(t("Better converting %i") % (cut_number + 1))

                        burn_thr = convert_functions.BurnLogo(temp_dir=self.temp_dir, cut_number=cut_number, input_video=video_path,
                                                              time_start=time_start, duration=duration,
                                                              tmp_out=self.temp_dir.name + path_separator + str(cut_number) + "_comments.mp4",
                                                              video_info=video_info, watermark=self.watermark)
                        burn_thr.start()
                        while burn_thr.is_alive():
                            wx.Yield()
                            self.Update()
                            dummy_event = threading.Event()
                            dummy_event.wait(timeout=0.01)

                    else:
                        # self.PushStatusText(t("Adding subtitles to item %i") % (cut_number + 1))

                        has_comments = True
                        sub_thr = convert_functions.EncodeSubtitles(temp_dir=self.temp_dir, cut_number=cut_number, video_path=video_path,
                                                                    video_info=video_info,
                                                                    time_start=time_start, duration=duration, comments=comments,
                                                                    tmp_out=self.temp_dir.name + path_separator + str(cut_number) + "_comments.mp4",
                                                                    font_size=self.font_size,
                                                                    watermark=self.watermark)
                        sub_thr.start()
                        while sub_thr.is_alive():
                            wx.Yield()
                            self.Update()
                            dummy_event = threading.Event()
                            dummy_event.wait(timeout=0.01)

                elif has_drawing or has_multiple_drawings:
                    # we need to convert without fast copy so that the further cuts work out right
                    key_thr = convert_functions.CutWithKeyFrames(temp_dir=self.temp_dir, cut_number=cut_number, video_path=video_path,
                                                                 time_start=real_time_start, duration=real_duration,
                                                                 tmp_out=self.temp_dir.name + path_separator + str(cut_number) + "_comments.mp4",
                                                                 key_frames=12,
                                                                 callback=lambda p: self.update_drawing_progress(p, cut_number + 1, num_items))
                    key_thr.start()
                    while key_thr.is_alive():
                        wx.Yield()
                        self.Update()
                        dummy_event = threading.Event()
                        dummy_event.wait(timeout=0.01)
                else:
                    # just cut in time since we need no further processing
                    # status_text = t("Fast cutting item %i") % (cut_number + 1)
                    # self.PushStatusText(status_text)
                    fast_cut_thr = convert_functions.CutFastCopy(temp_dir=self.temp_dir, cut_number=cut_number, video_path=video_path,
                                                                 time_start=time_start, duration=duration,
                                                                 tmp_out=self.temp_dir.name + path_separator + str(cut_number) + "_comments.mp4")
                    fast_cut_thr.start()
                    while fast_cut_thr.is_alive():
                        wx.Yield()
                        self.Update()
                        dummy_event = threading.Event()
                        dummy_event.wait(timeout=0.01)

                # do we add an overlay?
                if has_drawing:
                    # self.PushStatusText(t("Adding drawing to item %i") % (cut_number + 1))
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

                    overlay_thr = convert_functions.AddOverlay(temp_dir=self.temp_dir, cut_number=cut_number,
                                                               input_video=self.temp_dir.name + path_separator + str(cut_number) + "_comments.mp4",
                                                               video_info=video_info,
                                                               video_time=video_time,
                                                               tmp_out=self.temp_dir.name + path_separator + str(cut_number) + "_overlay.mp4",
                                                               image_path=self.temp_dir.name + path_separator + str(cut_number) + "_composite.png",
                                                               pause_time=self.pause_duration.get(),
                                                               watermark=self.watermark)
                    overlay_thr.start()
                    while overlay_thr.is_alive():
                        wx.Yield()
                        self.Update()
                        dummy_event = threading.Event()
                        dummy_event.wait(timeout=0.01)

                if has_multiple_drawings:
                    multiple_thr = convert_functions.AddMultipleDrawings(temp_dir=self.temp_dir,
                                                                         cut_number=cut_number,
                                                                         input_video=self.temp_dir.name + path_separator + str(cut_number) +
                                                                         "_comments.mp4",
                                                                         video_info=video_info,
                                                                         tmp_out=self.temp_dir.name + path_separator + str(cut_number) + "_overlay.mp4",
                                                                         drawings=multiple_drawings,
                                                                         pause_time=self.pause_duration,
                                                                         duration=real_duration,
                                                                         watermark=self.watermark,
                                                                         callback=lambda p: self.update_drawing_progress(p, cut_number + 1, num_items),
                                                                         fast_drawings=True)
                    multiple_thr.start()
                    while multiple_thr.is_alive():
                        self.update_progress(gauge, estimate_text)
                        wx.Yield()
                        self.Update()
                        dummy_event = threading.Event()
                        dummy_event.wait(timeout=0.01)

                # lastly we convert to fast copy for the final join
                if has_drawing or has_multiple_drawings:
                    fast_copy_input = self.temp_dir.name + path_separator + str(cut_number) + "_overlay.mp4"
                else:
                    fast_copy_input = self.temp_dir.name + path_separator + str(cut_number) + "_comments.mp4"

                fast_copy_thr = convert_functions.ConvertToFastCopy(temp_dir=self.temp_dir, cut_number=cut_number,
                                                                    input_video=fast_copy_input, tmp_out=tmp_out)
                fast_copy_thr.start()
                while fast_copy_thr.is_alive():
                    wx.Yield()
                    # self.PushStatusText(t("Finishing item %i") % (cut_number + 1))
                    self.Update()
                    dummy_event = threading.Event()
                    dummy_event.wait(timeout=0.01)

                # calc progress
                progress = cut_number / num_items
                # progress_str = str(math.ceil(progress * 100))
                # TODO solve this
                # self.meter.set(progress, t("Converting: ") + self.base_name + " " + progress_str + "%")
                # self.meter.SetValue(progress * 100)

                self.mark_progress(int(progress * 100))

                self.update_progress(gauge, estimate_text)
                wx.Yield()
                self.Update()

                cut_number += 1

            # self.PushStatusText(t("Joining final video"))
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
            join_args.append("-metadata")
            join_args.append("comment=VOCONVERTER")

            # outfile
            out_filename = os.path.basename(one_file).replace(".vopl", "")
            out_path = self.destination_dir + path_separator + out_filename + ".mp4"

            if os.path.isfile(out_path):
                out_filename = os.path.basename(one_file).replace(".vopl", "")
                out_path = self.destination_dir + path_separator + out_filename + "_1_.mp4"

            # put it on desktop for now
            join_args.append(out_path)

            try:
                out = subprocess.check_call(join_args, stderr=subprocess.STDOUT, shell=False)
            except subprocess.CalledProcessError as cpe:
                print_mine("ERROR>>", cpe.output)
            # TODO solve this

            current_number += 1

        self.final_path = out_path
        self.filenames = [out_path]
        self.show_playlist_complete(None)

    # utility function
    def playlist_add_files(self, filenames, the_list, estimate):
        for file in filenames:
            the_list.Append([file])
            self.filenames.append(file)

    def show_playlist_complete(self, e):
        print_mine("CONVERT COMPLETE")
        self.replace_view(self.create_playlist_complete())

    def update_drawing_progress(self, progress, cut_number, total_items):
        # print_mine("prog, cut, num", progress, cut_number, total_items)
        # get the lower and upper bound
        interval = 100 / total_items
        upper = (cut_number / total_items) * 100
        lower = upper - interval
        # print_mine("int, low, up", interval, upper, lower)
        relative_progress = (progress * interval) / 100
        actual_progress = lower + relative_progress
        # print_mine("rel, act", relative_progress, actual_progress)
        self.mark_progress(int(actual_progress))

    # show the next screen
    def replace_view(self, new_view_creator):
        # remove the previous view
        # use deferred destruction or mac os will crash frequently
        self.current_window.DestroyLater()
        # recreate a blank sizer to occupy the whole screen
        self.main_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        # get the window we were passed
        self.current_window = new_view_creator
        # fill the sizer with such window
        self.main_sizer.Add(self.current_window)
        # set this sizer as our main sizer
        self.SetSizer(self.main_sizer)
        # redraw the window
        self.Layout()
        self.Refresh()
        self.SendSizeEvent()
        self.Update()

    # create a nav button
    def create_nav_button(self, parent, size, file, text, back_color, text_color, hover_color, click_handler):

        # a window so we can have a colored background
        anchor_window = wx.Window(parent=parent, id=wx.ID_ANY, size=size)
        anchor_window_sizer = wx.BoxSizer(orient=wx.VERTICAL)

        anchor_window.SetSizer(anchor_window_sizer)
        anchor_window.SetBackgroundColour(back_color)

        # load bitmap from file
        raw_bitmap = wx.Bitmap(name=file, type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        static_bitmap = wx.StaticBitmap(parent=anchor_window, id=wx.ID_ANY)
        static_bitmap.SetBitmap(raw_bitmap)
        # center in the middle, and give so
        anchor_window_sizer.Add(static_bitmap, 0, wx.CENTER | wx.TOP, 45)

        # the text label
        text_label = wx.StaticText(parent=anchor_window, id=wx.ID_ANY, label=text.upper())
        text_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        text_label.SetForegroundColour(text_color)
        anchor_window_sizer.Add(text_label, 0, wx.CENTER | wx.TOP, 25)

        # we want the user to know that it can click here
        anchor_window.SetCursor(wx.Cursor(wx.CURSOR_HAND))

        # bind the clicks in all the components, so that anywhere in the "button" registers as a click
        anchor_window.Bind(wx.EVT_LEFT_DOWN, click_handler)
        static_bitmap.Bind(wx.EVT_LEFT_DOWN, click_handler)
        text_label.Bind(wx.EVT_LEFT_DOWN, click_handler)

        # create the over
        anchor_window.Bind(wx.EVT_ENTER_WINDOW, lambda e: self.change_background(anchor_window, hover_color))
        static_bitmap.Bind(wx.EVT_ENTER_WINDOW, lambda e: self.change_background(anchor_window, hover_color))
        text_label.Bind(wx.EVT_ENTER_WINDOW, lambda e: self.change_background(anchor_window, hover_color))

        anchor_window.Bind(wx.EVT_LEAVE_WINDOW, lambda e: self.change_background(anchor_window, back_color))

        # component ready to use elsewhere
        return anchor_window

    # to change the back of a nav button
    def change_background(self, window, color):
        window.SetBackgroundColour(color)
        self.Layout()
        self.Refresh()
        self.SendSizeEvent()
        self.Update()

    # create a small button
    def create_small_button(self, parent, length, text, back_color, text_color, click_handler, border_color=None):

        # a window so we can have a colored background
        anchor_window = wx.Window(parent=parent, id=wx.ID_ANY, size=(length, 30))
        anchor_window_sizer = wx.BoxSizer(orient=wx.VERTICAL)

        anchor_window.SetSizer(anchor_window_sizer)
        anchor_window.SetBackgroundColour(back_color)

        if border_color is not None:
            anchor_window.SetBackgroundColour(border_color)

            border_window = wx.Window(parent=anchor_window, id=wx.ID_ANY, size=(length, 30))
            border_window.SetBackgroundColour(back_color)
            border_window_sizer = wx.BoxSizer(orient=wx.VERTICAL)
            border_window.SetSizer(border_window_sizer)

            border_window.Bind(wx.EVT_LEFT_DOWN, click_handler)

            anchor_window_sizer.Add(border_window, 1, wx.TOP | wx.LEFT | wx.RIGHT | wx.BOTTOM, 1)

            # the text label
            text_label = wx.StaticText(parent=border_window, id=wx.ID_ANY, label=text.upper())
            text_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
            text_label.SetForegroundColour(text_color)
            border_window_sizer.Add(text_label, 0, wx.CENTER | wx.TOP, 6)

        else:
            # the text label
            text_label = wx.StaticText(parent=anchor_window, id=wx.ID_ANY, label=text.upper())
            text_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
            text_label.SetForegroundColour(text_color)
            anchor_window_sizer.Add(text_label, 0, wx.CENTER | wx.TOP, 8)

        # we want the user to know that it can click here
        anchor_window.SetCursor(wx.Cursor(wx.CURSOR_HAND))

        # bind the clicks in all the components, so that anywhere in the "button" registers as a click
        anchor_window.Bind(wx.EVT_LEFT_DOWN, click_handler)
        text_label.Bind(wx.EVT_LEFT_DOWN, click_handler)

        # component ready to use elsewhere
        return anchor_window

    def create_alert_dialog(self, parent, title, message, is_ok_type=False,
                            no_click_handler=None, yes_click_handler=None):

        dialog = wx.Dialog(parent=parent, id=wx.ID_ANY, title="", size=(395, 210))
        dialog_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        dialog.SetSizer(dialog_sizer)

        # header background
        header_win = wx.Window(parent=dialog, id=wx.ID_ANY, size=(395, 50))
        header_win.SetBackgroundColour(color_dark_grey)
        dialog_sizer.Add(header_win, 0, wx.EXPAND)
        header_win_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        header_win.SetSizer(header_win_sizer)

        # header text
        header_text = wx.StaticText(parent=header_win, id=wx.ID_ANY, label=title)
        header_text.SetFont(wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        header_text.SetForegroundColour(color_white)
        header_win_sizer.Add(header_text, 0, wx.CENTER | wx.TOP, 15)

        # white window
        back_window = wx.Window(parent=dialog, id=wx.ID_ANY, size=(310, 230))
        back_window.SetBackgroundColour(color_white)
        back_window_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        back_window.SetSizer(back_window_sizer)
        dialog_sizer.Add(back_window, 0, wx.EXPAND)

        back_window_sizer.AddSpacer(20)

        # the message
        message_text = wx.StaticText(parent=back_window, id=wx.ID_ANY, label=message)
        message_text.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False))
        message_text.SetForegroundColour(color_dark_grey)
        back_window_sizer.Add(message_text, 0, wx.CENTER | wx.TOP, 15)

        button_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)

        if is_ok_type:
            # just add an ok type button
            ok_btn = self.create_small_button(parent=back_window, length=100, text="OK",
                                              back_color=color_orange, text_color=color_white,
                                              click_handler=lambda ev: dialog.Destroy())
            button_sizer.Add(ok_btn, 1, wx.CENTER)
        else:

            def no_handler(e):
                if no_click_handler is not None:
                    no_click_handler(e)
                dialog.Destroy()
            no_btn = self.create_small_button(parent=back_window, length=100, text="NO",
                                              back_color=color_white, text_color=color_dark_grey,
                                              border_color=color_dark_grey,
                                              click_handler=no_handler)
            button_sizer.Add(no_btn, 1)

            button_sizer.AddSpacer(10)

            def yes_handler(e):
                if yes_click_handler is not None:
                    yes_click_handler(e)
                dialog.Destroy()
            yes_btn = self.create_small_button(parent=back_window, length=100, text="YES",
                                               back_color=color_orange, text_color=color_white,
                                               click_handler=yes_handler)
            button_sizer.Add(yes_btn, 1)

        back_window_sizer.Add(button_sizer, 1, wx.CENTER | wx.TOP, 10)

        dialog.Show()
        dialog.SendSizeEvent()
        return dialog

    # include the header always
    def create_header(self, parent):

        anchor_window = wx.Window(parent=parent, id=wx.ID_ANY, size=(600, 60))
        anchor_window.SetBackgroundColour(color_dark_grey)

        anchor_window_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)

        # load bitmap from file
        log_raw_bitmap = wx.Bitmap(name="assets/vo_logo.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        logo_bitmap = wx.StaticBitmap(parent=anchor_window, id=wx.ID_ANY)
        logo_bitmap.SetBitmap(log_raw_bitmap)
        # center in the middle, and give so
        anchor_window_sizer.Add(logo_bitmap, 0, wx.CENTER | wx.LEFT, 10)

        anchor_window_sizer.AddStretchSpacer(1)

        if self.logged_in:
            # create the login button
            login_window = wx.Window(parent=anchor_window, id=wx.ID_ANY, size=(175, 25))
            login_window.SetBackgroundColour(color_orange)

            login_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
            login_window.SetSizer(login_sizer)

            # login_raw_bitmap = wx.Bitmap(name="assets/login.png", type=wx.BITMAP_TYPE_PNG)
            # logout_bitmap = wx.StaticBitmap(parent=login_window, id=wx.ID_ANY)
            # logout_bitmap.SetBitmap(login_raw_bitmap)
            # login_sizer.Add(logout_bitmap, 0, wx.CENTER | wx.LEFT, 6)

            # and now the username
            login_user = wx.StaticText(parent=login_window, id=wx.ID_ANY, label=self.username_to_display)
            login_user.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
            login_user.SetForegroundColour(color_white)
            login_sizer.Add(login_user, 0, wx.CENTER | wx.LEFT, 5)

            anchor_window_sizer.Add(login_window, 0, wx.CENTER | wx.RIGHT, 5)

            # create the log out button
            logout_window = wx.Window(parent=anchor_window, id=wx.ID_ANY, size=(25, 25))
            logout_window.SetBackgroundColour(color_orange)

            logout_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
            logout_window.SetSizer(logout_sizer)

            logout_raw_bitmap = wx.Bitmap(name="assets/logout.png", type=wx.BITMAP_TYPE_PNG)
            logout_bitmap = wx.StaticBitmap(parent=logout_window, id=wx.ID_ANY)
            logout_bitmap.SetBitmap(logout_raw_bitmap)
            logout_sizer.Add(logout_bitmap, 1, wx.CENTER)
            logout_window.SetCursor(wx.Cursor(wx.CURSOR_HAND))
            anchor_window_sizer.Add(logout_window, 0, wx.CENTER | wx.RIGHT, 10)

            logout_window.Bind(wx.EVT_LEFT_DOWN, self.do_logout)
            logout_bitmap.Bind(wx.EVT_LEFT_DOWN, self.do_logout)

        else:
            pass
            login_btn = self.create_small_button(parent=anchor_window, length=150, text="LOGIN",
                                                 text_color=color_orange, back_color=color_dark_grey,
                                                 border_color=color_orange,
                                                 click_handler=self.show_login_form)
            anchor_window_sizer.Add(login_btn, 0, wx.CENTER | wx.RIGHT, 10)

        anchor_window.SetSizer(anchor_window_sizer)

        return anchor_window

    # and include the footer always
    def create_footer(self, parent):

        # footer bar
        anchor_window = wx.Window(parent=parent, id=wx.ID_ANY, size=(800, 35))
        anchor_window.SetBackgroundColour(color_dark_grey)
        anchor_window_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        anchor_window.SetSizer(anchor_window_sizer)

        # copyright
        copyright_text = wx.StaticText(parent=anchor_window, id=wx.ID_ANY, label="© VIDEOBSERVER 2016")
        copyright_text.SetFont(wx.Font(7, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False))
        copyright_text.SetForegroundColour(color_white)
        anchor_window_sizer.Add(copyright_text, 0, wx.CENTER | wx.LEFT, 20)

        version_text = wx.StaticText(parent=anchor_window, id=wx.ID_ANY, label="v: " + current_version)
        version_text.SetFont(wx.Font(7, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False))
        version_text.SetForegroundColour(color_white)
        anchor_window_sizer.Add(version_text, 0, wx.CENTER | wx.LEFT, 20)

        # a space in the middle
        anchor_window_sizer.AddStretchSpacer(1)

        # help
        help_text = wx.StaticText(parent=anchor_window, id=wx.ID_ANY, label="Help")
        help_text.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, True))
        help_text.SetForegroundColour(color_white)
        help_text.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        anchor_window_sizer.Add(help_text, 0, wx.CENTER | wx.RIGHT, 20)
        help_text.Bind(wx.EVT_LEFT_DOWN, self.go_to_help)

        return anchor_window

    def show_login_form(self, e):

        self.login_dialog = dialog = wx.Dialog(parent=self, id=wx.ID_ANY, title="", size=(310, 290))
        dialog_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        dialog.SetSizer(dialog_sizer)

        # header background
        header_win = wx.Window(parent=dialog, id=wx.ID_ANY, size=(310, 50))
        header_win.SetBackgroundColour(color_dark_grey)
        dialog_sizer.Add(header_win, 0, wx.EXPAND)
        header_win_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        header_win.SetSizer(header_win_sizer)

        # header text
        header_text = wx.StaticText(parent=header_win, id=wx.ID_ANY, label="LOGIN")
        header_text.SetFont(wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        header_text.SetForegroundColour(color_white)
        header_win_sizer.Add(header_text, 0, wx.CENTER | wx.TOP, 15)

        # white window
        back_window = wx.Window(parent=dialog, id=wx.ID_ANY, size=(310, 250))
        back_window.SetBackgroundColour(color_white)
        back_window_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        back_window.SetSizer(back_window_sizer)
        dialog_sizer.Add(back_window, 0, wx.EXPAND)

        # space before
        back_window_sizer.AddSpacer(10)

        # username
        username_label = wx.StaticText(parent=back_window, id=wx.ID_ANY, label="Email")
        username_label.SetFont(wx.Font(8, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False))
        username_label.SetForegroundColour(color_dark_grey)
        back_window_sizer.Add(username_label, 0, wx.LEFT, 20)
        saved_user = settings.get("login_user", "")
        username = wx.TextCtrl(parent=back_window, id=wx.ID_ANY, size=(270, 25), value=saved_user)
        back_window_sizer.Add(username, 0, wx.CENTER | wx.LEFT | wx.RIGHT, 20)

        # space before
        back_window_sizer.AddSpacer(10)

        # password
        password_label = wx.StaticText(parent=back_window, id=wx.ID_ANY, label="Password")
        password_label.SetFont(wx.Font(8, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False))
        password_label.SetForegroundColour(color_dark_grey)
        back_window_sizer.Add(password_label, 0, wx.LEFT, 20)
        saved_pass = settings.get("login_pass", "")
        password = wx.TextCtrl(parent=back_window, id=wx.ID_ANY, size=(270, 25), style=wx.TE_PASSWORD, value=saved_pass)
        back_window_sizer.Add(password, 0, wx.CENTER | wx.LEFT | wx.RIGHT, 20)

        # space before
        back_window_sizer.AddSpacer(15)

        # keep me logged in and forgot password
        remember_me_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        back_window_sizer.Add(remember_me_sizer, 0, wx.LEFT | wx.RIGHT, 20)

        remember_cb = wx.CheckBox(parent=back_window, id=wx.ID_ANY, label="Keep me logged in.")
        remember_cb.SetValue(True)
        remember_me_sizer.Add(remember_cb, 1)

        remember_me_sizer.AddStretchSpacer(1)

        lost_pass = wx.StaticText(parent=back_window, id=wx.ID_ANY, label="Forgot Password")
        lost_pass.SetFont(wx.Font(8, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, True))
        lost_pass.SetForegroundColour(color_dark_grey)
        lost_pass.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        lost_pass.Bind(event=wx.EVT_LEFT_DOWN, handler=self.lost_pass)
        remember_me_sizer.Add(lost_pass)

        # space before
        back_window_sizer.AddSpacer(15)

        # cancel and login button
        button_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        back_window_sizer.Add(button_sizer, 0, wx.LEFT | wx.RIGHT, 20)

        cancel_btn = self.create_small_button(parent=back_window, length=110, text="CANCEL",
                                              back_color=color_white, text_color=color_dark_grey,
                                              border_color=color_dark_grey,
                                              click_handler=lambda ev: dialog.Destroy())
        button_sizer.Add(cancel_btn, 1)

        button_sizer.AddStretchSpacer(2)

        login_btn = self.create_small_button(parent=back_window, length=100, text="LOGIN",
                                             back_color=color_orange, text_color=color_white,
                                             click_handler=lambda wv: self.do_login(username.GetValue(),
                                                                                    password.GetValue(),
                                                                                    remember_cb.GetValue()))
        button_sizer.Add(login_btn, 1)

        dialog.Show()
        dialog.SendSizeEvent()

    def go_to_help(self, e):
        webbrowser.open("https://www.videobserver.com/faqs/category/id/3/vo-converter", new=0, autoraise=True)

    def lost_pass(self, e):
        webbrowser.open("https://www.videobserver.com/forgot-password", new=0, autoraise=True)

    def do_login(self, username, password, remember):
        code, self.token = aws.get_token(username, password)
        if code == 200:
            self.login_dialog.Destroy()
            self.aws_data = aws.get_aws_data(self.token["token"])
            self.logged_in = True
            self.username_to_display = username

            if remember:
                # save the user in the settings
                settings.set("login_user", username)
                settings.set("login_pass", password)
                settings.save()

        if code == 2:
            dialog = self.create_alert_dialog(parent=self,
                                              title="Login Failed",
                                              message="Wrong user name or password",
                                              is_ok_type=True)
            print_mine("wrong user and pass")

    def do_logout(self, e):
        print_mine("Do LOGOUT")
        self.logged_in = False

    # create the home screen
    def create_main_screen(self):

        win = wx.Window(parent=self, id=wx.ID_ANY)
        win.SetBackgroundColour(color_white)
        # main sizer
        sizer = wx.BoxSizer(orient=wx.VERTICAL)
        win.SetSizer(sizer)

        # place header
        header_window = self.create_header(parent=win)
        sizer.Add(header_window)

        # what do you want to do?
        select_window = wx.Window(parent=win, id=wx.ID_ANY, size=(600, 100))
        select_window.SetBackgroundColour(color_white)
        select_window_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        select_window.SetSizer(select_window_sizer)

        select_text = wx.StaticText(parent=select_window, id=wx.ID_ANY, label="What do you want to do?")
        select_text.SetFont(wx.Font(12, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        select_text.SetForegroundColour(color_home_headers)
        select_window_sizer.Add(select_text, 0, wx.CENTER | wx.TOP, 40)
        sizer.Add(select_window)

        # create the buttons
        button_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        button_sizer.SetMinSize((600, 200))

        upload_btn = self.create_nav_button(parent=win,
                                            size=(190, 190),
                                            file="assets/home_convert_file.png",
                                            text="CONVERT FILE",
                                            back_color=color_home_back,
                                            text_color=color_home_text,
                                            hover_color=color_home_headers,
                                            click_handler=self.show_convert_join)

        convert_btn = self.create_nav_button(parent=win,
                                             size=(190, 190),
                                             file="assets/home_upload_file.png",
                                             text="UPLOAD",
                                             back_color=color_home_back,
                                             text_color=color_home_text,
                                             hover_color=color_home_headers,
                                             click_handler=self.show_upload)

        join_btn = self.create_nav_button(parent=win,
                                          size=(190, 190),
                                          file="assets/home_create_playlist.png",
                                          text="CREATE PLAYLIST",
                                          back_color=color_home_back,
                                          text_color=color_home_text,
                                          hover_color=color_home_headers,
                                          click_handler=self.show_playlist)

        button_sizer.Add(upload_btn)
        button_sizer.Add(convert_btn, 0, wx.LEFT, 5)
        button_sizer.Add(join_btn, 0, wx.LEFT, 5)
        sizer.Add(button_sizer, 0, wx.LEFT | wx.RIGHT, 10)

        # select a funtion?
        select_window = wx.Window(parent=win, id=wx.ID_ANY, size=(600, 100))
        select_window.SetBackgroundColour(color_white)
        select_window_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        select_window.SetSizer(select_window_sizer)

        select_text = wx.StaticText(parent=select_window, id=wx.ID_ANY, label="Select a function.")
        select_text.SetFont(wx.Font(12, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        select_text.SetForegroundColour(color_home_headers)
        select_window_sizer.Add(select_text, 0, wx.CENTER | wx.TOP, 40)
        sizer.Add(select_window)

        sizer.AddSpacer(10)

        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        return win

    # this is where you select convert a single file or join some
    def create_convert_join_screen(self):

        win = wx.Window(parent=self, id=wx.ID_ANY)
        win.SetBackgroundColour(color_white)
        # main sizer
        sizer = wx.BoxSizer(orient=wx.VERTICAL)
        win.SetSizer(sizer)

        # place header
        header_window = self.create_header(parent=win)
        sizer.Add(header_window)

        # what do you want to do?
        select_window = wx.Window(parent=win, id=wx.ID_ANY, size=(600, 100))
        select_window.SetBackgroundColour(color_white)
        select_window_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        select_window.SetSizer(select_window_sizer)

        select_text = wx.StaticText(parent=select_window, id=wx.ID_ANY, label="What do you want to do?")
        select_text.SetFont(wx.Font(12, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        select_text.SetForegroundColour(color_home_headers)
        select_window_sizer.Add(select_text, 0, wx.CENTER | wx.TOP, 40)
        sizer.Add(select_window)

        # create the buttons
        button_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        button_sizer.SetMinSize((600, 200))

        join_btn = self.create_nav_button(parent=win,
                                          size=(280, 190),
                                          file="assets/home_create_playlist.png",
                                          text="JOIN FILES",
                                          back_color=color_home_back,
                                          text_color=color_home_text,
                                          hover_color=color_home_headers,
                                          click_handler=self.show_join)

        convert_btn = self.create_nav_button(parent=win,
                                             size=(280, 190),
                                             file="assets/home_convert_file.png",
                                             text="CONVERT FILE",
                                             back_color=color_home_back,
                                             text_color=color_home_text,
                                             hover_color=color_home_headers,
                                             click_handler=self.show_convert)

        button_sizer.Add(join_btn)
        button_sizer.Add(convert_btn, 0, wx.LEFT, 5)
        sizer.Add(button_sizer, 0, wx.LEFT | wx.RIGHT, 10)

        # select a funtion?
        select_window = wx.Window(parent=win, id=wx.ID_ANY, size=(600, 100))
        select_window.SetBackgroundColour(color_white)
        select_window_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        select_window.SetSizer(select_window_sizer)

        select_text = wx.StaticText(parent=select_window, id=wx.ID_ANY, label="Select a function.")
        select_text.SetFont(wx.Font(12, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        select_text.SetForegroundColour(color_home_headers)
        select_window_sizer.Add(select_text, 0, wx.CENTER | wx.TOP, 40)
        sizer.Add(select_window)

        sizer.AddSpacer(10)

        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        return win

    # convert just one file
    def create_convert_screen(self):

        win = wx.Window(parent=self, id=wx.ID_ANY)
        win.SetBackgroundColour(color_white)
        # main sizer
        sizer = wx.BoxSizer(orient=wx.VERTICAL)
        win.SetSizer(sizer)

        # place header
        header_window = self.create_header(parent=win)
        sizer.Add(header_window)

        # conversion header
        conversion_header = wx.StaticText(parent=win, id=wx.ID_ANY, label="Conversion Options")
        sizer.Add(conversion_header, 0, wx.TOP | wx.LEFT, 10)

        # presets
        presets, choices = convert_functions.get_presets()
        conversion_presets = wx.RadioBox(parent=win, id=wx.ID_ANY, choices=choices, label=" ")
        sizer.Add(conversion_presets, 0, wx.LEFT, 10)
        conversion_presets.Bind(wx.EVT_RADIOBOX,
                                lambda x: self.set_current_preset(conversion_presets.GetStringSelection(),
                                                                  estimated_size_indicator))

        # drag list and add a file btn
        list_add = wx.Window(parent=win, id=wx.ID_ANY)
        list_add.SetBackgroundColour(color_white)
        list_add_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        list_add.SetSizer(list_add_sizer)
        sizer.Add(list_add, 0, wx.TOP, 10)

        if platform.system() == "Darwin":
            # convert_list = wx.ListView(parent=list_add, id=wx.ID_ANY, style=wx.LC_REPORT)
            convert_list = wx.ListView(list_add, -1, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        else:
            convert_list = wx.ListView(list_add, -1, style=wx.LC_REPORT)
        convert_list.AppendColumn("Drag & Drop to Convert or Add a File.", wx.LIST_FORMAT_CENTER, 400)
        list_add_sizer.Add(convert_list, 3, wx.LEFT, 10)

        # and the real label, so we can refer to it later
        estimated_size_indicator = wx.StaticText(parent=win, id=wx.ID_ANY, label="0 Mb")
        estimated_size_indicator.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        estimated_size_indicator.SetForegroundColour(color_dark_green)


        # begin the buttons

        up_down_buttons_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        list_add_sizer.Add(up_down_buttons_sizer, 0, wx.RIGHT | wx.LEFT, 10)

        up_raw_bitmap = wx.Bitmap(name="assets/up_arrow.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        up_bitmap = wx.StaticBitmap(parent=list_add, id=wx.ID_ANY)
        up_bitmap.SetBitmap(up_raw_bitmap)
        up_bitmap.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        # center in the middle, and give so
        up_down_buttons_sizer.Add(up_bitmap, 0, wx.TOP, 10)

        up_bitmap.Bind(event=wx.EVT_LEFT_DOWN, handler=lambda evt: self.move_up_list(convert_list))

        down_raw_bitmap = wx.Bitmap(name="assets/down_arrow.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        down_bitmap = wx.StaticBitmap(parent=list_add, id=wx.ID_ANY)
        down_bitmap.SetBitmap(down_raw_bitmap)
        down_bitmap.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        # center in the middle, and give so
        up_down_buttons_sizer.Add(down_bitmap, 0, wx.TOP | wx.BOTTOM, 30)

        down_bitmap.Bind(event=wx.EVT_LEFT_DOWN, handler=lambda evt: self.move_down_list(convert_list))

        delete_raw_bitmap = wx.Bitmap(name="assets/delete.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        delete_bitmap = wx.StaticBitmap(parent=list_add, id=wx.ID_ANY)
        delete_bitmap.SetBitmap(delete_raw_bitmap)
        delete_bitmap.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        # center in the middle, and give so
        up_down_buttons_sizer.Add(delete_bitmap, 0, wx.TOP, 30)

        delete_bitmap.Bind(event=wx.EVT_LEFT_DOWN, handler=lambda evt: self.delete_list(convert_list, estimated_size_indicator))

        # end the buttons

        right_part_sizer = wx.BoxSizer(orient=wx.VERTICAL)

        add_a_file = self.create_small_button(parent=list_add, length=150, text="ADD FILES",
                                              text_color=color_white, back_color=color_dark_grey,
                                              click_handler=lambda x: self.convert_browse_for_files(convert_list,
                                                                                                   estimated_size_indicator))

        right_part_sizer.Add(add_a_file)

        right_part_sizer.AddSpacer(20)

        list_add_sizer.Add(right_part_sizer, 1, wx.RIGHT, 10)

        sizer.AddSpacer(20)

        # Estimated size
        estimated_size_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(estimated_size_sizer, 0, wx.LEFT, 10)
        # the header
        estimated_size_header = wx.StaticText(parent=win, id=wx.ID_ANY, label="Estimated Size ")
        estimated_size_header.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        estimated_size_header.SetForegroundColour(color_dark_green)
        estimated_size_sizer.Add(estimated_size_header)
        # we add it now
        estimated_size_sizer.Add(estimated_size_indicator)

        current_preset = conversion_presets.GetStringSelection()
        self.set_current_preset(current_preset, estimated_size_indicator)

        # test the drop target stuff?
        list_add.SetDropTarget(ConvertFileDrop(callback=lambda filenames, estimate: self.convert_add_files(filenames,
                                                                                                           convert_list,
                                                                                                           estimated_size_indicator)))

        sizer.AddSpacer(70)

        # now the destination header
        destination_header = wx.StaticText(parent=win, id=wx.ID_ANY, label="Destination")
        sizer.Add(destination_header, 0, wx.LEFT, 10)

        # and the destination stuff
        destination_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(destination_sizer, 0, wx.LEFT | wx.RIGHT, 10)

        # first the file picker
        destination_text = wx.TextCtrl(parent=win, id=wx.ID_ANY, size=(200, 25))
        destination_sizer.Add(destination_text, wx.CENTER)

        if self.destination_dir != "":
            destination_text.SetLabel(self.destination_dir)

        # then the cancel button
        cancel_btn = self.create_small_button(parent=win, length=80, text="BROWSE",
                                              text_color=color_white, back_color=color_dark_grey,
                                              click_handler=lambda x: self.set_destination_dir(destination_text))
        destination_sizer.Add(cancel_btn, 1, wx.LEFT, 10)

        # then the cancel button
        cancel_btn = self.create_small_button(parent=win, length=100, text="GO BACK",
                                              text_color=color_dark_grey, back_color=color_white,
                                              click_handler=self.show_main,
                                              border_color=color_dark_grey)
        destination_sizer.Add(cancel_btn, 1, wx.LEFT, 10)

        # then the convert button
        convert_btn = self.create_small_button(parent=win, length=150, text="CONVERT",
                                               text_color=color_white, back_color=color_orange,
                                               click_handler=self.show_convert_progress)
        destination_sizer.Add(convert_btn, 2, wx.RIGHT | wx.LEFT, 5)

        sizer.AddSpacer(17)

        # place footer
        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        return win, estimated_size_indicator

    def create_convert_progress(self):
        win = wx.Window(parent=self, id=wx.ID_ANY)
        win.SetBackgroundColour(color_white)
        # main sizer
        sizer = wx.BoxSizer(orient=wx.VERTICAL)
        win.SetSizer(sizer)

        # place header
        header_window = self.create_header(parent=win)
        sizer.Add(header_window)

        # some space
        sizer.AddSpacer(115)

        # converting... file
        converting_header_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(converting_header_sizer, 0, wx.LEFT, 65)
        # the converting...
        converting_label = wx.StaticText(parent=win, id=wx.ID_ANY, label="Converting...")
        converting_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        converting_label.SetForegroundColour(color_dark_grey)
        converting_header_sizer.Add(converting_label)
        # the file name
        converting_file_label = wx.StaticText(parent=win, id=wx.ID_ANY, label=self.filenames[0].file)
        converting_file_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False))
        converting_file_label.SetForegroundColour(color_dark_grey)
        converting_header_sizer.Add(converting_file_label, 0, wx.LEFT, 10)

        sizer.AddSpacer(10)

        # convert box
        convert_box = wx.StaticBox(parent=win, id=wx.ID_ANY, size=(475, 90), label=" ")
        convert_box_sizer = wx.StaticBoxSizer(wx.HORIZONTAL, convert_box, label=" ")
        convert_box.SetSizer(convert_box_sizer)
        sizer.Add(convert_box, 0, wx.LEFT, 65)
        # convert icon
        # load bitmap from file
        raw_bitmap = wx.Bitmap(name="assets/progress_icon.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        static_bitmap = wx.StaticBitmap(parent=convert_box, id=wx.ID_ANY)
        static_bitmap.SetBitmap(raw_bitmap)
        # center in the middle, and give so
        convert_box_sizer.Add(static_bitmap, 0, wx.CENTER | wx.LEFT, 22)
        # now we add vertical sizer
        vertical_spacer = wx.BoxSizer(orient=wx.VERTICAL)
        convert_box_sizer.Add(vertical_spacer, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 20)

        estimate_text = wx.StaticText(parent=convert_box, id=wx.ID_ANY, label="Estimated time ? 0%")
        vertical_spacer.Add(estimate_text, 0, wx.ALIGN_LEFT | wx.TOP, 10)

        convert_gauge = wx.Gauge(parent=convert_box, id=wx.ID_ANY, range=100, size=(375, 15))
        vertical_spacer.Add(convert_gauge, 0, wx.TOP, 10)

        sizer.AddSpacer(100)

        cancel_btn = self.create_small_button(parent=win, length=105, text="CANCEL",
                                              back_color=color_white, text_color=color_black,
                                              click_handler=self.cancel_current_thread,
                                              border_color=color_dark_grey)
        sizer.Add(cancel_btn, 0, wx.ALIGN_CENTER)

        sizer.AddSpacer(50)

        # place footer
        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        return win, convert_gauge, estimate_text, converting_file_label

    def create_convert_complete(self):
        win = wx.Window(parent=self, id=wx.ID_ANY)
        win.SetBackgroundColour(color_white)
        # main sizer
        sizer = wx.BoxSizer(orient=wx.VERTICAL)
        win.SetSizer(sizer)

        # place header
        header_window = self.create_header(parent=win)
        sizer.Add(header_window)

        # what do you want to do?
        select_window = wx.Window(parent=win, id=wx.ID_ANY, size=(600, 100))
        select_window.SetBackgroundColour(color_white)
        select_window_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        select_window.SetSizer(select_window_sizer)

        select_text = wx.StaticText(parent=select_window, id=wx.ID_ANY, label="What do you want to do?")
        select_text.SetFont(wx.Font(12, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        select_text.SetForegroundColour(color_home_headers)
        select_window_sizer.Add(select_text, 0, wx.CENTER | wx.TOP, 40)
        sizer.Add(select_window)

        sizer.AddSpacer(25)

        # done icon
        # load bitmap from file
        log_raw_bitmap = wx.Bitmap(name="assets/done_icon.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        logo_bitmap = wx.StaticBitmap(parent=win, id=wx.ID_ANY)
        logo_bitmap.SetBitmap(log_raw_bitmap)
        # center in the middle, and give so
        sizer.Add(logo_bitmap, 0, wx.CENTER)

        sizer.AddSpacer(20)

        # converting... file
        converting_header_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(converting_header_sizer, 0, wx.CENTER | wx.TOP, 20)
        # the converting...
        converting_label = wx.StaticText(parent=win, id=wx.ID_ANY, label="Complete: ")
        converting_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        converting_label.SetForegroundColour(color_dark_grey)
        converting_header_sizer.Add(converting_label)

        if self.time_delta != 0:

            seconds = int(self.time_delta % 60)
            minutes = int(self.time_delta / 60)
            hours = int(self.time_delta / (60 * 60))
            elapsed_time = " t:" + format(hours, "02d") + ":" +  format(minutes, "02d") + ":" + format(seconds, "02d")
        else:
            elapsed_time = ""

        # the file name
        converting_file_label = wx.StaticText(parent=win, id=wx.ID_ANY, label=self.final_path + elapsed_time)
        converting_file_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False))
        converting_file_label.SetForegroundColour(color_dark_grey)
        converting_header_sizer.Add(converting_file_label, 0, wx.LEFT, 10)

        sizer.AddSpacer(65)

        button_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(button_sizer, 1, wx.CENTER)

        cancel_btn = self.create_small_button(parent=win, length=150, text="GO BACK",
                                              back_color=color_white, text_color=color_black,
                                              click_handler=self.show_main,
                                              border_color=color_dark_grey)
        button_sizer.Add(cancel_btn)

        button_sizer.AddSpacer(20)

        open_btn = self.create_small_button(parent=win, length=150, text="OPEN",
                                            back_color=color_white, text_color=color_black,
                                            click_handler=self.open_final_path,
                                            border_color=color_dark_grey)
        button_sizer.Add(open_btn)

        button_sizer.AddSpacer(20)

        upload_btn = self.create_small_button(parent=win, length=150, text="UPLOAD",
                                              back_color=color_orange, text_color=color_white,
                                              click_handler=self.show_upload_progress)
        button_sizer.Add(upload_btn)

        sizer.AddSpacer(55)

        # place footer
        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        return win

    def move_up_list(self, the_list):
        index = the_list.GetFirstSelected()
        if index == -1:
            return
        self.filenames[index - 1], self.filenames[index] = self.filenames[index], self.filenames[index - 1]
        # update the list
        the_list.DeleteAllItems()
        for file in self.filenames:
            if type(file) is str:
                the_list.Append([file])
            else:
                the_list.Append([file.file])

        the_list.Select(index - 1)

    def move_down_list(self, the_list):
        index = the_list.GetFirstSelected()
        if index == -1:
            return
        self.filenames[index + 1], self.filenames[index] = self.filenames[index], self.filenames[index + 1]
        # update the list
        the_list.DeleteAllItems()
        for file in self.filenames:
            if type(file) is str:
                the_list.Append([file])
            else:
                the_list.Append([file.file])
        the_list.Select(index + 1)

    def delete_list(self, the_list, estimate):
        index = the_list.GetFirstSelected()
        if index == -1:
            return
        del self.filenames[index]
        # update the list
        the_list.DeleteAllItems()
        for file in self.filenames:
            if type(file) is str:
                the_list.Append([file])
            else:
                the_list.Append([file.file])
        the_list.Select(index + 1)

        if estimate is not None:
            self.calculate_conversion_estimates(estimate)

        # join several files
    def create_join_screen(self):

        win = wx.Window(parent=self, id=wx.ID_ANY)
        win.SetBackgroundColour(color_white)
        # main sizer
        sizer = wx.BoxSizer(orient=wx.VERTICAL)
        win.SetSizer(sizer)

        # place header
        header_window = self.create_header(parent=win)
        sizer.Add(header_window)

        # conversion header
        conversion_header = wx.StaticText(parent=win, id=wx.ID_ANY, label="Conversion Options")
        sizer.Add(conversion_header, 0, wx.TOP | wx.LEFT, 10)

        # presets
        presets, choices = convert_functions.get_presets()
        conversion_presets = wx.RadioBox(parent=win, id=wx.ID_ANY, choices=choices, label=" ")
        sizer.Add(conversion_presets, 0, wx.LEFT, 10)
        conversion_presets.Bind(wx.EVT_RADIOBOX,
                                lambda x: self.set_current_preset(conversion_presets.GetStringSelection(),
                                                                  estimated_size_indicator))

        # drag list and add a file btn
        list_add = wx.Window(parent=win, id=wx.ID_ANY)
        list_add.SetBackgroundColour(color_white)
        list_add_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        list_add.SetSizer(list_add_sizer)
        sizer.Add(list_add, 0, wx.TOP, 10)

        if platform.system() == "Darwin":
            # convert_list = wx.ListView(parent=list_add, id=wx.ID_ANY, style=wx.LC_REPORT)
            convert_list = wx.ListView(list_add, -1, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        else:
            convert_list = wx.ListView(list_add, -1, style=wx.LC_REPORT)
        convert_list.AppendColumn("Drag & Drop to Join or Add a File.", wx.LIST_FORMAT_CENTER, 400)
        list_add_sizer.Add(convert_list, 3, wx.LEFT, 10)

        sizer.AddSpacer(20)

        # and the real label, so we can refer to it later
        estimated_size_indicator = wx.StaticText(parent=win, id=wx.ID_ANY, label="0 Mb")
        estimated_size_indicator.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        estimated_size_indicator.SetForegroundColour(color_dark_green)

        # begin the buttons

        up_down_buttons_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        list_add_sizer.Add(up_down_buttons_sizer, 0, wx.RIGHT | wx.LEFT, 10)

        up_raw_bitmap = wx.Bitmap(name="assets/up_arrow.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        up_bitmap = wx.StaticBitmap(parent=list_add, id=wx.ID_ANY)
        up_bitmap.SetBitmap(up_raw_bitmap)
        up_bitmap.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        # center in the middle, and give so
        up_down_buttons_sizer.Add(up_bitmap, 0, wx.TOP, 10)

        up_bitmap.Bind(event=wx.EVT_LEFT_DOWN, handler=lambda evt: self.move_up_list(convert_list))

        down_raw_bitmap = wx.Bitmap(name="assets/down_arrow.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        down_bitmap = wx.StaticBitmap(parent=list_add, id=wx.ID_ANY)
        down_bitmap.SetBitmap(down_raw_bitmap)
        down_bitmap.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        # center in the middle, and give so
        up_down_buttons_sizer.Add(down_bitmap, 0, wx.TOP | wx.BOTTOM, 30)

        down_bitmap.Bind(event=wx.EVT_LEFT_DOWN, handler=lambda evt: self.move_down_list(convert_list))

        delete_raw_bitmap = wx.Bitmap(name="assets/delete.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        delete_bitmap = wx.StaticBitmap(parent=list_add, id=wx.ID_ANY)
        delete_bitmap.SetBitmap(delete_raw_bitmap)
        delete_bitmap.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        # center in the middle, and give so
        up_down_buttons_sizer.Add(delete_bitmap, 0, wx.TOP, 30)

        delete_bitmap.Bind(event=wx.EVT_LEFT_DOWN, handler=lambda evt: self.delete_list(convert_list, estimated_size_indicator))

        # end the buttons

        right_part_sizer = wx.BoxSizer(orient=wx.VERTICAL)

        add_a_file = self.create_small_button(parent=list_add, length=150, text="ADD FILES",
                                              text_color=color_white, back_color=color_dark_grey,
                                              click_handler=lambda x: self.convert_browse_for_files(convert_list,
                                                                                                    estimated_size_indicator))

        right_part_sizer.Add(add_a_file)

        right_part_sizer.AddSpacer(20)

        list_add_sizer.Add(right_part_sizer, 1, wx.RIGHT, 10)

        # Estimated size
        estimated_size_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(estimated_size_sizer, 0, wx.LEFT, 10)
        # the header
        estimated_size_header = wx.StaticText(parent=win, id=wx.ID_ANY, label="Estimated Size ")
        estimated_size_header.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        estimated_size_header.SetForegroundColour(color_dark_green)
        estimated_size_sizer.Add(estimated_size_header)
        # we add it now
        estimated_size_sizer.Add(estimated_size_indicator)

        current_preset = conversion_presets.GetStringSelection()
        self.set_current_preset(current_preset, estimated_size_indicator)

        # test the drop target stuff?
        list_add.SetDropTarget(ConvertFileDrop(callback=lambda filenames, estimate: self.join_add_files(filenames,
                                                                                                        convert_list,
                                                                                                        estimated_size_indicator,
                                                                                                        final_file_name)))

        final_file_name_label = wx.StaticText(parent=win, id=wx.ID_ANY, label="Final file name:")
        sizer.Add(final_file_name_label, 0, wx.LEFT | wx.TOP, 10)

        final_file_name = wx.TextCtrl(parent=win, id=wx.ID_ANY)
        sizer.Add(final_file_name, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 10)
        final_file_name.Bind(wx.EVT_TEXT, lambda evt: self.set_final_filename(evt))

        sizer.AddSpacer(15)

        # now the destination header
        destination_header = wx.StaticText(parent=win, id=wx.ID_ANY, label="Destination")
        sizer.Add(destination_header, 0, wx.LEFT, 10)

        # and the destination stuff
        destination_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(destination_sizer, 0, wx.LEFT | wx.RIGHT, 10)

        # first the file picker
        destination_text = wx.TextCtrl(parent=win, id=wx.ID_ANY, size=(200, 25))
        destination_sizer.Add(destination_text, wx.CENTER)

        if self.destination_dir != "":
            destination_text.SetLabel(self.destination_dir)

        # then the cancel button
        cancel_btn = self.create_small_button(parent=win, length=80, text="BROWSE",
                                              text_color=color_white, back_color=color_dark_grey,
                                              click_handler=lambda x: self.set_destination_dir(destination_text))
        destination_sizer.Add(cancel_btn, 1, wx.LEFT, 10)

        # then the cancel button
        cancel_btn = self.create_small_button(parent=win, length=100, text="GO BACK",
                                              text_color=color_dark_grey, back_color=color_white,
                                              click_handler=self.show_main,
                                              border_color=color_dark_grey)
        destination_sizer.Add(cancel_btn, 1, wx.LEFT, 10)

        # then the convert button
        convert_btn = self.create_small_button(parent=win, length=150, text="JOIN",
                                               text_color=color_white, back_color=color_orange,
                                               click_handler=self.show_join_progress)
        destination_sizer.Add(convert_btn, 2, wx.RIGHT | wx.LEFT, 5)

        sizer.AddSpacer(13)

        # place footer
        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        return win, estimated_size_indicator, final_file_name

    def create_join_progress(self):
        win = wx.Window(parent=self, id=wx.ID_ANY)
        win.SetBackgroundColour(color_white)
        # main sizer
        sizer = wx.BoxSizer(orient=wx.VERTICAL)
        win.SetSizer(sizer)

        # place header
        header_window = self.create_header(parent=win)
        sizer.Add(header_window)

        # some space
        sizer.AddSpacer(115)

        # converting... file
        converting_header_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(converting_header_sizer, 0, wx.LEFT, 65)
        # the converting...
        converting_label = wx.StaticText(parent=win, id=wx.ID_ANY, label="Joining...")
        converting_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        converting_label.SetForegroundColour(color_dark_grey)
        converting_header_sizer.Add(converting_label)
        # the file name
        converting_file_label = wx.StaticText(parent=win, id=wx.ID_ANY, label=self.filenames[0].file)
        converting_file_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False))
        converting_file_label.SetForegroundColour(color_dark_grey)
        converting_header_sizer.Add(converting_file_label, 0, wx.LEFT, 10)

        sizer.AddSpacer(10)

        # convert box
        convert_box = wx.StaticBox(parent=win, id=wx.ID_ANY, size=(475, 90), label=" ")
        convert_box_sizer = wx.StaticBoxSizer(wx.HORIZONTAL, convert_box, label=" ")
        convert_box.SetSizer(convert_box_sizer)
        sizer.Add(convert_box, 0, wx.LEFT, 65)
        # convert icon
        # load bitmap from file
        raw_bitmap = wx.Bitmap(name="assets/progress_icon.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        static_bitmap = wx.StaticBitmap(parent=convert_box, id=wx.ID_ANY)
        static_bitmap.SetBitmap(raw_bitmap)
        # center in the middle, and give so
        convert_box_sizer.Add(static_bitmap, 0, wx.CENTER | wx.LEFT, 22)
        # now we add vertical sizer
        vertical_spacer = wx.BoxSizer(orient=wx.VERTICAL)
        convert_box_sizer.Add(vertical_spacer, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 20)

        estimate_text = wx.StaticText(parent=convert_box, id=wx.ID_ANY, label="Estimated time ? 0%")
        vertical_spacer.Add(estimate_text, 0, wx.ALIGN_LEFT | wx.TOP, 10)

        convert_gauge = wx.Gauge(parent=convert_box, id=wx.ID_ANY, range=100, size=(375, 15))
        vertical_spacer.Add(convert_gauge, 0, wx.TOP, 10)

        sizer.AddSpacer(100)

        cancel_btn = self.create_small_button(parent=win, length=105, text="CANCEL",
                                              back_color=color_white, text_color=color_black,
                                              click_handler=self.cancel_current_thread,
                                              border_color=color_dark_grey)
        sizer.Add(cancel_btn, 0, wx.ALIGN_CENTER)

        sizer.AddSpacer(50)

        # place footer
        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        return win, convert_gauge, estimate_text, converting_file_label

    def create_join_complete(self):
        win = wx.Window(parent=self, id=wx.ID_ANY)
        win.SetBackgroundColour(color_white)
        # main sizer
        sizer = wx.BoxSizer(orient=wx.VERTICAL)
        win.SetSizer(sizer)

        # place header
        header_window = self.create_header(parent=win)
        sizer.Add(header_window)

        # what do you want to do?
        select_window = wx.Window(parent=win, id=wx.ID_ANY, size=(600, 100))
        select_window.SetBackgroundColour(color_white)
        select_window_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        select_window.SetSizer(select_window_sizer)

        select_text = wx.StaticText(parent=select_window, id=wx.ID_ANY, label="What do you want to do?")
        select_text.SetFont(wx.Font(12, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        select_text.SetForegroundColour(color_home_headers)
        select_window_sizer.Add(select_text, 0, wx.CENTER | wx.TOP, 40)
        sizer.Add(select_window)

        sizer.AddSpacer(25)

        # done icon
        # load bitmap from file
        log_raw_bitmap = wx.Bitmap(name="assets/done_icon.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        logo_bitmap = wx.StaticBitmap(parent=win, id=wx.ID_ANY)
        logo_bitmap.SetBitmap(log_raw_bitmap)
        # center in the middle, and give so
        sizer.Add(logo_bitmap, 0, wx.CENTER)

        sizer.AddSpacer(20)

        # converting... file
        converting_header_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(converting_header_sizer, 0, wx.CENTER | wx.TOP, 20)

        if self.time_delta != 0:

            seconds = int(self.time_delta % 60)
            minutes = int(self.time_delta / 60)
            hours = int(self.time_delta / (60 * 60))
            elapsed_time = " t:" + format(hours, "02d") + ":" + format(minutes, "02d") + ":" + format(seconds, "02d")
        else:
            elapsed_time = ""

        # the converting...
        converting_label = wx.StaticText(parent=win, id=wx.ID_ANY, label="Complete: ")
        converting_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        converting_label.SetForegroundColour(color_dark_grey)
        converting_header_sizer.Add(converting_label)
        # the file name
        converting_file_label = wx.StaticText(parent=win, id=wx.ID_ANY, label=self.final_path + elapsed_time)
        converting_file_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False))
        converting_file_label.SetForegroundColour(color_dark_grey)
        converting_header_sizer.Add(converting_file_label, 0, wx.LEFT, 10)

        sizer.AddSpacer(55)

        button_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(button_sizer, 1, wx.CENTER)

        cancel_btn = self.create_small_button(parent=win, length=150, text="GO BACK",
                                              back_color=color_white, text_color=color_black,
                                              click_handler=self.show_main,
                                              border_color=color_dark_grey)
        button_sizer.Add(cancel_btn)

        button_sizer.AddSpacer(20)

        open_btn = self.create_small_button(parent=win, length=150, text="OPEN",
                                            back_color=color_white, text_color=color_black,
                                            click_handler=self.open_final_path,
                                            border_color=color_dark_grey)
        button_sizer.Add(open_btn)

        button_sizer.AddSpacer(20)

        upload_btn = self.create_small_button(parent=win, length=150, text="UPLOAD",
                                              back_color=color_orange, text_color=color_white,
                                              click_handler=self.show_upload_progress)
        button_sizer.Add(upload_btn)

        sizer.AddSpacer(55)

        # place footer
        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        return win

    # upload multiple files
    def create_upload_screen(self):

        win = wx.Window(parent=self, id=wx.ID_ANY)
        win.SetBackgroundColour(color_white)
        # main sizer
        sizer = wx.BoxSizer(orient=wx.VERTICAL)
        win.SetSizer(sizer)

        # place header
        header_window = self.create_header(parent=win)
        sizer.Add(header_window)

        # drag list and add a file btn
        list_add = wx.Window(parent=win, id=wx.ID_ANY, size=(600, 170))
        list_add.SetBackgroundColour(color_white)
        list_add_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        list_add.SetSizer(list_add_sizer)
        sizer.Add(list_add, 0, wx.TOP, 10)

        if platform.system() == "Darwin":
            convert_list = wx.ListView(list_add, -1)
        else:
            convert_list = wx.ListView(parent=list_add, winid=wx.ID_ANY, style=wx.LC_REPORT)
        convert_list.AppendColumn("Drag & Drop to Upload or Add a File.", wx.LIST_FORMAT_CENTER, 400)
        list_add_sizer.Add(convert_list, 3, wx.LEFT, 10)


        # begin the buttons

        up_down_buttons_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        list_add_sizer.Add(up_down_buttons_sizer, 0, wx.RIGHT | wx.LEFT, 10)

        up_raw_bitmap = wx.Bitmap(name="assets/up_arrow.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        up_bitmap = wx.StaticBitmap(parent=list_add, id=wx.ID_ANY)
        up_bitmap.SetBitmap(up_raw_bitmap)
        up_bitmap.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        # center in the middle, and give so
        up_down_buttons_sizer.Add(up_bitmap, 0, wx.TOP, 10)

        up_bitmap.Bind(event=wx.EVT_LEFT_DOWN, handler=lambda evt: self.move_up_list(convert_list))

        down_raw_bitmap = wx.Bitmap(name="assets/down_arrow.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        down_bitmap = wx.StaticBitmap(parent=list_add, id=wx.ID_ANY)
        down_bitmap.SetBitmap(down_raw_bitmap)
        down_bitmap.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        # center in the middle, and give so
        up_down_buttons_sizer.Add(down_bitmap, 0, wx.TOP | wx.BOTTOM, 30)

        down_bitmap.Bind(event=wx.EVT_LEFT_DOWN, handler=lambda evt: self.move_down_list(convert_list))

        delete_raw_bitmap = wx.Bitmap(name="assets/delete.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        delete_bitmap = wx.StaticBitmap(parent=list_add, id=wx.ID_ANY)
        delete_bitmap.SetBitmap(delete_raw_bitmap)
        delete_bitmap.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        # center in the middle, and give so
        up_down_buttons_sizer.Add(delete_bitmap, 0, wx.TOP, 30)

        delete_bitmap.Bind(event=wx.EVT_LEFT_DOWN, handler=lambda evt: self.delete_list(convert_list, None))

        # end the buttons

        # test the drop target stuff?
        list_add.SetDropTarget(UploadFileDrop(callback=lambda filenames: self.upload_add_files(filenames, convert_list)))

        add_a_file = self.create_small_button(parent=list_add, length=150, text="ADD FILES",
                                              text_color=color_white, back_color=color_dark_grey,
                                              click_handler=lambda x: self.upload_browse_for_files(convert_list))
        list_add_sizer.Add(add_a_file, 1, wx.RIGHT, 10)

        sizer.AddSpacer(180)

        # and the destination stuff
        destination_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(destination_sizer, 0, wx.LEFT | wx.RIGHT, 10)

        destination_sizer.AddStretchSpacer(5)

        # then the cancel button
        cancel_btn = self.create_small_button(parent=win, length=100, text="GO BACK",
                                              text_color=color_dark_grey, back_color=color_white,
                                              click_handler=self.show_main,
                                              border_color=color_dark_grey)
        destination_sizer.Add(cancel_btn, 1)

        # then the convert button
        convert_btn = self.create_small_button(parent=win, length=150, text="UPLOAD",
                                               text_color=color_white, back_color=color_orange,
                                               click_handler=self.show_upload_progress)
        destination_sizer.Add(convert_btn, 2, wx.LEFT, 10)

        sizer.AddSpacer(20)

        # place footer
        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        return win

    def create_upload_progress(self):
        win = wx.Window(parent=self, id=wx.ID_ANY)
        win.SetBackgroundColour(color_white)
        # main sizer
        sizer = wx.BoxSizer(orient=wx.VERTICAL)
        win.SetSizer(sizer)

        # place header
        header_window = self.create_header(parent=win)
        sizer.Add(header_window)

        # some space
        sizer.AddSpacer(115)

        # converting... file
        converting_header_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(converting_header_sizer, 0, wx.LEFT, 65)
        # the converting...
        converting_label = wx.StaticText(parent=win, id=wx.ID_ANY, label="Uploading...")
        converting_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        converting_label.SetForegroundColour(color_dark_grey)
        converting_header_sizer.Add(converting_label)
        # the file name
        converting_file_label = wx.StaticText(parent=win, id=wx.ID_ANY, label=self.filenames[0])
        converting_file_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False))
        converting_file_label.SetForegroundColour(color_dark_grey)
        converting_header_sizer.Add(converting_file_label, 0, wx.LEFT, 10)

        sizer.AddSpacer(10)

        # convert box
        convert_box = wx.StaticBox(parent=win, id=wx.ID_ANY, size=(475, 90))
        convert_box_sizer = wx.StaticBoxSizer(wx.HORIZONTAL, convert_box)
        convert_box.SetSizer(convert_box_sizer)
        sizer.Add(convert_box, 0, wx.LEFT, 65)
        # convert icon
        # load bitmap from file
        raw_bitmap = wx.Bitmap(name="assets/progress_icon.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        static_bitmap = wx.StaticBitmap(parent=convert_box, id=wx.ID_ANY)
        static_bitmap.SetBitmap(raw_bitmap)
        # center in the middle, and give so
        convert_box_sizer.Add(static_bitmap, 0, wx.CENTER | wx.LEFT, 22)
        # now we add vertical sizer
        vertical_spacer = wx.BoxSizer(orient=wx.VERTICAL)
        convert_box_sizer.Add(vertical_spacer, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 20)

        estimate_text = wx.StaticText(parent=convert_box, id=wx.ID_ANY, label="Estimated time ? 0%")
        vertical_spacer.Add(estimate_text, 0, wx.ALIGN_LEFT | wx.TOP, 10)

        convert_gauge = wx.Gauge(parent=convert_box, id=wx.ID_ANY, range=100, size=(375, 15))
        vertical_spacer.Add(convert_gauge, 0, wx.TOP, 10)

        sizer.AddSpacer(100)

        cancel_btn = self.create_small_button(parent=win, length=105, text="CANCEL",
                                              back_color=color_white, text_color=color_black,
                                              click_handler=self.cancel_current_thread,
                                              border_color=color_dark_grey)
        sizer.Add(cancel_btn, 0, wx.ALIGN_CENTER)

        sizer.AddSpacer(40)

        # place footer
        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        return win, convert_gauge, estimate_text, converting_file_label

    def create_upload_complete(self):
        win = wx.Window(parent=self, id=wx.ID_ANY)
        win.SetBackgroundColour(color_white)
        # main sizer
        sizer = wx.BoxSizer(orient=wx.VERTICAL)
        win.SetSizer(sizer)

        # place header
        header_window = self.create_header(parent=win)
        sizer.Add(header_window)

        # what do you want to do?
        select_window = wx.Window(parent=win, id=wx.ID_ANY, size=(600, 100))
        select_window.SetBackgroundColour(color_white)
        select_window_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        select_window.SetSizer(select_window_sizer)

        select_text = wx.StaticText(parent=select_window, id=wx.ID_ANY, label="Upload Complete...")
        select_text.SetFont(wx.Font(12, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        select_text.SetForegroundColour(color_home_headers)
        select_window_sizer.Add(select_text, 0, wx.CENTER | wx.TOP, 40)
        sizer.Add(select_window)

        sizer.AddSpacer(25)

        # done icon
        # load bitmap from file
        log_raw_bitmap = wx.Bitmap(name="assets/done_icon.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        logo_bitmap = wx.StaticBitmap(parent=win, id=wx.ID_ANY)
        logo_bitmap.SetBitmap(log_raw_bitmap)
        # center in the middle, and give so
        sizer.Add(logo_bitmap, 0, wx.CENTER)

        sizer.AddSpacer(20)

        # converting... file
        converting_header_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(converting_header_sizer, 0, wx.CENTER | wx.TOP, 20)
        # the converting...
        converting_label = wx.StaticText(parent=win, id=wx.ID_ANY, label="Complete: ")
        converting_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        converting_label.SetForegroundColour(color_dark_grey)
        converting_header_sizer.Add(converting_label)
        # the file name
        converting_file_label = wx.StaticText(parent=win, id=wx.ID_ANY, label=self.final_path)
        converting_file_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False))
        converting_file_label.SetForegroundColour(color_dark_grey)
        converting_header_sizer.Add(converting_file_label, 0, wx.LEFT, 10)

        sizer.AddSpacer(55)

        button_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(button_sizer, 1, wx.CENTER)

        cancel_btn = self.create_small_button(parent=win, length=150, text="GO BACK",
                                              back_color=color_white, text_color=color_black,
                                              click_handler=self.show_main,
                                              border_color=color_dark_grey)
        button_sizer.Add(cancel_btn)

        sizer.AddSpacer(55)

        # place footer
        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        return win

    # convert just one file
    def create_playlist_screen(self):

        win = wx.Window(parent=self, id=wx.ID_ANY)
        win.SetBackgroundColour(color_white)
        # main sizer
        sizer = wx.BoxSizer(orient=wx.VERTICAL)
        win.SetSizer(sizer)

        # place header
        header_window = self.create_header(parent=win)
        sizer.Add(header_window)

        # # conversion header
        # conversion_header = wx.StaticText(parent=win, id=wx.ID_ANY, label="Conversion Options")
        # sizer.Add(conversion_header, 0, wx.TOP | wx.LEFT, 10)
        #
        # # presets
        # presets, choices = convert_functions.get_presets()
        # conversion_presets = wx.RadioBox(parent=win, id=wx.ID_ANY, choices=choices,
        #                                  style=wx.BORDER_NONE)
        # sizer.Add(conversion_presets, 0, wx.LEFT, 10)
        # conversion_presets.Bind(wx.EVT_RADIOBOX,
        #                         lambda x: self.set_current_preset(conversion_presets.GetStringSelection(),
        #                                                           estimated_size_indicator))

        # drag list and add a file btn
        list_add = wx.Window(parent=win, id=wx.ID_ANY, size=(600, 245))
        list_add.SetBackgroundColour(color_white)
        list_add_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        list_add.SetSizer(list_add_sizer)
        sizer.Add(list_add, 0, wx.TOP, 10)

        if platform.system() == "Darwin":
            # convert_list = wx.ListView(parent=list_add, id=wx.ID_ANY, style=wx.LC_REPORT)
            convert_list = wx.ListView(list_add, -1, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        else:
            convert_list = wx.ListView(list_add, -1, style=wx.LC_REPORT)
        convert_list.AppendColumn("Drag & Drop to Create a Playlist or Add a File.", wx.LIST_FORMAT_CENTER, 400)
        list_add_sizer.Add(convert_list, 3, wx.RIGHT | wx.LEFT, 10)

        # and the real label, so we can refer to it later
        estimated_size_indicator = wx.StaticText(parent=win, id=wx.ID_ANY, label="0 Mb")
        estimated_size_indicator.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        estimated_size_indicator.SetForegroundColour(color_dark_green)

        half_part = wx.BoxSizer(orient=wx.VERTICAL)
        list_add_sizer.Add(half_part, 1, wx.RIGHT | wx.LEFT, 10)

        add_a_file = self.create_small_button(parent=list_add, length=150, text="ADD FILES",
                                              text_color=color_white, back_color=color_dark_grey,
                                              click_handler=lambda x: self.playlist_browse_for_files(convert_list))
        half_part.Add(add_a_file, 1)

        font_size_label = wx.StaticText(parent=list_add, id=wx.ID_ANY, label="Font Size:")
        half_part.Add(font_size_label, 1, wx.TOP, 5)
        font_size_slider = wx.Slider(parent=list_add, id=wx.ID_ANY, value=self.font_size, minValue=10, maxValue=50)
        half_part.Add(font_size_slider, 1, wx.EXPAND)
        font_size_slider.Bind(event=wx.EVT_SLIDER, handler=lambda evt: self.set_font_size(evt.GetInt()))

        pause_size_label = wx.StaticText(parent=list_add, id=wx.ID_ANY, label="Pause Time:")
        half_part.Add(pause_size_label, 1)
        pause_time_slider = wx.Slider(parent=list_add, id=wx.ID_ANY, value=self.pause_duration, minValue=1, maxValue=10)
        half_part.Add(pause_time_slider, 1, wx.EXPAND)
        pause_time_slider.Bind(event=wx.EVT_SLIDER, handler=lambda evt: self.set_pause_time(evt.GetInt()))

        watermark_cb = wx.CheckBox(parent=list_add, id=wx.ID_ANY, label="Watermark")
        half_part.Add(watermark_cb, self.watermark)
        watermark_cb.Bind(event=wx.EVT_CHECKBOX, handler=lambda evt: self.set_watermark_enabled(evt.GetInt()))

        # Estimated size
        estimated_size_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(estimated_size_sizer, 0, wx.LEFT, 10)
        # the header
        estimated_size_header = wx.StaticText(parent=win, id=wx.ID_ANY, label="Estimated Size ")
        estimated_size_header.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        estimated_size_header.SetForegroundColour(color_dark_green)
        estimated_size_sizer.Add(estimated_size_header)
        # we add it now
        estimated_size_sizer.Add(estimated_size_indicator)

        # current_preset = conversion_presets.GetStringSelection()
        # self.set_current_preset(current_preset, estimated_size_indicator)

        # test the drop target stuff?
        list_add.SetDropTarget(ConvertFileDrop(callback=lambda filenames, estimate: self.playlist_add_files(filenames,
                                                                                                           convert_list,
                                                                                                           estimated_size_indicator)))

        sizer.AddSpacer(70)

        # now the destination header
        destination_header = wx.StaticText(parent=win, id=wx.ID_ANY, label="Destination")
        sizer.Add(destination_header, 0, wx.LEFT, 10)

        # and the destination stuff
        destination_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(destination_sizer, 0, wx.LEFT | wx.RIGHT, 10)

        # first the file picker
        destination_text = wx.TextCtrl(parent=win, id=wx.ID_ANY, size=(200, 25))
        destination_sizer.Add(destination_text, wx.CENTER)

        if self.destination_dir != "":
            destination_text.SetLabel(self.destination_dir)

        # then the cancel button
        cancel_btn = self.create_small_button(parent=win, length=80, text="BROWSE",
                                              text_color=color_white, back_color=color_dark_grey,
                                              click_handler=lambda x: self.set_destination_dir(destination_text))
        destination_sizer.Add(cancel_btn, 1, wx.LEFT, 10)

        # then the cancel button
        cancel_btn = self.create_small_button(parent=win, length=100, text="GO BACK",
                                              text_color=color_dark_grey, back_color=color_white,
                                              click_handler=self.show_main,
                                              border_color=color_dark_grey)
        destination_sizer.Add(cancel_btn, 1, wx.LEFT, 10)

        # then the convert button
        convert_btn = self.create_small_button(parent=win, length=150, text="CREATE PLAYLIST",
                                               text_color=color_white, back_color=color_orange,
                                               click_handler=self.show_playlist_progress)
        destination_sizer.Add(convert_btn, 2, wx.RIGHT | wx.LEFT, 5)

        sizer.AddSpacer(23)

        # place footer
        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        return win

    def create_playlist_progress(self):
        win = wx.Window(parent=self, id=wx.ID_ANY)
        win.SetBackgroundColour(color_white)
        # main sizer
        sizer = wx.BoxSizer(orient=wx.VERTICAL)
        win.SetSizer(sizer)

        # place header
        header_window = self.create_header(parent=win)
        sizer.Add(header_window)

        # some space
        sizer.AddSpacer(115)

        # converting... file
        converting_header_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(converting_header_sizer, 0, wx.LEFT, 65)
        # the converting...
        converting_label = wx.StaticText(parent=win, id=wx.ID_ANY, label="Converting...")
        converting_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        converting_label.SetForegroundColour(color_dark_grey)
        converting_header_sizer.Add(converting_label)
        # the file name
        converting_file_label = wx.StaticText(parent=win, id=wx.ID_ANY, label=self.filenames[0])
        converting_file_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False))
        converting_file_label.SetForegroundColour(color_dark_grey)
        converting_header_sizer.Add(converting_file_label, 0, wx.LEFT, 10)

        sizer.AddSpacer(10)

        # convert box
        convert_box = wx.StaticBox(parent=win, id=wx.ID_ANY, size=(475, 90), label=" ")
        convert_box_sizer = wx.StaticBoxSizer(wx.HORIZONTAL, convert_box, label=" ")
        convert_box.SetSizer(convert_box_sizer)
        sizer.Add(convert_box, 0, wx.LEFT, 65)
        # convert icon
        # load bitmap from file
        raw_bitmap = wx.Bitmap(name="assets/progress_icon.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        static_bitmap = wx.StaticBitmap(parent=convert_box, id=wx.ID_ANY)
        static_bitmap.SetBitmap(raw_bitmap)
        # center in the middle, and give so
        convert_box_sizer.Add(static_bitmap, 0, wx.CENTER | wx.LEFT, 22)
        # now we add vertical sizer
        vertical_spacer = wx.BoxSizer(orient=wx.VERTICAL)
        convert_box_sizer.Add(vertical_spacer, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 20)

        estimate_text = wx.StaticText(parent=convert_box, id=wx.ID_ANY, label="Estimated time ? 0%")
        vertical_spacer.Add(estimate_text, 0, wx.ALIGN_LEFT | wx.TOP, 10)

        convert_gauge = wx.Gauge(parent=convert_box, id=wx.ID_ANY, range=100, size=(375, 15))
        vertical_spacer.Add(convert_gauge, 0, wx.TOP, 10)

        sizer.AddSpacer(100)

        cancel_btn = self.create_small_button(parent=win, length=105, text="CANCEL",
                                              back_color=color_white, text_color=color_black,
                                              click_handler=self.cancel_current_thread,
                                              border_color=color_dark_grey)
        sizer.Add(cancel_btn, 0, wx.ALIGN_CENTER)

        sizer.AddSpacer(40)

        # place footer
        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        return win, convert_gauge, estimate_text, converting_file_label

    def create_playlist_complete(self):
        win = wx.Window(parent=self, id=wx.ID_ANY)
        win.SetBackgroundColour(color_white)
        # main sizer
        sizer = wx.BoxSizer(orient=wx.VERTICAL)
        win.SetSizer(sizer)

        # place header
        header_window = self.create_header(parent=win)
        sizer.Add(header_window)

        # what do you want to do?
        select_window = wx.Window(parent=win, id=wx.ID_ANY, size=(600, 100))
        select_window.SetBackgroundColour(color_white)
        select_window_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        select_window.SetSizer(select_window_sizer)

        select_text = wx.StaticText(parent=select_window, id=wx.ID_ANY, label="What do you want to do?")
        select_text.SetFont(wx.Font(12, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        select_text.SetForegroundColour(color_home_headers)
        select_window_sizer.Add(select_text, 0, wx.CENTER | wx.TOP, 40)
        sizer.Add(select_window)

        sizer.AddSpacer(25)

        # done icon
        # load bitmap from file
        log_raw_bitmap = wx.Bitmap(name="assets/done_icon.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        logo_bitmap = wx.StaticBitmap(parent=win, id=wx.ID_ANY)
        logo_bitmap.SetBitmap(log_raw_bitmap)
        # center in the middle, and give so
        sizer.Add(logo_bitmap, 0, wx.CENTER)

        sizer.AddSpacer(20)

        # converting... file
        converting_header_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(converting_header_sizer, 0, wx.CENTER | wx.TOP, 20)
        # the converting...
        converting_label = wx.StaticText(parent=win, id=wx.ID_ANY, label="Complete: ")
        converting_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        converting_label.SetForegroundColour(color_dark_grey)
        converting_header_sizer.Add(converting_label)
        # the file name
        converting_file_label = wx.StaticText(parent=win, id=wx.ID_ANY, label=self.final_path)
        converting_file_label.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False))
        converting_file_label.SetForegroundColour(color_dark_grey)
        converting_header_sizer.Add(converting_file_label, 0, wx.LEFT, 10)

        sizer.AddSpacer(55)

        button_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(button_sizer, 1, wx.CENTER)

        cancel_btn = self.create_small_button(parent=win, length=150, text="GO BACK",
                                              back_color=color_white, text_color=color_black,
                                              click_handler=self.show_main,
                                              border_color=color_dark_grey)
        button_sizer.Add(cancel_btn)

        button_sizer.AddSpacer(20)

        open_btn = self.create_small_button(parent=win, length=150, text="OPEN",
                                            back_color=color_white, text_color=color_black,
                                            click_handler=self.open_final_path,
                                            border_color=color_dark_grey)
        button_sizer.Add(open_btn)

        sizer.AddSpacer(55)

        # place footer
        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        return win

os.makedirs(os.path.expanduser("~/VoConverter/"), exist_ok=True)
# trunc vo converter.log?
log_file = open(os.path.expanduser("~/VoConverter/voconverter.log"), "w")
log_file.truncate()
log_file.close()

settings_path = os.path.expanduser("~/VoConverter/voconverter.conf")
settings = EasySettings(settings_path)

app = wx.App(redirect=True, filename=os.path.expanduser("~/VoConverter/voconverter.log"))
# app = wx.App(redirect=False)
frame = MainWindow(None, "Videobserver Converter")
app.MainLoop()
