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
from boto3.session import Session
import math

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


class ListFileDrop(wx.FileDropTarget):

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
        self.destination_dir = os.path.expanduser("~" + "\\" + "Desktop")
        # self.destination_dir = ""
        self.filenames = []
        self.preset = ""

        self.temp_dir = tempfile.TemporaryDirectory()

        self.current_progress = 0
        self.progress_start_time = time.time()
        self.data_points = []

        self.final_path = ""

        self.current_thread = threading.Thread()

        self.logged_in = False
        self.token = {}
        self.aws_data = {}
        self.login_dialog = None
        self.username_to_display = ""

        self.current_upload_size = 0

        # init the main screen
        # next calls will be via the replace view method
        self.main_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        self.current_window = self.create_main_screen()
        self.main_sizer.Add(self.current_window)
        self.SetSizer(self.main_sizer)

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
            # print(remain)
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
            call(["open", self.final_path])
        else:
            os.startfile(self.final_path)

    # abandon thread
    def cancel_current_thread(self, e):
        self.current_thread.abort()

    # navigation
    def show_main(self, e):
        print("MAIN!")
        self.replace_view(self.create_main_screen())

    def show_convert_join(self, e):
        print("CONVERT / JOIN!")
        self.replace_view(self.create_convert_join_screen())

    def show_upload(self, e):
        print("UPLOAD")
        if not self.logged_in:
            self.create_alert_dialog(parent=self, title="Not logged in",
                                     message="You must be logged in to upload files",
                                     is_ok_type=True)
            return
        self.filenames = []
        self.replace_view(self.create_upload_screen())

    def show_playlist(self, e):
        pass

    def show_convert(self, e):
        print("CONVERT")
        self.filenames = []
        self.replace_view(self.create_convert_screen())

    def show_join(self, e):
        pass

    def show_convert_progress(self, e):
        # sanity check
        if self.destination_dir == "":
            print("NO DESTINATION DIR")
            return
        if len(self.filenames) < 1:
            print("NO FILES TO CONVERT")
            return
        if self.preset == "":
            print("NO PRESET")
            return
        print("CONVERT PROGRESS")
        win, gauge, text = self.create_convert_progress()
        self.replace_view(win)

        presets, choices = convert_functions.get_presets()
        the_preset = [x for x in presets if x.name == self.preset][0]

        out_video = self.destination_dir + path_separator + os.path.basename(self.filenames[0].split(".")[0]) + ".mp4"
        if os.path.exists(out_video):
            out_video = out_video = self.destination_dir + path_separator + os.path.basename(self.filenames[0].split(".")[0]) + "_1.mp4"

        files_with_info = []
        # get the video_infos
        for file in self.filenames:
            file_to_convert = convert_functions.FileToConvert()
            file_to_convert.file = file
            file_to_convert.video_info = convert_functions.get_video_info(file)
            files_with_info.append(file_to_convert)

        self.current_thread = join_thr = convert_functions.JoinFiles(in_videos=files_with_info,
                                                                     out_video=out_video,
                                                                     tmp_dir=self.temp_dir,
                                                                     preset=the_preset,
                                                                     callback=lambda progress: self.mark_progress(progress))

        join_thr.start()

        self.reset_progress()

        while join_thr.is_alive():
            dummy_event = threading.Event()
            dummy_event.wait(timeout=0.01)

            self.update_progress(gauge, text)

            wx.Yield()
            self.Update()

        self.final_path = out_video
        self.filenames = [out_video]
        self.show_convert_complete(None)

    def show_convert_complete(self, e):
        print("CONVERT COMPLETE")
        self.replace_view(self.create_convert_complete())

    # utility function
    def convert_add_files(self, filenames, the_list):
        for file in filenames:
            the_list.Append([file])
            self.filenames.append(file)

    def convert_browse_for_files(self, the_list):
        path = ""
        dlg = wx.FileDialog(self, "Video file", "", "", "*.*", wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()

        dlg.Destroy()
        if path != "":
            self.convert_add_files([path], the_list)

    def set_destination_dir(self, text_ctrl):
        path = ""
        dlg = wx.DirDialog(self, "Destination Directory")
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()

        dlg.Destroy()
        if path != "":
            self.destination_dir = path
            text_ctrl.SetLabel(path)

    def set_current_preset(self, preset):
        self.preset = preset
        print("preset: ", preset)

    def show_upload_progress(self, e):
        print("DO THE UPLOAD")

        if not self.logged_in:
            self.create_alert_dialog(parent=self, title="Not logged in",
                                     message="You must be logged in to upload files",
                                     is_ok_type=True)
            return

        upload_key = os.path.basename(self.filenames[0])
        print("Upload key", upload_key)

        win, gauge, text = self.create_upload_progress()
        self.replace_view(win)

        self.reset_progress()

        # init s3 session
        aws_session = Session(aws_access_key_id=self.aws_data["AccessKeyId"],
                              aws_secret_access_key=self.aws_data["SecretAccessKey"],
                              aws_session_token=self.aws_data["SessionToken"],
                              region_name=self.aws_data["Region"])

        # first create and object to send
        client = aws_session.client(service_name="s3",
                                    endpoint_url=self.aws_data["CloudfrontEndpoint"])

        # we cheat so that the user can see some progress at start
        gauge.Pulse()

        total_size = os.stat(self.filenames[0]).st_size
        self.current_upload_size = 0

        upload_thr = aws.UploadFile(s3client=client,
                                    bucket=self.aws_data["Bucket"],
                                    key=upload_key,
                                    file=self.filenames[0],
                                    progress_callback=lambda progress: self.mark_upload_progress(progress, total_size),
                                    resume_callback=lambda progress: self.mark_progress(progress),
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
        final_video_info = convert_functions.get_video_info(self.filenames[0])

        print("file duration", final_video_info.duration)

        aws.confirm_upload(self.token["token"],
                           bucket=self.aws_data["Bucket"],
                           key=upload_key,
                           duration=int(float(final_video_info.duration)),
                           size=100)
        self.final_path = self.filenames[0]
        self.show_upload_complete(None)

        # show complete

    def mark_upload_progress(self, progress, total):
        print("UP:", progress, total)
        self.current_upload_size += progress
        percentage = math.ceil((self.current_upload_size / total) * 100)
        self.mark_progress(percentage)

    def show_upload_complete(self, e):
        print("UPLOAD COMPLETE")
        self.replace_view(self.create_upload_complete())

    # show the next screen
    def replace_view(self, new_view_creator):
        # remove the previous view
        self.current_window.Destroy()
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
                            no_click_handler = None, yes_click_handler = None ):

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

            no_btn = self.create_small_button(parent=back_window, length=100, text="NO",
                                              back_color=color_white, text_color=color_dark_grey,
                                              border_color=color_dark_grey,
                                              click_handler=no_click_handler)
            button_sizer.Add(no_btn, 1)

            button_sizer.AddSpacer(10)

            yes_btn = self.create_small_button(parent=back_window, length=100, text="YES",
                                               back_color=color_orange, text_color=color_white,
                                               click_handler=yes_click_handler)
            button_sizer.Add(yes_btn, 1)

        back_window_sizer.Add(button_sizer, 1, wx.CENTER | wx.TOP, 10)

        dialog.Show()
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
        else:
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
        username = wx.TextCtrl(parent=back_window, id=wx.ID_ANY, size=(270, 25), value="soccer_teste@vo.com")
        back_window_sizer.Add(username, 0, wx.CENTER | wx.LEFT | wx.RIGHT, 20)

        # space before
        back_window_sizer.AddSpacer(10)

        # password
        password_label = wx.StaticText(parent=back_window, id=wx.ID_ANY, label="Password")
        password_label.SetFont(wx.Font(8, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False))
        password_label.SetForegroundColour(color_dark_grey)
        back_window_sizer.Add(password_label, 0, wx.LEFT, 20)
        password = wx.TextCtrl(parent=back_window, id=wx.ID_ANY, size=(270, 25), style=wx.TE_PASSWORD, value="password")
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

    def go_to_help(self, e):
        webbrowser.open("http://faqs.videobserver.com/", new=0, autoraise=True)

    def lost_pass(self, e):
        webbrowser.open("https://www.videobserver.com/forgot-password", new=0, autoraise=True)

    def do_login(self, username, password, remember):
        code, self.token = aws.get_token(username, password)
        if code == 200:
            self.login_dialog.Destroy()
            self.aws_data = aws.get_aws_data(self.token["token"])
            self.logged_in = True
            self.username_to_display = username

        if code == 2:
            dialog = self.create_alert_dialog(parent=self,
                                              title="Login Failed",
                                              message="Wrong user name or password",
                                              is_ok_type=True)
            print("wrong user and pass")

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
        conversion_presets = wx.RadioBox(parent=win, id=wx.ID_ANY, choices=["Full HD", "HD", "DVD", "Original"],
                                         style=wx.BORDER_NONE)
        sizer.Add(conversion_presets, 0, wx.LEFT, 10)
        conversion_presets.Bind(wx.EVT_RADIOBOX, lambda x: self.set_current_preset(conversion_presets.GetStringSelection()))

        current_preset = conversion_presets.GetStringSelection()
        self.set_current_preset(current_preset)

        # drag list and add a file btn
        list_add = wx.Window(parent=win, id=wx.ID_ANY, size=(600, 170))
        list_add.SetBackgroundColour(color_white)
        list_add_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        list_add.SetSizer(list_add_sizer)
        sizer.Add(list_add, 0, wx.TOP, 10)

        convert_list = wx.ListView(parent=list_add, winid=wx.ID_ANY, style=wx.LC_REPORT)
        convert_list.AppendColumn("Drag & Drop to Convert or Add a File.", wx.LIST_FORMAT_CENTER, 400)
        list_add_sizer.Add(convert_list, 3, wx.RIGHT | wx.LEFT, 10)

        # test the drop target stuff?
        list_add.SetDropTarget(ListFileDrop(callback=lambda filenames: self.convert_add_files(filenames, convert_list)))

        add_a_file = self.create_small_button(parent=list_add, length=150, text="ADD A FILE",
                                              text_color=color_white, back_color=color_dark_grey,
                                              click_handler=lambda x: self.convert_browse_for_files(convert_list))
        list_add_sizer.Add(add_a_file, 1, wx.RIGHT | wx.LEFT, 10)

        # Estimated size
        estimated_size_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        sizer.Add(estimated_size_sizer, 0, wx.LEFT, 10)
        # the header
        estimated_size_header = wx.StaticText(parent=win, id=wx.ID_ANY, label="Estimated Size ")
        estimated_size_header.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        estimated_size_header.SetForegroundColour(color_dark_green)
        estimated_size_sizer.Add(estimated_size_header)
        # and the real label
        estimated_size_indicator = wx.StaticText(parent=win, id=wx.ID_ANY, label="XXXX Mb")
        estimated_size_indicator.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
        estimated_size_indicator.SetForegroundColour(color_dark_green)
        estimated_size_sizer.Add(estimated_size_indicator)

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

        sizer.AddSpacer(20)

        # place footer
        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        return win

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

        return win, convert_gauge, estimate_text

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

        # convert just one file
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

        convert_list = wx.ListView(parent=list_add, winid=wx.ID_ANY, style=wx.LC_REPORT)
        convert_list.AppendColumn("Drag & Drop to Upload or Add a File.", wx.LIST_FORMAT_CENTER, 400)
        list_add_sizer.Add(convert_list, 3, wx.RIGHT | wx.LEFT, 10)

        # test the drop target stuff?
        list_add.SetDropTarget(ListFileDrop(callback=lambda filenames: self.convert_add_files(filenames, convert_list)))

        add_a_file = self.create_small_button(parent=list_add, length=150, text="ADD A FILE",
                                              text_color=color_white, back_color=color_dark_grey,
                                              click_handler=lambda x: self.convert_browse_for_files(convert_list))
        list_add_sizer.Add(add_a_file, 1, wx.RIGHT | wx.LEFT, 10)

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

        return win, convert_gauge, estimate_text

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

app = wx.App(False)

frame = MainWindow(None, "Layout Test")
app.MainLoop()
