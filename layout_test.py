import wx
import webbrowser

# flags_center = wx.SizerFlags(1)
# flags_center.Center()

# some colors
color_dark_grey = wx.Colour(44, 49, 56)
color_orange = wx.Colour(255, 122, 0)
color_background_grey = wx.Colour(226, 228, 234)
color_home_back = wx.Colour(243, 245, 250)
color_home_text = wx.Colour(44, 49, 56)
color_home_headers = wx.Colour(155, 160, 167)
color_white = wx.WHITE
color_black = wx.BLACK


class MainWindow(wx.Frame):

    # main init
    def __init__(self, parent, title):

        # we don't want to allow resizing
        wx.Frame.__init__(self, parent, title=title, size=(600, 600),
                          style=wx.DEFAULT_FRAME_STYLE)

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

    # navigation
    def show_main(self, e):
        print("MAIN!")
        self.replace_view(self.create_main_screen())

    def show_convert_join(self, e):
        print("CONVERT / JOIN!")
        self.replace_view(self.create_convert_join_screen())

    def show_upload(self, e):
        pass

    def show_playlist(self, e):
        pass

    def show_convert(self, e):
        pass

    def show_join(self, e):
        pass

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
    def create_button(self, parent, size, file, text, back_color, text_color, hover_color, click_handler):

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
        anchor_window_sizer.Add(logo_bitmap, 0, wx.CENTER | wx.LEFT, 20)

        anchor_window_sizer.AddStretchSpacer(1)

        # create the login button
        login_window = wx.Window(parent=anchor_window, id=wx.ID_ANY, size=(125, 25))
        login_window.SetBackgroundColour(color_orange)

        login_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        login_window.SetSizer(login_sizer)

        login_raw_bitmap = wx.Bitmap(name="assets/login.png", type=wx.BITMAP_TYPE_PNG)
        logout_bitmap = wx.StaticBitmap(parent=login_window, id=wx.ID_ANY)
        logout_bitmap.SetBitmap(login_raw_bitmap)
        login_sizer.Add(logout_bitmap, 0, wx.CENTER | wx.LEFT, 6)

        # and now the username
        login_user = wx.StaticText(parent=login_window, id=wx.ID_ANY, label="Username")
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
        logout_sizer.Add(logout_bitmap, 0, wx.CENTER | wx.LEFT, 6)
        logout_window.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        anchor_window_sizer.Add(logout_window, 0, wx.CENTER | wx.RIGHT, 20)

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

    def go_to_help(self, e):
        webbrowser.open("http://faqs.videobserver.com/", new=0, autoraise=True)

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

        upload_btn = self.create_button(parent=win,
                                        size=(190, 190),
                                        file="assets/home_convert_file.png",
                                        text="CONVERT FILE",
                                        back_color=color_home_back,
                                        text_color=color_home_text,
                                        hover_color=color_home_headers,
                                        click_handler=self.show_convert_join)

        convert_btn = self.create_button(parent=win,
                                         size=(190, 190),
                                         file="assets/home_upload_file.png",
                                         text="UPLOAD",
                                         back_color=color_home_back,
                                         text_color=color_home_text,
                                         hover_color=color_home_headers,
                                         click_handler=self.show_upload)

        join_btn = self.create_button(parent=win,
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

        join_btn = self.create_button(parent=win,
                                      size=(280, 190),
                                      file="assets/home_create_playlist.png",
                                      text="JOIN FILES",
                                      back_color=color_home_back,
                                      text_color=color_home_text,
                                      hover_color=color_home_headers,
                                      click_handler=self.show_join)

        convert_btn = self.create_button(parent=win,
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


app = wx.App(False)

frame = MainWindow(None, "Layout Test")
app.MainLoop()
