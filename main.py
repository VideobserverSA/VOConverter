__author__ = 'Rui'

from tkinter import *
from tkinter import filedialog
import xml.etree.ElementTree as xmlParser
from subprocess import *
import os
import tempfile

ffmpeg_path = "ffmpeg.exe"

root = Tk()

class FileChooser(object):

    def __init__(self):
        btn = Button(text="Open File", command=self.open_dialog)
        btn.pack()

        another = Button(text="Quit", command=self.quit_app)
        another.pack()

    def open_dialog(self):

        initial_dir = os.path.expanduser("~/Documents/VideoObserver/Playlist")

        fn = filedialog.askopenfilename(filetypes=(("VO Playlist", "*.vopl"),
                                                   ("All Files", "*.*")),
                                        initialdir=initial_dir
                                        )
        self.parse_playlist(filename=fn)

    def quit_app(self):
        exit()

    def parse_playlist(self, filename):

        # to keep the cut files
        temp_dir = tempfile.TemporaryDirectory()
        # we have a name so make sure we create the dir
        if not os.path.exists(temp_dir.name):
            os.makedirs(temp_dir.name)

        print("INfile>> ", filename)
        tree = xmlParser.parse(filename)
        base = tree.getroot()
        video_path = base.get("video_path")
        video_path = video_path[8:]
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
                time_start = int(child.find("game_action").find("video_time_start").text)
                time_end = int(child.find("game_action").find("video_time_end").text)
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
                out = check_output([
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
                ], shell=False)

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
            concat += temp_dir.name + "\\" + str(x) + ".mp4" + "|"
        concat = concat[:-1]
        join_args.append(concat)
        # outfile
        # put it on desktop for now
        desktop_dir = os.path.expanduser("~/Desktop/")
        join_args.append(desktop_dir + "\\" + "final" + ".mp4")

        try:
            out = check_output(join_args, shell=False)
        except CalledProcessError as cpe:
            print("ERROR>>", cpe.output)

        # Cleanup
        temp_dir.cleanup()

        # DEBUG
        exit()

if __name__ == '__main__':
    fc = FileChooser()
    mainloop()
