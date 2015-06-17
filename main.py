__author__ = 'Rui'

from tkinter import *
from tkinter import filedialog
import xml.etree.ElementTree as xmlParser
from subprocess import *
import os
import tempfile
import sys

ffmpeg_path = "ffmpeg.exe"

root = Tk()

class FileChooser(object):

    # meter = ""
    # num_items = ""

    def __init__(self):
        btn = Button(text="Open File", command=self.open_dialog)
        btn.pack()

        self.meter = Meter(root, bg="white", fillcolor="light blue")
        self.meter.pack()

        another = Button(text="Quit", command=self.quit_app)
        another.pack()

        self.temp_dir = tempfile.TemporaryDirectory()

    def open_dialog(self):

        initial_dir = os.path.expanduser("~/Documents/VideoObserver/Playlist")

        fn = filedialog.askopenfilename(filetypes=(("VO Playlist", "*.vopl"),
                                                   ("All Files", "*.*")),
                                        initialdir=initial_dir
                                        )
        self.parse_playlist(filename=fn)

    def quit_app(self):

        # Cleanup
        self.temp_dir.cleanup()

        sys.exit(0)

    def parse_playlist(self, filename):

        # to keep the cut files

        # we have a name so make sure we create the dir
        if not os.path.exists(self.temp_dir.name):
            os.makedirs(self.temp_dir.name)

        print("INfile>> ", filename)
        tree = xmlParser.parse(filename)
        base = tree.getroot()
        video_path = base.get("video_path")

        # get playlist length
        play_len = len(base.findall('.items/item'))
        print("NItems>> ", play_len)
        # we say that the join is the last step
        play_len += 1
        self.num_items = play_len
        self.meter.set(0.0, "Converting: " + base.get("name") + " " + "0%")

        # now if we have the file:/// present we remove it
        video_path = video_path.replace("file:///", "")

        print("VPath>> ", video_path)

        print("")

        cut_number = 0
        # start parsing each item
        for child in base.findall('.items/item'):
            item_type = child.find("type").text
            print("ItemType>> ", item_type)

            time_start = ""
            time_end = ""
            comments = ""

            if item_type == "ga":
                time_start = int(float(child.find("game_action").find("video_time_start").text))
                time_end = int(float(child.find("game_action").find("video_time_end").text))
                comments = child.find("game_action").find("comments").text

            if item_type == "cue":
                time_start = int(child.find("action_cue").find("starting_time").text)
                time_end = int(child.find("action_cue").find("ending_time").text)
                comments = child.find("action_cue").find("comments").text

            print("TimeStart>> ", time_start)
            print("TimeEnd>> ", time_end)
            print("Comments>> ", comments)

            print("")

            duration = time_end - time_start
            tmp_out = temp_dir.name + "\\" + str(cut_number) + ".mp4"
            cut_number += 1

            try:
                # out = check_output([ffmpeg_path, args], shell=False)
                out = check_call([
                    # path to ffmpeg
                    ffmpeg_path,
                    # overwrite
                    "-y",
                    # start time
                    "-ss",
                    str(time_start),
                    # input file
                    "-i",
                    video_path,
                    # duration
                    "-t",
                    str(duration),
                    # codec
                    "-c",
                    "copy",
                    "-bsf:v",
                    "h264_mp4toannexb",
                    "-f",
                    "mpegts",
                    # output file
                    tmp_out
                    ], shell=True)
                # calc progress
                progress = (cut_number / self.num_items)
                self.meter.set(progress, "Converting: " + base.get("name") + " " + str((progress * 100)) + "%")

            except CalledProcessError as cpe:
                print("ERROR>> ", cpe.output)

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
            concat += self.temp_dir.name + "\\" + str(x) + ".mp4" + "|"
        concat = concat[:-1]
        join_args.append(concat)
        # outfile
        # put it on desktop for now
        desktop_dir = os.path.expanduser("~/Desktop/")
        join_args.append(desktop_dir + "\\" + base.get("name") + ".mp4")

        try:
            out = check_output(join_args, shell=False)
        except CalledProcessError as cpe:
            print("ERROR>>", cpe.output)

        self.meter.set(1, "Done: " + base.get("name") + " " + "100" + "%")

        # DEBUG
        # sys.exit(0)

# CODE FOR PROGRESS BAR
class Meter(Frame):
    def __init__(self, master, width=300, height=20, bg='white', fillcolor='orchid1',\
                 value=0.0, text=None, font=None, textcolor='black', *args, **kw):
        Frame.__init__(self, master, bg=bg, width=width, height=height, *args, **kw)
        self._value = value

        self._canv = Canvas(self, bg=self['bg'], width=self['width'], height=self['height'],\
                                    highlightthickness=0, relief='flat', bd=0)
        self._canv.pack(fill='both', expand=1)
        self._rect = self._canv.create_rectangle(0, 0, 0, self._canv.winfo_reqheight(), fill=fillcolor,\
                                                 width=0)
        self._text = self._canv.create_text(self._canv.winfo_reqwidth()/2, self._canv.winfo_reqheight()/2,\
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
        if text == None:
            # if no text is specified use the default percentage string:
            text = str(int(round(100 * value))) + ' %'
        self._canv.coords(self._rect, 0, 0, self._canv.winfo_width()*value, self._canv.winfo_height())
        self._canv.itemconfigure(self._text, text=text)
        self._canv.update_idletasks()

if __name__ == '__main__':
    fc = FileChooser()
    mainloop()
