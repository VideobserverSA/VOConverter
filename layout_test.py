import wx

# flags_center = wx.SizerFlags(1)
# flags_center.Center()

# some colors
color_dark_grey = wx.Colour(44, 49, 56)
color_orange = wx.Colour(255, 122, 0)
color_background_grey = wx.Colour(226, 228, 234)


class MainWindow(wx.Frame):

    def __init__(self, parent, title):

        # we don't want to allow resizing
        wx.Frame.__init__(self, parent, title=title, size=(900, 400),
                          style=wx.DEFAULT_FRAME_STYLE)

        # init the main screen
        # next calls will be via the replace view method
        self.main_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        self.current_window = self.create_main_screen()
        self.main_sizer.Add(self.current_window)
        self.SetSizer(self.main_sizer)

        self.Show()

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
        self.Update()

    def create_button(self, parent, file, text, back_color, text_color, click_handler):

        # a window so we can have a colored background
        anchor_window = wx.Window(parent=parent, id=wx.ID_ANY, size=(250, 200))
        anchor_window_sizer = wx.BoxSizer(orient=wx.VERTICAL)

        anchor_window.SetSizer(anchor_window_sizer)
        anchor_window.SetBackgroundColour(back_color)

        # load bitmap from file
        raw_bitmap = wx.Bitmap(name=file, type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        static_bitmap = wx.StaticBitmap(parent=anchor_window, id=wx.ID_ANY)
        static_bitmap.SetBitmap(raw_bitmap)
        # center in the middle, and give so
        anchor_window_sizer.Add(static_bitmap, 0, wx.CENTER | wx.TOP, 20)

        # the text label
        text_label = wx.StaticText(parent=anchor_window, id=wx.ID_ANY, label=text)
        text_label.SetFont(wx.Font(15, wx.FONTFAMILY_DECORATIVE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False, "Verdana"))
        text_label.SetForegroundColour(text_color)
        anchor_window_sizer.Add(text_label, 0, wx.CENTER | wx.TOP, 30)

        # we want the user to know that it can click here
        anchor_window.SetCursor(wx.Cursor(wx.CURSOR_HAND))

        # bind the clicks in all the components, so that anywhere in the "button" registers as a click
        anchor_window.Bind(wx.EVT_LEFT_DOWN, click_handler)
        static_bitmap.Bind(wx.EVT_LEFT_DOWN, click_handler)
        text_label.Bind(wx.EVT_LEFT_DOWN, click_handler)

        # anchor_window_sizer.SetMinSize((250, 200))
        # anchor_window_sizer.SetSizeHints(anchor_window)
        # component ready to use elsewhere
        return anchor_window

    def convert(self, e):
        print("CONVERT!")
        self.replace_view(self.create_second_screen())

    def join(self, e):
        print("JOIN!")
        self.replace_view(self.create_second_screen())

    def upload(self, e):
        print("UPLOAD!!")
        self.replace_view(self.create_main_screen())

    def create_main_screen(self):

        win = wx.Window(parent=self, id=wx.ID_ANY)

        sizer = wx.BoxSizer(orient=wx.VERTICAL)

        header_window = self.create_header(parent=win)
        sizer.Add(header_window)

        button_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        button_sizer.SetMinSize((600, 200))

        upload_btn = self.create_button(parent=win,
                                        file="test_icon.png",
                                        text="Upload File",
                                        back_color=wx.Colour(255, 255, 255),
                                        text_color=wx.BLACK,
                                        click_handler=self.join)

        convert_btn = self.create_button(parent=win,
                                         file="test_icon2.png",
                                         text="Convert File",
                                         back_color=color_orange,
                                         text_color=wx.WHITE,
                                         click_handler=self.convert)

        join_btn = self.create_button(parent=win,
                                      file="test_icon.png",
                                      text="Join File",
                                      back_color=wx.Colour(255, 255, 255),
                                      text_color=wx.BLACK,
                                      click_handler=self.join)

        button_sizer.Add(upload_btn, 0, wx.LEFT | wx.TOP | wx.BOTTOM, 10)
        button_sizer.Add(convert_btn, 0, wx.LEFT | wx.TOP | wx.BOTTOM, 10)
        button_sizer.Add(join_btn, 0, wx.LEFT | wx.TOP | wx.BOTTOM, 10)
        win.SetSizer(sizer)

        sizer.Add(button_sizer)

        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        return win

    def create_second_screen(self):

        win = wx.Window(parent=self, id=wx.ID_ANY)

        sizer = wx.BoxSizer(orient=wx.VERTICAL)

        header_window = self.create_header(parent=win)
        sizer.Add(header_window)

        button_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        button_sizer.SetMinSize((600, 200))

        convert_btn = self.create_button(parent=win,
                                         file="test_icon2.png",
                                         text="Upload",
                                         back_color=wx.BLUE,
                                         text_color=wx.WHITE,
                                         click_handler=self.upload)

        button_sizer.Add(convert_btn, 0, wx.LEFT | wx.TOP | wx.BOTTOM, 10)

        sizer.Add(button_sizer)

        footer_window = self.create_footer(parent=win)
        sizer.Add(footer_window)

        win.SetSizer(sizer)
        return win

    def create_header(self, parent):

        anchor_window = wx.Window(parent=parent, id=wx.ID_ANY, size=(800, 60))
        anchor_window.SetBackgroundColour(color_dark_grey)

        anchor_window_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)

        # load bitmap from file
        raw_bitmap = wx.Bitmap(name="assets/vo_logo.png", type=wx.BITMAP_TYPE_PNG)
        # to hold the raw bitmap
        logo_bitmap = wx.StaticBitmap(parent=anchor_window, id=wx.ID_ANY)
        logo_bitmap.SetBitmap(raw_bitmap)
        # center in the middle, and give so
        anchor_window_sizer.Add(logo_bitmap, 0, wx.CENTER | wx.LEFT, 20)

        anchor_window_sizer.AddStretchSpacer(1)

        # create the login button
        login_window = wx.Window(parent=anchor_window, id=wx.ID_ANY, size=(200, 25))
        login_window.SetBackgroundColour(color_orange)

        anchor_window_sizer.Add(login_window, 0, wx.CENTER | wx.RIGHT, 20)

        anchor_window.SetSizer(anchor_window_sizer)

        return anchor_window

    def create_footer(self, parent):

        anchor_window = wx.Window(parent=parent, id=wx.ID_ANY, size=(800, 35))
        anchor_window.SetBackgroundColour(color_background_grey)

        anchor_window_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)

        copyright_text = wx.StaticText(parent=anchor_window, id=wx.ID_ANY, label="© VIDEOBSERVER 2016")
        copyright_text.SetForegroundColour(color_orange)

        anchor_window_sizer.Add(copyright_text, 0, wx.CENTER | wx.LEFT, 20)

        anchor_window.SetSizer(anchor_window_sizer)

        return anchor_window


app = wx.App(False)

frame = MainWindow(None, "Layout Test")
app.MainLoop()
